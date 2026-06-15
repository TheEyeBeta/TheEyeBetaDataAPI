"""Smoke tests for root and health endpoints."""

from fastapi.testclient import TestClient

from app.api.dependencies.services import get_health_service
from app.main import app
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService


class _FakeRepository:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def check_health(self) -> bool:
        return self.ok


class _FakeHealthService:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def get_health(self) -> HealthResponse:
        return HealthResponse(status="healthy", database=self.ok)


def test_root_endpoint_has_basic_metadata() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "TheEyeBetaDataAPI"
    assert payload["status"] == "ok"
    assert "version" in payload


def test_health_returns_healthy_when_db_ok() -> None:
    app.dependency_overrides[get_health_service] = lambda: _FakeHealthService(ok=True)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": True, "redis": None}
    app.dependency_overrides.clear()


def test_health_keeps_api_healthy_when_db_unhealthy() -> None:
    app.dependency_overrides[get_health_service] = lambda: _FakeHealthService(ok=False)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": False, "redis": None}
    app.dependency_overrides.clear()


def test_health_service_reports_api_healthy_when_database_unavailable() -> None:
    payload = HealthService(_FakeRepository(ok=False)).get_health()

    assert payload.status == "healthy"
    assert payload.database is False
