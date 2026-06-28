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


# ── Reference ────────────────────────────────────────────────────────────────

class CountryResponse(BaseModel):
    country_code: str
    country_name: str
    default_timezone: str | None = None


class CountriesResponse(BaseModel):
    countries: list[CountryResponse]


class CurrencyResponse(BaseModel):
    currency_code: str
    currency_name: str
    symbol: str | None = None


class CurrenciesResponse(BaseModel):
    currencies: list[CurrencyResponse]


class ExchangeResponse(BaseModel):
    exchange_id: int
    name: str
    mic_code: str | None = None
    country_code: str | None = None
    timezone: str | None = None


class ExchangesResponse(BaseModel):
    exchanges: list[ExchangeResponse]


class SectorResponse(BaseModel):
    sector_id: int
    sector_name: str


class SectorsResponse(BaseModel):
    sectors: list[SectorResponse]


class IndustryResponse(BaseModel):
    industry_id: int
    sector_id: int
    industry_name: str


class IndustriesResponse(BaseModel):
    industries: list[IndustryResponse]


class TradingCalendarDayResponse(BaseModel):
    calendar_date: date
    is_trading_day: bool
    market_name: str | None = None
    holiday_name: str | None = None
    notes: str | None = None


class TradingCalendarResponse(BaseModel):
    days: list[TradingCalendarDayResponse]


# ── Ticker detail ─────────────────────────────────────────────────────────────

class TickerIdentifierResponse(BaseModel):
    id_type: str
    id_value: str


class TickerDetailResponse(BaseModel):
    ticker: str
    company_name: str
    asset_type: str | None = None
    country_code: str | None = None
    timezone: str | None = None
    currency_code: str | None = None
    is_active: bool
    sector_id: int | None = None
    industry_id: int | None = None
    website: str | None = None
    description: str | None = None
    founded_year: int | None = None
    employees: int | None = None
    identifiers: list[TickerIdentifierResponse] = Field(default_factory=list)


class TickerListResponse(BaseModel):
    tickers: list[TickerDetailResponse]
    total: int


class PriceDayResponse(BaseModel):
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adj_close: float | None = None
    volume: float | None = None
    vwap: float | None = None


class PriceHistoryResponse(BaseModel):
    ticker: str
    prices: list[PriceDayResponse]


class CorporateActionResponse(BaseModel):
    action_id: int
    action_date: date | None = None
    action_type: str
    split_ratio: float | None = None
    dividend_amount: float | None = None
    notes: str | None = None


class CorporateActionsResponse(BaseModel):
    ticker: str
    actions: list[CorporateActionResponse]


class CompanyFundamentalsResponse(BaseModel):
    ticker: str
    sector: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    ceo: str | None = None
    full_time_employees: int | None = None
    headquarters_city: str | None = None
    headquarters_state: str | None = None
    headquarters_country: str | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    shares_outstanding: float | None = None
    float_shares: float | None = None
    pe_ratio: float | None = None
    pe_forward: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    ev_to_ebitda: float | None = None
    ev_to_revenue: float | None = None
    dividend_rate: float | None = None
    dividend_yield: float | None = None
    ex_dividend_date: date | None = None
    payout_ratio: float | None = None
    currency: str | None = None
    source: str | None = None
    last_updated: datetime | None = None


# ── Financial statements ──────────────────────────────────────────────────────

class IncomeStatementResponse(BaseModel):
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    ebit: float | None = None
    ebitda: float | None = None
    interest_expense: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None


class IncomeStatementsResponse(BaseModel):
    ticker: str
    statements: list[IncomeStatementResponse]


class BalanceSheetResponse(BaseModel):
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    shares_outstanding: float | None = None


class BalanceSheetsResponse(BaseModel):
    ticker: str
    statements: list[BalanceSheetResponse]


class CashFlowResponse(BaseModel):
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    ocf: float | None = None
    capex: float | None = None
    fcf: float | None = None
    working_cap_change: float | None = None
    stock_based_comp: float | None = None


class CashFlowsResponse(BaseModel):
    ticker: str
    statements: list[CashFlowResponse]


class QualityMetricResponse(BaseModel):
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    nopat: float | None = None
    invested_capital: float | None = None
    roic: float | None = None
    roe: float | None = None
    roa: float | None = None
    roce: float | None = None
    wacc: float | None = None
    cost_of_equity: float | None = None
    cost_of_debt: float | None = None
    roic_wacc_spread: float | None = None
    debt_equity: float | None = None
    net_debt_ebitda: float | None = None
    interest_coverage: float | None = None
    ocf: float | None = None
    fcf: float | None = None


class QualityMetricsResponse(BaseModel):
    ticker: str
    metrics: list[QualityMetricResponse]


# ── Indicators ────────────────────────────────────────────────────────────────

class TechnicalDayResponse(BaseModel):
    date: date
    sma_10: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_10: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    roc_10: float | None = None
    roc_20: float | None = None
    golden_cross_sma: bool | None = None
    death_cross_sma: bool | None = None


