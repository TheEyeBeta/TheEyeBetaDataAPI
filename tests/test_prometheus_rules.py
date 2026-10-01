"""deploy/prometheus/rules/*.yml must be loadable and match what the app exports.

CI also runs `promtool check rules` (ci.yml lint job). Whether TheEyeBetaProd's
Prometheus actually loads these rules is a host/cross-repo fact (DEBT-13).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app

RULES = sorted((Path(__file__).resolve().parents[1] / "deploy" / "prometheus" / "rules").glob("*.yml"))


def _rules() -> list[dict]:
    rules = []
    for path in RULES:
        for group in yaml.safe_load(path.read_text(encoding="utf-8"))["groups"]:
            rules.extend(group["rules"])
    return rules


def test_rule_files_exist() -> None:
    assert RULES


@pytest.mark.parametrize("rule", _rules(), ids=lambda r: r["alert"])
def test_rule_shape(rule: dict) -> None:
    assert set(rule) >= {"alert", "expr", "labels", "annotations"}
    assert rule["labels"]["severity"] in {"info", "warning", "critical"}
    assert rule["annotations"].get("summary")


@pytest.mark.parametrize("rule", _rules(), ids=lambda r: r["alert"])
def test_rule_references_exported_metrics_and_real_routes(rule: dict) -> None:
    # Generate a sample so the instrumentator has emitted every series once.
    client = TestClient(app, client=("127.0.0.1", 50000))
    client.post("/api/v1/auth/service-token", json={})
    exported = client.get("/metrics").text
    for metric in re.findall(r"\b([a-z_]+_total)\{", rule["expr"]):
        assert f"{metric}{{" in exported, f"{rule['alert']}: {metric} is not exported by the app"
    assert "status=~\"4xx" not in rule["expr"], "status codes are not grouped (should_group_status_codes=False)"

    routes = list(app.openapi()["paths"])
    for kind, value in re.findall(r'handler(=~?)"([^"]+)"', rule["expr"]):
        if kind == "=":
            assert value in routes, f"{rule['alert']}: unknown handler {value}"
        else:
            assert any(re.fullmatch(value, route) for route in routes), f"{rule['alert']}: {value} matches no route"
