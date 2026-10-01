"""Tunnel routing: config, docs and scripts must tell the same story.

docs/OWNERSHIP.md section 2 is the canonical routing table. The tunnel is
shared with TheEyeBetaProd and TheEyeBetaLocal, so nothing automatic may push
configuration to it (docs/TUNNEL_RUNBOOK.md "Change policy").
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "deploy" / "cloudflared-config.yml"
SCRIPTS = ROOT / "scripts"

# hostname -> origin (target architecture). Changing a row is a cross-repo
# decision. admin -> :8080 is DEBT-01's decision (2026-10-01): the AdminFrontend
# static terminal host; admin-service (:7200) is reachable only through
# DataAPI's /admin/* gateway and must never be a tunnel origin.
EXPECTED = {
    "dataapiprod.theeyebeta.store": "127.0.0.1:7000",
    "dataapi.theeyebeta.store": "127.0.0.1:7000",
    "admin.theeyebeta.store": "127.0.0.1:8080",
    "api.theeyebeta.store": "127.0.0.1:8000",
}
ADMIN_SERVICE_ORIGIN = "127.0.0.1:7200"


def _config_ingress() -> dict[str, str]:
    routes: dict[str, str] = {}
    hostname = None
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- hostname:"):
            hostname = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("service:") and hostname:
            routes[hostname] = stripped.split(":", 1)[1].strip().removeprefix("http://")
            hostname = None
    return routes


def _doc_rows(path: Path) -> dict[str, str]:
    """First `host` -> `origin` pair per hostname, from markdown table rows or tree lines."""
    rows: dict[str, str] = {}
    table = re.compile(r"^\|\s*`(?:https://)?([a-z.]+theeyebeta\.store)`\s*\|\s*`([0-9.:]+)`")
    tree = re.compile(r"──\s*([a-z.]+theeyebeta\.store)\s*→\s*([0-9.:]+)")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = table.match(line) or tree.search(line)
        if match and match.group(1) not in rows:
            rows[match.group(1)] = match.group(2)
    return rows


def test_config_matches_canonical_table() -> None:
    assert _config_ingress() == EXPECTED


def test_config_ends_with_catch_all_404() -> None:
    services = [
        line.strip()
        for line in CONFIG.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- service:")
    ]
    assert services == ["- service: http_status:404"]


@pytest.mark.parametrize("doc", ["docs/OWNERSHIP.md", "README.md", "docs/TUNNEL_RUNBOOK.md"])
def test_docs_agree_with_config(doc: str) -> None:
    rows = _doc_rows(ROOT / doc)
    for host, origin in EXPECTED.items():
        assert rows.get(host) == origin, f"{doc}: {host} should route to {origin}, found {rows.get(host)}"


def test_admin_service_is_never_a_tunnel_origin() -> None:
    assert ADMIN_SERVICE_ORIGIN not in _config_ingress().values()


def test_no_doc_routes_admin_hostname_to_admin_service() -> None:
    for doc in ["AGENTS.md", "README.md", "docs/OWNERSHIP.md", "docs/TUNNEL_RUNBOOK.md", "docs/PRODUCTION_RUNBOOK.md"]:
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert not re.search(r"admin\.theeyebeta\.store`?\s*(?:\|\s*`|→|->)\s*`?127\.0\.0\.1:7200", text), doc


def test_config_carries_do_not_apply_warning() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "DO NOT APPLY until the AdminFrontend :8080 health check passes" in text


@pytest.mark.parametrize("script", ["watchdog_all.sh", "start_all_native.sh", "deploy.sh"])
def test_automatic_scripts_never_reconfigure_tunnel(script: str) -> None:
    code = "\n".join(
        line
        for line in (SCRIPTS / script).read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    for forbidden in ("sync_tunnel.sh", "fix_tunnel.sh", "cloudflared tunnel route", "/configurations"):
        assert forbidden not in code, f"{script} must not run {forbidden}"


@pytest.mark.parametrize("script", ["watchdog_all.sh", "start_all_native.sh"])
def test_local_repo_is_explicit_opt_in(script: str) -> None:
    text = (SCRIPTS / script).read_text(encoding="utf-8")
    assert 'LOCAL_DIR="${THEEYE_LOCAL_REPO:-}"' in text
    assert "../TheEyeBetaLocal" not in text


@pytest.mark.parametrize("script", ["sync_tunnel.sh", "fix_tunnel.sh"])
def test_tunnel_scripts_are_approval_gated(script: str) -> None:
    text = (SCRIPTS / script).read_text(encoding="utf-8")
    gate = text.index('TUNNEL_CHANGE_APPROVED:-}" != "yes"')
    for action in ("cloudflared tunnel route", "systemctl restart", 'cp "$CANONICAL_CONFIG"'):
        position = text.find(action)
        if position != -1:
            assert position > gate, f"{script}: '{action}' runs before the approval gate"


@pytest.mark.parametrize("script", ["sync_tunnel.sh", "fix_tunnel.sh"])
def test_tunnel_scripts_check_terminal_health_before_any_change(script: str) -> None:
    text = (SCRIPTS / script).read_text(encoding="utf-8")
    guard = text.index("REFUSING: AdminFrontend terminal host is not healthy")
    assert guard > text.index('TUNNEL_CHANGE_APPROVED:-}" != "yes"')
    for action in ("cloudflared tunnel route", "systemctl restart", 'cp "$CANONICAL_CONFIG"', "tmux kill-session"):
        position = text.find(action)
        if position != -1:
            assert position > guard, f"{script}: '{action}' runs before the :8080 health guard"


BASH = shutil.which("bash")


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("script", ["sync_tunnel.sh", "fix_tunnel.sh"])
def test_tunnel_scripts_dry_run_without_approval(script: str) -> None:
    env = {k: v for k, v in os.environ.items() if k != "TUNNEL_CHANGE_APPROVED"}
    result = subprocess.run(  # noqa: S603 - fixed repo script, no user input
        [str(BASH), str(SCRIPTS / script)], capture_output=True, text=True, env=env, timeout=30, check=False
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "DRY RUN" in result.stdout
    assert "admin.theeyebeta.store" in result.stdout


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("script", ["sync_tunnel.sh", "fix_tunnel.sh"])
def test_approved_run_refuses_while_terminal_host_is_down(script: str, tmp_path: Path) -> None:
    """Approval alone is not enough: an unhealthy :8080 stops the script (exit 3)
    before it touches cloudflared, systemd or any config file."""
    calls = tmp_path / "calls.log"
    for name in ("cloudflared", "systemctl", "tmux", "cp", "sudo"):
        stub = tmp_path / name
        stub.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> {calls}\n', encoding="utf-8")
        stub.chmod(0o755)
    (tmp_path / "curl").write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")  # connection refused
    (tmp_path / "curl").chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "TUNNEL_CHANGE_APPROVED": "yes"}
    result = subprocess.run(  # noqa: S603 - fixed repo script, no user input
        [str(BASH), str(SCRIPTS / script)], capture_output=True, text=True, env=env, timeout=30, check=False
    )
    assert result.returncode == 3, result.stdout + result.stderr
    assert "DO NOT APPLY" in result.stderr
    assert not calls.exists(), calls.read_text(encoding="utf-8")
