"""Advisor context response contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TickerSummaryResponse(BaseModel):
    """Public ticker summary response."""

    ticker: str
    company_name: str


class NewsItemResponse(BaseModel):
    """Public market news response."""

    headline: str
    source: str | None = None
    category: str | None = None
    published_at: datetime | None = None


class TickerSnapshotResponse(BaseModel):
    """Ticker snapshot response contract."""

    ticker: str
    company_name: str
    last_price: float | None = None
    price_change_pct: float | None = None
    rsi_14: float | None = None
    sma_10: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    updated_at: datetime | None = None


class AdvisorContextResponse(BaseModel):
    """Advisor context payload returned to clients."""

    tickers: list[TickerSummaryResponse]
    news: list[NewsItemResponse]
    ticker_snapshot: TickerSnapshotResponse | None = None
