"""Unit tests for MarketDataService.get_price_history's adjust= handling."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.models import CorporateAction, PriceDay
from app.services.market_data_service import MarketDataService


class _FakeRepository:
    def __init__(self, prices: list[PriceDay], actions: list[CorporateAction]) -> None:
        self._prices = prices
        self._actions = actions
        self.corporate_actions_requested = False

    def get_price_history(self, *, ticker, start, end, limit):  # noqa: ANN001, ARG002
        return self._prices

    def get_corporate_actions(self, *, ticker, limit):  # noqa: ANN001, ARG002
        self.corporate_actions_requested = True
        return self._actions


def _bar(close: float, adj_close: float | None) -> PriceDay:
    return PriceDay(
        date=date(2026, 1, 2),
        open=close,
        high=close,
        low=close,
        close=close,
        adj_close=adj_close,
        volume=1000.0,
        vwap=close,
    )


def test_adjust_none_returns_raw_bars_and_no_corporate_actions() -> None:
    repo = _FakeRepository(prices=[_bar(100.0, 90.0)], actions=[])
    service = MarketDataService(repository=repo)

    result = service.get_price_history(ticker="aapl", start=None, end=None, limit=252, adjust="none")

    assert result.adjustment == "none"
    assert result.corporate_actions == []
    assert result.prices[0].close == 100.0
    assert repo.corporate_actions_requested is False


def test_adjust_splits_dividends_rescales_ohlc_and_includes_actions() -> None:
    action = CorporateAction(
        action_id=1,
        action_date=date(2026, 1, 1),
        action_type="split",
        split_ratio=2.0,
        dividend_amount=None,
        notes=None,
    )
    repo = _FakeRepository(prices=[_bar(100.0, 90.0)], actions=[action])
    service = MarketDataService(repository=repo)

    result = service.get_price_history(
        ticker="aapl", start=None, end=None, limit=252, adjust="splits_dividends"
    )

    assert result.adjustment == "splits_dividends"
    bar = result.prices[0]
    assert bar.close == 90.0
    assert bar.open == pytest.approx(90.0)
    assert bar.high == pytest.approx(90.0)
    assert bar.low == pytest.approx(90.0)
    assert len(result.corporate_actions) == 1
    assert result.corporate_actions[0].action_type == "split"
    assert repo.corporate_actions_requested is True


def test_adjust_splits_dividends_leaves_bar_unchanged_when_adj_close_missing() -> None:
    repo = _FakeRepository(prices=[_bar(100.0, None)], actions=[])
    service = MarketDataService(repository=repo)

    result = service.get_price_history(
        ticker="aapl", start=None, end=None, limit=252, adjust="splits_dividends"
    )

    assert result.prices[0].close == 100.0
