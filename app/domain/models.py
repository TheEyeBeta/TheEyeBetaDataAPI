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


# ── Reference / lookup ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Country:
    country_code: str
    country_name: str
    default_timezone: str | None


@dataclass(frozen=True)
class Currency:
    currency_code: str
    currency_name: str
    symbol: str | None


@dataclass(frozen=True)
class Exchange:
    exchange_id: int
    name: str
    mic_code: str | None
    country_code: str | None
    timezone: str | None


@dataclass(frozen=True)
class Sector:
    sector_id: int
    sector_name: str


@dataclass(frozen=True)
class Industry:
    industry_id: int
    sector_id: int
    industry_name: str


@dataclass(frozen=True)
class TradingCalendarDay:
    calendar_date: date
    is_trading_day: bool
    market_name: str | None
    holiday_name: str | None
    notes: str | None


# ── Ticker detail ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TickerDetail:
    ticker: str
    company_name: str
    asset_type: str | None
    country_code: str | None
    timezone: str | None
    currency_code: str | None
    is_active: bool
    sector_id: int | None
    industry_id: int | None
    website: str | None
    description: str | None
    founded_year: int | None
    employees: int | None
    identifiers: list[dict[str, Any]]


@dataclass(frozen=True)
class PriceDay:
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None
    volume: float | None
    vwap: float | None


@dataclass(frozen=True)
class CorporateAction:
    action_id: int
    action_date: date | None
    action_type: str
    split_ratio: float | None
    dividend_amount: float | None
    notes: str | None


@dataclass(frozen=True)
class CompanyFundamentals:
    sector: str | None
    industry: str | None
    sub_industry: str | None
    ceo: str | None
    full_time_employees: int | None
    headquarters_city: str | None
    headquarters_state: str | None
    headquarters_country: str | None
    market_cap: float | None
    enterprise_value: float | None
    shares_outstanding: float | None
    float_shares: float | None
    pe_ratio: float | None
    pe_forward: float | None
    peg_ratio: float | None
    price_to_book: float | None
    price_to_sales: float | None
    ev_to_ebitda: float | None
    ev_to_revenue: float | None
    dividend_rate: float | None
    dividend_yield: float | None
    ex_dividend_date: date | None
    payout_ratio: float | None
    currency: str | None
    source: str | None
    last_updated: datetime | None


# ── Financial statements ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class IncomeStatementQ:
    period_end: date | None
    fiscal_year: int | None
    fiscal_quarter: int | None
    revenue: float | None
    gross_profit: float | None
    ebit: float | None
    ebitda: float | None
    interest_expense: float | None
    net_income: float | None
    eps_basic: float | None
    eps_diluted: float | None


@dataclass(frozen=True)
class BalanceSheetQ:
    period_end: date | None
    fiscal_year: int | None
    fiscal_quarter: int | None
    total_assets: float | None
    total_liabilities: float | None
    total_equity: float | None
    total_debt: float | None
    cash_and_equivalents: float | None
    shares_outstanding: float | None


@dataclass(frozen=True)
class CashFlowQ:
    period_end: date | None
    fiscal_year: int | None
    fiscal_quarter: int | None
    ocf: float | None
    capex: float | None
    fcf: float | None
    working_cap_change: float | None
    stock_based_comp: float | None


@dataclass(frozen=True)
class QualityQ:
    period_end: date | None
    fiscal_year: int | None
    fiscal_quarter: int | None
    nopat: float | None
    invested_capital: float | None
    roic: float | None
    roe: float | None
    roa: float | None
    roce: float | None
    wacc: float | None
    cost_of_equity: float | None
    cost_of_debt: float | None
    roic_wacc_spread: float | None
    debt_equity: float | None
    net_debt_ebitda: float | None
    interest_coverage: float | None
    ocf: float | None
    fcf: float | None


# ── Indicator time-series ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class TechnicalDay:
    date: date
    sma_10: float | None
    sma_50: float | None
    sma_200: float | None
    ema_10: float | None
    ema_50: float | None
    ema_200: float | None
    ema_12: float | None
    ema_26: float | None
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    roc_10: float | None
    roc_20: float | None
    golden_cross_sma: bool | None
    death_cross_sma: bool | None


