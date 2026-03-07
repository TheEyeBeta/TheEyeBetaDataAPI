"""Tests for auth, context, and chat routes."""

from fastapi.testclient import TestClient

from app.main import app


class _DummySession:
    closed = False

    def close(self) -> None:
        self.closed = True


def test_issue_token_requires_api_key() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/auth/token", json={"subject": "svc-client", "expires_minutes": 30})

    assert response.status_code == 401


def test_issue_token_with_api_key_succeeds() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/token",
        headers={"X-API-Key": "test-api-key-which-is-definitely-24chars"},
        json={"subject": "svc-client", "expires_minutes": 30},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_minutes"] == 30
    assert isinstance(payload["access_token"], str) and payload["access_token"]


def test_context_requires_auth() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/context")

    assert response.status_code == 401


def test_context_returns_payload_for_api_key(monkeypatch) -> None:
    client = TestClient(app)
    dummy = _DummySession()

    monkeypatch.setattr("app.api.routes.context.get_db_session", lambda: dummy)
    monkeypatch.setattr("app.api.routes.context.fetch_active_tickers", lambda _s, limit: [{"ticker": "AAPL"}])
    monkeypatch.setattr("app.api.routes.context.fetch_recent_news", lambda _s, limit: [{"headline": "Fed update"}])
    monkeypatch.setattr(
        "app.api.routes.context.fetch_latest_snapshot",
        lambda _s, ticker: {"ticker": ticker, "last_price": 250.0},
    )

    response = client.get(
        "/api/v1/context?ticker=AAPL&ticker_limit=5&news_limit=2",
        headers={"X-API-Key": "test-api-key-which-is-definitely-24chars"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == [{"ticker": "AAPL"}]
    assert payload["news"] == [{"headline": "Fed update"}]
    assert payload["ticker_snapshot"]["ticker"] == "AAPL"
    assert dummy.closed is True


def test_chat_returns_mocked_answer(monkeypatch) -> None:
    client = TestClient(app)
    dummy = _DummySession()

    monkeypatch.setattr("app.api.routes.chat.get_db_session", lambda: dummy)
    monkeypatch.setattr("app.api.routes.chat.answer_question", lambda session, question, ticker: ("Mock answer", 3))

    response = client.post(
        "/api/v1/chat",
        headers={"X-API-Key": "test-api-key-which-is-definitely-24chars"},
        json={"question": "What happened today?", "ticker": "AAPL"},
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "Mock answer", "used_ticker": "AAPL", "context_rows": 3}
    assert dummy.closed is True
