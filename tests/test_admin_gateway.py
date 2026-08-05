"""Gateway manifest and delegated-token regression tests."""

from app.api.routes.admin_gateway import is_allowed_admin_route
from app.auth.tokens import create_delegated_access_token, decode_access_token
from app.auth.scopes import LENS_DELEGATED_READ_SCOPES


def test_admin_gateway_allows_manifested_sql_execute() -> None:
    assert is_allowed_admin_route("sql/execute", "POST")
    assert not is_allowed_admin_route("sql/export", "POST")


def test_admin_gateway_rejects_unlisted_and_path_traversal_routes() -> None:
    assert not is_allowed_admin_route("secrets/export", "GET")
    assert not is_allowed_admin_route("sql/../secrets", "POST")
    assert not is_allowed_admin_route("sql-unsafe/execute", "POST")


def test_delegated_token_preserves_actor_subject_and_tenant_binding() -> None:
    token = create_delegated_access_token(
        subject="lens-user-123",
        actor_client_id="lens-backend",
        tenant_id="f6b70d15-2dfd-46b7-a217-3af37ed2b7dc",
        product="LENS",
        scopes=["market:read"],
        policy_version=1,
    )
    principal = decode_access_token(token)

    assert principal.delegated
    assert principal.subject == "lens-user-123"
    assert principal.client_id == "lens-backend"
    assert principal.tenant_id == "f6b70d15-2dfd-46b7-a217-3af37ed2b7dc"
    assert principal.product == "LENS"
    assert principal.policy_version == 1


def test_lens_delegation_never_includes_administrative_or_portfolio_scopes() -> None:
    assert "admin:read" not in LENS_DELEGATED_READ_SCOPES
    assert "admin:*" not in LENS_DELEGATED_READ_SCOPES
    assert "portfolio:read" not in LENS_DELEGATED_READ_SCOPES
