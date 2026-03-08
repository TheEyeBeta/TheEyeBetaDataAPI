"""Domain data models independent from transport and persistence layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class TickerSummary:
    """Public symbol summary."""

    ticker: str
    company_name: str


@dataclass(frozen=True)
class MarketNewsItem:
    """Public market news item."""

    headline: str
    source: str | None
    category: str | None
    published_at: datetime | None


@dataclass(frozen=True)
class TickerSnapshot:
    """Domain-level latest ticker snapshot."""

    ticker: str
    company_name: str
    last_price: float | None
    price_change_pct: float | None
    rsi_14: float | None
    sma_10: float | None
    sma_50: float | None
    sma_200: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    updated_at: datetime | None


@dataclass(frozen=True)
class AdvisorContext:
    """Context payload used by advisor/chat use cases."""

    tickers: list[TickerSummary]
    news: list[MarketNewsItem]
    ticker_snapshot: TickerSnapshot | None


@dataclass(frozen=True)
class SignalRecord:
    """Public signal record."""

    ticker: str
    strategy_name: str | None
    signal: str
    confidence: float | None
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
    timestamp: datetime | None


@dataclass(frozen=True)
class PortfolioPosition:
    """Portfolio position snapshot."""

    ticker: str
    company_name: str
    quantity: float
    average_cost: float | None
    last_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    last_updated: datetime | None


@dataclass(frozen=True)
class PortfolioValuation:
    """Portfolio valuation snapshot."""

    valuation_date: date | None
    total_value: float | None
    cash_balance: float | None
    positions_value: float | None
    total_cost_basis: float | None
    unrealized_pnl: float | None
    realized_pnl: float | None
    currency_code: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class TradeOrderResult:
    """Result of a trade order command."""

    order_ref: str
    status: str
    idempotency_key: str
    symbol: str
    side: str
    quantity: float
    executed_price: float
    total_cost: float
    accepted_at: datetime | None
    idempotent_replay: bool


@dataclass(frozen=True)
class AdminAuditEvent:
    """Admin-visible audit event."""

    event_id: str
    event_type: str | None
    event_category: str | None
    source_type: str | None
    source_id: str | None
    target_type: str | None
    target_id: str | None
    severity: str | None
    payload: dict[str, Any] | None
    created_at: datetime | None


@dataclass(frozen=True)
class InternalJobReceipt:
    """Internal job enqueue receipt."""

    command_id: str
    status: str
    command_type: str
    created_at: datetime | None
