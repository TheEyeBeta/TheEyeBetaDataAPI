"""Advisor answer fallback when OpenAI is not configured."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.schemas.chat import ChatResponse
from app.services.ai_service import answer_question


@pytest.fixture(autouse=True)
def _no_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")


def test_fallback_with_snapshot_returns_a_string_answer() -> None:
    answer = answer_question(
        question="What is the RSI for AAPL?",
        ticker="AAPL",
        context={"ticker_snapshot": {"ticker": "AAPL", "last_price": 227.1, "rsi_14": 55.2, "price_change_pct": 0.4}},
    )
    assert isinstance(answer, str)
    assert "AAPL" in answer and "rsi_14=55.2" in answer
    # The route wraps this in ChatResponse; a non-string answer would be a 500.
    assert ChatResponse(answer=answer).answer == answer


def test_fallback_without_snapshot_explains_configuration() -> None:
    answer = answer_question(question="How is the market?", ticker=None, context={})
    assert isinstance(answer, str)
    assert "OPENAI_API_KEY" in answer
