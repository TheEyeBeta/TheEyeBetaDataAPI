"""Tests for optional mTLS service authentication flow."""

from fastapi.testclient import TestClient

from app.api.dependencies.services import get_trades_service
from app.core.config import settings
from app.main import app
from app.schemas.market import PlaceOrderResponse


class _FakeTradesService:
    def place_order(self, **kwargs) -> PlaceOrderResponse:  # noqa: ANN003
        return PlaceOrderResponse(
            status="accepted",
            order_ref="paper-trade-123",
            idempotency_key=str(kwargs["idempotency_key"]),
            symbol=str(kwargs["request"].symbol).upper(),
            side=str(kwargs["request"].side).lower(),
            quantity=float(kwargs["request"].quantity),
            executed_price=100.0,
            total_cost=100.0 * float(kwargs["request"].quantity),
            accepted_at=None,
            idempotent_replay=False,
        )


def test_mtls_service_auth_allows_scoped_trade_write(monkeypatch) -> None:
    monkeypatch.setattr(settings, "service_mtls_enabled", True)
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "service_mtls_subjects_json", '{"trade-engine":["CN=trade-engine"]}')

    app.dependency_overrides[get_trades_service] = lambda: _FakeTradesService()
    client = TestClient(app)
    response = client.post(
        "/api/v1/trades/orders",
        headers={
            "X-Service-Client-Id": "trade-engine",
            "X-Client-Cert-Subject": "CN=trade-engine",
            "Idempotency-Key": "idem-mtls-1",
        },
        json={"symbol": "AAPL", "side": "buy", "quantity": 1},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    app.dependency_overrides.clear()


def test_mtls_service_auth_rejects_wrong_subject(monkeypatch) -> None:
    monkeypatch.setattr(settings, "service_mtls_enabled", True)
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "service_mtls_subjects_json", '{"trade-engine":["CN=trade-engine"]}')

    client = TestClient(app)
    response = client.post(
        "/api/v1/trades/orders",
        headers={
            "X-Service-Client-Id": "trade-engine",
            "X-Client-Cert-Subject": "CN=wrong-client",
            "Idempotency-Key": "idem-mtls-2",
        },
        json={"symbol": "AAPL", "side": "buy", "quantity": 1},
    )
    assert response.status_code == 401
