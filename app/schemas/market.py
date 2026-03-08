"""Market/symbol/analytics/trades/admin contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.context import TickerSnapshotResponse, TickerSummaryResponse


class MarketQuotesResponse(BaseModel):
    """Quotes response for one or more symbols."""

    quotes: list[TickerSnapshotResponse]


class SymbolSearchResponse(BaseModel):
    """Search results for symbol lookup."""

    results: list[TickerSummaryResponse]


class AnalyticsSnapshotResponse(BaseModel):
    """Analytics snapshot response."""

    snapshot: TickerSnapshotResponse | None = None


class SignalRecordResponse(BaseModel):
    """Signal record response."""

    ticker: str
    strategy_name: str | None = None
    signal: str
    confidence: float | None = None
    entry_price: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    timestamp: datetime | None = None


class SignalsLatestResponse(BaseModel):
    """Latest signals response."""

    signals: list[SignalRecordResponse]


class PortfolioValuationResponse(BaseModel):
    """Portfolio valuation summary."""

    valuation_date: date | None = None
    total_value: float | None = None
    cash_balance: float | None = None
    positions_value: float | None = None
    total_cost_basis: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float | None = None
    currency_code: str | None = None
    created_at: datetime | None = None


class PortfolioPositionResponse(BaseModel):
    """Portfolio position response."""

    ticker: str
    company_name: str
    quantity: float
    average_cost: float | None = None
    last_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    last_updated: datetime | None = None


class PortfolioStateResponse(BaseModel):
    """Portfolio state response with effective owner context."""

    owner_subject: str
    valuation: PortfolioValuationResponse | None = None
    positions: list[PortfolioPositionResponse]


class PlaceOrderRequest(BaseModel):
    """Trade order request contract."""

    symbol: str = Field(min_length=1, max_length=16)
    side: str = Field(pattern="^(buy|sell)$")
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)


class PlaceOrderResponse(BaseModel):
    """Trade order acceptance response."""

    status: str
    order_ref: str
    idempotency_key: str
    symbol: str
    side: str
    quantity: float
    executed_price: float
    total_cost: float
    accepted_at: datetime | None = None
    idempotent_replay: bool = False


class GenericStatusResponse(BaseModel):
    """Generic status response."""

    status: str


class AdminAuditEventResponse(BaseModel):
    """Admin audit event response."""

    event_id: str
    event_type: str | None = None
    event_category: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    severity: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime | None = None


class AdminAuditEventsResponse(BaseModel):
    """Admin audit events list response."""

    events: list[AdminAuditEventResponse]


class InternalRebuildRequest(BaseModel):
    """Internal rebuild command request."""

    ticker: str | None = Field(default=None, max_length=16)
    force: bool = False
    reason: str | None = Field(default=None, max_length=300)


class InternalJobResponse(BaseModel):
    """Internal job command response."""

    status: str
    command_id: str
    command_type: str
    created_at: datetime | None = None
