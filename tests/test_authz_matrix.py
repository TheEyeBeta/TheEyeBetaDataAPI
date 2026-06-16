"""Authorization matrix tests across consumer capabilities."""

from fastapi.testclient import TestClient

from app.api.dependencies.services import get_admin_service, get_market_data_service
from app.main import app
from app.schemas.market import AdminAuditEventResponse, AdminAuditEventsResponse, MarketQuotesResponse


class _FakeMarketDataService:
    def get_quotes(self, symbols: list[str]) -> MarketQuotesResponse:
        from app.schemas.context import TickerSnapshotResponse

        return MarketQuotesResponse(
            quotes=[
                TickerSnapshotResponse(
                    ticker=symbol,
                    company_name=f"{symbol} Inc.",
                    last_price=100.0,
                )
                for symbol in symbols
            ]
        )


class _FakeAdminService:
    def get_audit_events(self, *, limit: int, category: str | None) -> AdminAuditEventsResponse:  # noqa: ARG002
        return AdminAuditEventsResponse(
            events=[
                AdminAuditEventResponse(
                    event_id="evt-1",
                    event_type="command",
                    event_category="operations",
                    source_type="api",
                    source_id="test",
                    severity="info",
                )
            ]
        )


def _issue_service_token(client: TestClient, username: str, password: str, scopes: list[str]) -> str:
    response = client.post(
        "/api/v1/auth/service-token",
        auth=(username, password),
        json={"requested_scopes": scopes},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_vi_service_can_read_market_but_cannot_write_trades() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeMarketDataService()
    client = TestClient(app)
    token = _issue_service_token(client, "vi-app", "vi-app-secret-which-is-24chars!!", ["market:read"])

    quotes_response = client.get(
        "/api/v1/market-data/quotes?symbols=AAPL,MSFT",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert quotes_response.status_code == 200
    assert len(quotes_response.json()["quotes"]) == 2

    trade_response = client.post(
        "/api/v1/trades/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-vi-1",
        },
        json={"symbol": "AAPL", "side": "buy", "quantity": 1},
    )
    assert trade_response.status_code == 404
    app.dependency_overrides.clear()


def test_trade_engine_write_route_is_not_part_of_data_api() -> None:
    client = TestClient(app)
    token = _issue_service_token(
        client,
        "trade-engine",
        "trade-engine-secret-which-is-24chars",
        ["portfolio:read"],
    )
    trade_response = client.post(
        "/api/v1/trades/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "idem-trade-1",
        },
        json={"symbol": "AAPL", "side": "buy", "quantity": 2},
    )
    assert trade_response.status_code == 404


def test_admin_wildcard_scope_can_access_admin_read_route() -> None:
    app.dependency_overrides[get_admin_service] = lambda: _FakeAdminService()
    client = TestClient(app)
    token = _issue_service_token(
        client,
        "admin-tool",
        "admin-tool-secret-which-is-24chars",
        ["admin:read"],
    )
    response = client.get(
        "/api/v1/admin/audit-events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert len(response.json()["events"]) == 1
    app.dependency_overrides.clear()
