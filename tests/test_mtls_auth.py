"""Tests for optional mTLS service authentication flow."""

from fastapi.testclient import TestClient

from app.api.dependencies.services import get_readonly_data_repository
from app.core.config import settings
from app.main import app
from app.schemas.data import DataTableInfo


class _FakeDataRepository:
    def list_tables(self) -> list[DataTableInfo]:
        return [DataTableInfo(name="instruments", table_type="BASE TABLE")]


def test_mtls_service_auth_allows_scoped_data_read(monkeypatch) -> None:
    monkeypatch.setattr(settings, "service_mtls_enabled", True)
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "service_mtls_subjects_json", '{"trade-engine":["CN=trade-engine"]}')

    app.dependency_overrides[get_readonly_data_repository] = lambda: _FakeDataRepository()
    client = TestClient(app)
    response = client.get(
        "/api/v1/data/tables",
        headers={
            "X-Service-Client-Id": "trade-engine",
            "X-Client-Cert-Subject": "CN=trade-engine",
        },
    )
    assert response.status_code == 200
    assert response.json()["tables"][0]["name"] == "instruments"
    app.dependency_overrides.clear()


def test_mtls_service_auth_rejects_wrong_subject(monkeypatch) -> None:
    monkeypatch.setattr(settings, "service_mtls_enabled", True)
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "service_mtls_subjects_json", '{"trade-engine":["CN=trade-engine"]}')

    client = TestClient(app)
    response = client.get(
        "/api/v1/data/tables",
        headers={
            "X-Service-Client-Id": "trade-engine",
            "X-Client-Cert-Subject": "CN=wrong-client",
        },
    )
    assert response.status_code == 401
