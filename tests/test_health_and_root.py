"""Smoke tests for root and health endpoints."""

from fastapi.testclient import TestClient

from app.main import app


class _DummySession:
    closed = False

    def close(self) -> None:
        self.closed = True


def test_root_endpoint_has_basic_metadata() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "TheEyeBetaDataAPI"
    assert payload["status"] == "ok"
    assert "version" in payload


def test_health_returns_healthy_when_db_ok(monkeypatch) -> None:
    client = TestClient(app)
    dummy = _DummySession()

    monkeypatch.setattr("app.api.routes.health.get_db_session", lambda: dummy)
    monkeypatch.setattr("app.api.routes.health.db_health", lambda _session: True)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": True}
    assert dummy.closed is True


def test_health_returns_degraded_when_db_unhealthy(monkeypatch) -> None:
    client = TestClient(app)
    dummy = _DummySession()

    monkeypatch.setattr("app.api.routes.health.get_db_session", lambda: dummy)
    monkeypatch.setattr("app.api.routes.health.db_health", lambda _session: False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": False}
