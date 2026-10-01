"""scripts/deploy.sh behaviour, hermetic: temp git repos + stub systemctl/curl/tmux.

Pins the fail-closed rules: no silent tmux fallback, only commits on
origin/main, /health must report database=true, rollback on a failed deploy.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(BASH is None or GIT is None, reason="bash and git required")


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def _git(cwd: Path, *args: str) -> str:
    result = _run([str(GIT), *args], cwd)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def host(tmp_path: Path) -> dict:
    """origin (bare) with commits good -> bad on main; checkout at good."""
    seed, origin, work, bin_dir = (tmp_path / n for n in ("seed", "origin.git", "work", "bin"))
    for d in (seed, bin_dir):
        d.mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(seed))
    _git(seed, "config", "user.email", "t@example.com")
    _git(seed, "config", "user.name", "t")
    (seed / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "deploy.sh", seed / "scripts" / "deploy.sh")
    (seed / "requirements.txt").write_text("", encoding="utf-8")
    (seed / "marker").write_text("good", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-q", "-m", "good")
    good = _git(seed, "rev-parse", "HEAD")
    (seed / "marker").write_text("bad", encoding="utf-8")
    _git(seed, "commit", "-q", "-am", "bad")
    bad = _git(seed, "rev-parse", "HEAD")
    _git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "reset", "-q", "--hard", good)

    calls = tmp_path / "calls.log"
    _stub(bin_dir, "systemctl", f'echo "systemctl $*" >> {calls}\n'
          'if [[ "$*" == *LoadState* ]]; then echo "${STUB_LOADSTATE:-loaded}"; fi\n')
    # Healthy only when the checked-out marker says "good".
    _stub(bin_dir, "curl", f'if [[ "$(cat {work}/marker)" == good ]]; then echo \'{{"status":"healthy","database":true}}\';'
          ' else echo \'{"status":"healthy","database":false}\'; fi\n')
    _stub(bin_dir, "tmux", f'echo "tmux $*" >> {calls}\n')
    _stub(bin_dir, "journalctl", "true\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DEPLOY_SKIP_PIP_INSTALL": "1",
        "DEPLOY_HEALTH_RETRIES": "2",
        "DEPLOY_HEALTH_INTERVAL": "0",
        "XDG_RUNTIME_DIR": str(tmp_path),
    }
    return {"work": work, "env": env, "good": good, "bad": bad, "calls": calls, "seed": seed}


def _deploy(host: dict, **extra: str) -> subprocess.CompletedProcess:
    return _run([str(BASH), "scripts/deploy.sh"], host["work"], {**host["env"], **extra})


def _calls(host: dict) -> str:
    return host["calls"].read_text(encoding="utf-8") if host["calls"].exists() else ""


def test_deploys_requested_sha_and_checks_database(host: dict) -> None:
    result = _deploy(host, DEPLOY_SHA=host["good"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(host["work"], "rev-parse", "HEAD") == host["good"]
    assert "systemctl --user restart theeyebeta-dataapi" in _calls(host)


def test_unhealthy_deploy_rolls_back_and_fails(host: dict) -> None:
    result = _deploy(host)  # origin/main == bad: database=false
    assert result.returncode == 1
    assert "ROLLBACK" in result.stdout
    assert "Rollback to" in result.stdout and "is healthy" in result.stdout
    assert _git(host["work"], "rev-parse", "HEAD") == host["good"]
    assert _calls(host).count("systemctl --user restart") == 2


def test_refuses_sha_not_on_main(host: dict) -> None:
    _git(host["work"], "checkout", "-q", "-b", "side")
    (host["work"] / "marker").write_text("side", encoding="utf-8")
    _git(host["work"], "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-am", "side")
    side = _git(host["work"], "rev-parse", "HEAD")
    result = _deploy(host, DEPLOY_SHA=side)
    assert result.returncode == 1
    assert "is not on origin/main" in result.stdout
    assert "restart" not in _calls(host)


def test_missing_unit_fails_instead_of_starting_tmux(host: dict) -> None:
    result = _deploy(host, DEPLOY_SKIP_GIT_SYNC="1", STUB_LOADSTATE="not-found")
    assert result.returncode == 1
    assert "Refusing to start a second, unmanaged gunicorn" in result.stdout
    assert "tmux" not in _calls(host)


def test_tmux_fallback_is_explicit_opt_in(host: dict) -> None:
    result = _deploy(host, DEPLOY_SKIP_GIT_SYNC="1", STUB_LOADSTATE="not-found", DEPLOY_ALLOW_TMUX_FALLBACK="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tmux new-session" in _calls(host)
