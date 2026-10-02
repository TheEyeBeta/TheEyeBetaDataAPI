"""/metrics is for a local Prometheus only, never through the public tunnel."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def _client(host: str) -> TestClient:
    return TestClient(app, client=(host, 50000))


def test_loopback_scrape_is_served() -> None:
    response = _client("127.0.0.1").get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text or "# HELP" in response.text


@pytest.mark.parametrize("header", ["CF-Connecting-IP", "CF-Ray", "X-Forwarded-For", "X-Real-IP", "Forwarded"])
def test_tunnel_request_from_loopback_is_refused(header: str) -> None:
    # cloudflared connects from 127.0.0.1 but always adds Cloudflare headers.
    response = _client("127.0.0.1").get("/metrics", headers={header: "203.0.113.9"})
    assert response.status_code == 404


def test_non_loopback_peer_is_refused() -> None:
    assert _client("203.0.113.9").get("/metrics").status_code == 404


def test_allowed_networks_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "metrics_allowed_networks", "172.18.0.0/16")
    assert _client("172.18.0.5").get("/metrics").status_code == 200
    assert _client("127.0.0.1").get("/metrics").status_code == 404