class TechnicalIndicatorsResponse(BaseModel):
    ticker: str
    indicators: list[TechnicalDayResponse]


class RiskDayResponse(BaseModel):
    date: date
    atr_14: float | None = None
    hist_vol_20d: float | None = None
    hist_vol_60d: float | None = None
    beta_sp500_60d: float | None = None
    worst_drop_1d: float | None = None
    worst_drop_5d: float | None = None
    worst_drop_10d: float | None = None
    max_drawdown_1y: float | None = None
    max_drawdown_2y: float | None = None
    sharpe_60d: float | None = None
    sortino_60d: float | None = None
    calmar_1y: float | None = None


class RiskIndicatorsResponse(BaseModel):
    ticker: str
    indicators: list[RiskDayResponse]


class ValuationDayResponse(BaseModel):
    date: date
    market_cap: float | None = None
    enterprise_value: float | None = None
    pe_ttm: float | None = None
    forward_pe: float | None = None
    ps_ttm: float | None = None
    pb: float | None = None
    ev_ebitda: float | None = None
    ev_ebit: float | None = None
    ev_fcf: float | None = None
    earnings_yield: float | None = None
    fcf_yield: float | None = None
    pct_chg_1w: float | None = None
    pct_chg_3m: float | None = None
    pct_chg_6m: float | None = None
    pct_chg_9m: float | None = None
    pct_chg_ytd: float | None = None
    pct_chg_1y: float | None = None


class ValuationIndicatorsResponse(BaseModel):
    ticker: str
    indicators: list[ValuationDayResponse]


class ReturnsDayResponse(BaseModel):
    date: date
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_9m: float | None = None
    ret_ytd: float | None = None
    ret_1y: float | None = None
    price_field: str | None = None
    computed_at: datetime | None = None


class ReturnsSnapshotResponse(BaseModel):
    ticker: str
    returns: list[ReturnsDayResponse]


# ── News ──────────────────────────────────────────────────────────────────────

class TickerNewsItemResponse(BaseModel):
    news_id: int
    source: str | None = None
    title: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None


class TickerNewsResponse(BaseModel):
    ticker: str
    news: list[TickerNewsItemResponse]


class MarketNewsItemResponse(BaseModel):
    id: int
    provider: str | None = None
    url: str | None = None
    headline: str | None = None
    summary: str | None = None
    source: str | None = None
    category: str | None = None
    published_at: datetime | None = None


class MarketNewsResponse(BaseModel):
    news: list[MarketNewsItemResponse]


# ── Admin-only ────────────────────────────────────────────────────────────────

class EtlJobStateResponse(BaseModel):
    job_name: str
    last_run_at: datetime | None = None
    last_successful_date: date | None = None
    status: str | None = None
    last_error: str | None = None


class EtlJobStatesResponse(BaseModel):
    jobs: list[EtlJobStateResponse]


class EngineStatusEntryResponse(BaseModel):
    key: str
    value: str | None = None
    updated_at: datetime | None = None


class EngineStatusResponse(BaseModel):
    entries: list[EngineStatusEntryResponse]


class PriceTickResponse(BaseModel):
    tick_id: int
    ts: datetime | None = None
    price: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    source: str | None = None


class PriceTicksResponse(BaseModel):
    ticker: str
    ticks: list[PriceTickResponse]


class WorkerHeartbeatResponse(BaseModel):
    worker_id: str
    worker_type: str | None = None
    status: str
    last_heartbeat: datetime | None = None
    started_at: datetime | None = None
    restart_count: int | None = None
    last_error: str | None = None


class WorkerHeartbeatsResponse(BaseModel):
    workers: list[WorkerHeartbeatResponse]


# ── Sector / universe ─────────────────────────────────────────────────────────

class SectorDailyEntryResponse(BaseModel):
    sector: str
    as_of_date: date
    n_instruments: int
    avg_return_1d: float | None = None
    avg_return_5d: float | None = None
    avg_return_30d: float | None = None
    median_rsi_14: float | None = None
    pct_above_sma_50: float | None = None
    pct_above_sma_200: float | None = None
    rel_strength_spx_30d: float | None = None
    rotation_rank: int | None = None
    volume_ratio_20d: float | None = None
    top_contributors: list[Any] = Field(default_factory=list)


class SectorDailyResponse(BaseModel):
    sectors: list[SectorDailyEntryResponse]


class UniverseCapEntryResponse(BaseModel):
    symbol: str
    as_of_date: date
    market_cap: float
    close_price: float | None = None
    shares_outstanding: int | None = None
    source: str | None = None


class UniverseActiveResponse(BaseModel):
    as_of_date: date | None = None
    entries: list[UniverseCapEntryResponse]


class CapEventResponse(BaseModel):
    id: int
    trade_date: date
    symbol: str
    event_type: str
    market_cap: float | None = None
    prior_market_cap: float | None = None
    action_required: str | None = None
    universe_updated: bool


class CapEventsResponse(BaseModel):
    events: list[CapEventResponse]
