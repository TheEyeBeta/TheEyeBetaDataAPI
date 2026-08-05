"""Route-level tests for admin account create/delete: scope enforcement + wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.dependencies.services import get_account_service
from app.auth.account_approval import require_account_approval
from app.domain.errors import NotFoundAppError
from app.main import app


def _issue_service_token(client: TestClient, username: str, password: str, scopes: list[str]) -> str:
    response = client.post(
        "/api/v1/auth/service-token",
        auth=(username, password),
        json={"requested_scopes": scopes},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


class _FakeAccountService:
    """Records calls; delete_account still runs the real approval gate."""

    def __init__(self) -> None:
        self.create_calls: list[dict] = []
        self.delete_calls: list[dict] = []

    def create_account(self, **kwargs) -> dict:
        self.create_calls.append(kwargs)
        return {
            "user_uuid": "11111111-1111-1111-1111-111111111111",
            "email": kwargs["email"],
            "display_name": kwargs["display_name"],
            "organization": kwargs["organization"],
            "plan": kwargs["plan"],
            "is_active": True,
            "created_at": None,
        }

    def delete_account(self, **kwargs) -> dict:
        self.delete_calls.append(kwargs)
        require_account_approval(kwargs["approval_code"])
        if kwargs["user_uuid"] == "00000000-0000-0000-0000-000000000000":
            raise NotFoundAppError("not found")
        return {"user_uuid": kwargs["user_uuid"], "email": "gone@example.com", "is_active": False}


def _client_with_fake_service() -> tuple[TestClient, _FakeAccountService]:
    fake = _FakeAccountService()
    app.dependency_overrides[get_account_service] = lambda: fake
    return TestClient(app), fake


def test_admin_write_scope_can_create_account() -> None:
    client, fake = _client_with_fake_service()
    try:
        token = _issue_service_token(client, "admin-tool", "admin-tool-secret-which-is-24chars", ["admin:write"])
        response = client.post(
            "/api/v1/admin/accounts",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "new.user@example.com", "plan": "free"},
        )
        assert response.status_code == 201
        assert response.json()["email"] == "new.user@example.com"
        assert len(fake.create_calls) == 1
    finally:
        app.dependency_overrides.clear()


def test_admin_read_only_scope_cannot_create_account() -> None:
    client, fake = _client_with_fake_service()
    try:
        token = _issue_service_token(client, "admin-tool", "admin-tool-secret-which-is-24chars", ["admin:read"])
        response = client.post(
            "/api/v1/admin/accounts",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "new.user@example.com", "plan": "free"},
        )
        assert response.status_code == 403
        assert fake.create_calls == []
    finally:
        app.dependency_overrides.clear()


def test_admin_read_only_scope_cannot_delete_account() -> None:
    client, fake = _client_with_fake_service()
    try:
        token = _issue_service_token(client, "admin-tool", "admin-tool-secret-which-is-24chars", ["admin:read"])
        response = client.request(
            "DELETE",
            "/api/v1/admin/accounts/11111111-1111-1111-1111-111111111111",
            headers={"Authorization": f"Bearer {token}"},
            json={"approval_code": "whatever"},
        )
        assert response.status_code == 403
        assert fake.delete_calls == []
    finally:
        app.dependency_overrides.clear()


def test_delete_account_rejects_wrong_approval_code_over_http() -> None:
    client, fake = _client_with_fake_service()
    try:
        token = _issue_service_token(client, "admin-tool", "admin-tool-secret-which-is-24chars", ["admin:write"])
        response = client.request(
            "DELETE",
            "/api/v1/admin/accounts/11111111-1111-1111-1111-111111111111",
            headers={"Authorization": f"Bearer {token}"},
            json={"approval_code": "wrong-code"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "APPROVAL_REQUIRED"
    finally:
        app.dependency_overrides.clear()


def test_delete_account_not_found_maps_to_404() -> None:
    from app.core.config import settings

    original = settings.admin_account_approval_code
    settings.admin_account_approval_code = "correct-horse-battery-staple"
    client, fake = _client_with_fake_service()
    try:
        token = _issue_service_token(client, "admin-tool", "admin-tool-secret-which-is-24chars", ["admin:write"])
        response = client.request(
            "DELETE",
            "/api/v1/admin/accounts/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {token}"},
            json={"approval_code": "correct-horse-battery-staple"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        settings.admin_account_approval_code = original