@dataclass(frozen=True)
class RiskDay:
    date: date
    atr_14: float | None
    hist_vol_20d: float | None
    hist_vol_60d: float | None
    beta_sp500_60d: float | None
    worst_drop_1d: float | None
    worst_drop_5d: float | None
    worst_drop_10d: float | None
    max_drawdown_1y: float | None
    max_drawdown_2y: float | None
    sharpe_60d: float | None
    sortino_60d: float | None
    calmar_1y: float | None


@dataclass(frozen=True)
class ValuationDay:
    date: date
    market_cap: float | None
    enterprise_value: float | None
    pe_ttm: float | None
    forward_pe: float | None
    ps_ttm: float | None
    pb: float | None
    ev_ebitda: float | None
    ev_ebit: float | None
    ev_fcf: float | None
    earnings_yield: float | None
    fcf_yield: float | None
    pct_chg_1w: float | None
    pct_chg_3m: float | None
    pct_chg_6m: float | None
    pct_chg_9m: float | None
    pct_chg_ytd: float | None
    pct_chg_1y: float | None


@dataclass(frozen=True)
class ReturnsDay:
    date: date
    ret_1w: float | None
    ret_1m: float | None
    ret_3m: float | None
    ret_6m: float | None
    ret_9m: float | None
    ret_ytd: float | None
    ret_1y: float | None
    price_field: str | None
    computed_at: datetime | None


# ── News ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TickerNewsItem:
    news_id: int
    source: str | None
    title: str | None
    url: str | None
    published_at: datetime | None
    summary: str | None
    sentiment: str | None
    sentiment_score: float | None


# ── Admin-only ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EtlJobState:
    job_name: str
    last_run_at: datetime | None
    last_successful_date: date | None
    status: str | None
    last_error: str | None


@dataclass(frozen=True)
class EngineStatusEntry:
    key: str
    value: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PriceTick:
    tick_id: int
    ts: datetime | None
    price: float | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    source: str | None


# ── Macro ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MacroSeriesInfo:
    """Static metadata for a macro series (vendored from the macro registry)."""

    code: str
    name: str
    category: str
    frequency: str
    units: str
    seasonal_adj: bool
    source: str


@dataclass(frozen=True)
class MacroSeriesStat:
    """DB-derived stats for a single macro series."""

    code: str
    latest_value: float | None
    latest_date: date | None
    observation_count: int
    source: str | None


@dataclass(frozen=True)
class MacroObservation:
    """A single macro observation point."""

    date: date
    value: float | None


@dataclass(frozen=True)
class MacroLatestPoint:
    """Most recent observation for a macro series."""

    code: str
    date: date | None
    value: float | None
    source: str | None


@dataclass(frozen=True)
class MacroRegimeSnapshot:
    """Latest macro regime snapshot with all derived columns."""

    as_of_date: date | None
    fed_funds_rate: float | None
    yield_10y: float | None
    yield_2y: float | None
    spread_2s10s: float | None
    vix: float | None
    dxy: float | None
    hy_oas_bps: float | None
    rate_environment: str | None
    yield_curve: str | None
    credit_environment: str | None
    volatility_regime: str | None
    dollar_regime: str | None
    style_tilts: Any | None
    data_source: str | None
    computed_at: datetime | None
    sp500_level: float | None
    sp500_change_pct: float | None
    nasdaq_level: float | None
    nasdaq_change_pct: float | None
    cpi: float | None
    gdp: float | None
    fed_funds_change_30d: float | None
    yield_10y_change_30d: float | None
    yield_2y_change_30d: float | None
    spread_2s10s_change_30d: float | None
    dxy_change_5d: float | None
    dxy_change_30d: float | None
    vix_change_5d: float | None
    vix_pct_rank_1y: float | None
    hy_oas_change_30d: float | None
    sp500_change_5d_pct: float | None
    sp500_change_30d_pct: float | None
    nasdaq_change_5d_pct: float | None
    nasdaq_change_30d_pct: float | None
    cpi_surprise: float | None
    cpi_yoy_pct: float | None
    gdp_qoq_pct: float | None
