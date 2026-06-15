"""Repository contracts."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from app.domain.models import (
    AdminAuditEvent,
    BalanceSheetQ,
    CashFlowQ,
    CompanyFundamentals,
    CorporateAction,
    Country,
    Currency,
    EngineStatusEntry,
    EtlJobState,
    Exchange,
    InternalJobReceipt,
    Industry,
    IncomeStatementQ,
    MacroLatestPoint,
    MacroObservation,
    MacroRegimeSnapshot,
    MacroSeriesStat,
    MarketNewsItem,
    PortfolioPosition,
    PortfolioValuation,
    PriceDay,
    PriceTick,
    QualityQ,
    ReturnsDay,
    RiskDay,
    Sector,
    SignalRecord,
    TechnicalDay,
    TickerDetail,
    TickerNewsItem,
    TickerSnapshot,
    TickerSummary,
    TradeOrderResult,
    TradingCalendarDay,
    ValuationDay,
)


class MarketDataRepository(Protocol):
    """Read-oriented market-data repository contract."""

    def check_health(self) -> bool:
        """Return True when DB is reachable."""

    def get_active_tickers(self, limit: int = 50) -> list[TickerSummary]:
        """Return active ticker summaries."""

    def search_symbols(self, query: str, limit: int = 25) -> list[TickerSummary]:
        """Return symbol search results."""

    def get_latest_snapshot(self, ticker: str) -> TickerSnapshot | None:
        """Return latest ticker snapshot or None."""

    def get_recent_news(self, limit: int = 10) -> list[MarketNewsItem]:
        """Return recent market news."""

    def get_latest_signals(self, limit: int = 20, ticker: str | None = None) -> list[SignalRecord]:
        """Return latest trading signals."""

    def get_portfolio_valuation(self) -> PortfolioValuation | None:
        """Return latest portfolio valuation snapshot."""

    def get_portfolio_positions(self, limit: int = 100) -> list[PortfolioPosition]:
        """Return portfolio positions with latest pricing."""

    def create_trade_order(
        self,
        *,
        operator_subject: str,
        symbol: str,
        side: str,
        quantity: float,
        idempotency_key: str,
        limit_price: float | None = None,
    ) -> TradeOrderResult:
        """Create trade order with idempotency semantics."""

    def get_admin_audit_events(self, limit: int = 50, category: str | None = None) -> list[AdminAuditEvent]:
        """Return admin audit events."""

    def enqueue_internal_job(
        self,
        *,
        operator_subject: str,
        command_type: str,
        params: dict[str, Any],
    ) -> InternalJobReceipt:
        """Record and return internal job command."""

    def get_table_row_counts(self) -> list[dict[str, Any]]:
        """Return row counts for key tables."""

    def get_engine_worker_heartbeats(self) -> list[dict[str, Any]]:
        """Return engine worker heartbeat rows."""

    def execute_readonly_query(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        """Execute a read-only SQL query and return results."""

    def execute_named_query(self, query_name: str, limit: int = 100) -> list[dict[str, Any]]:
        """Execute a server-side curated named query and return results."""

    def get_database_version(self) -> str:
        """Return PostgreSQL version string."""

    def get_active_ticker_count(self) -> int:
        """Return count of active tickers."""

    def get_service_client_summary(self) -> list[dict[str, Any]]:
        """Return summary of service clients from iam schema."""

    # ── Reference / lookup ──────────────────────────────────────────────────

    def get_countries(self) -> list[Country]:
        """Return all countries."""

    def get_currencies(self) -> list[Currency]:
        """Return all currencies."""

    def get_exchanges(self) -> list[Exchange]:
        """Return all exchanges."""

    def get_sectors(self) -> list[Sector]:
        """Return all sectors."""

    def get_industries(self, sector_id: int | None = None) -> list[Industry]:
        """Return industries, optionally filtered by sector_id."""

    def get_trading_calendar(
        self, start: date | None = None, end: date | None = None, limit: int = 90
    ) -> list[TradingCalendarDay]:
        """Return trading calendar days."""

    # ── Ticker detail ────────────────────────────────────────────────────────

    def get_ticker_detail(self, ticker: str) -> TickerDetail | None:
        """Return full ticker profile with identifiers."""

    def get_price_history(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 252,
    ) -> list[PriceDay]:
        """Return daily OHLCV price history."""

    def get_corporate_actions(self, ticker: str, limit: int = 50) -> list[CorporateAction]:
        """Return corporate actions for a ticker."""

    def get_company_fundamentals(self, ticker: str) -> CompanyFundamentals | None:
        """Return company fundamentals snapshot."""

    # ── Financial statements ─────────────────────────────────────────────────

    def get_income_statements(self, ticker: str, limit: int = 12) -> list[IncomeStatementQ]:
        """Return quarterly income statements."""

    def get_balance_sheets(self, ticker: str, limit: int = 12) -> list[BalanceSheetQ]:
        """Return quarterly balance sheets."""

    def get_cash_flows(self, ticker: str, limit: int = 12) -> list[CashFlowQ]:
        """Return quarterly cash flow statements."""

    def get_quality_metrics(self, ticker: str, limit: int = 12) -> list[QualityQ]:
        """Return quarterly quality/ROIC metrics."""

    # ── Indicator time-series ────────────────────────────────────────────────

    def get_technical_indicators(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 252,
    ) -> list[TechnicalDay]:
        """Return daily technical indicators."""

    def get_risk_indicators(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 252,
    ) -> list[RiskDay]:
        """Return daily risk metrics."""

    def get_valuation_indicators(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 252,
    ) -> list[ValuationDay]:
        """Return daily valuation metrics."""

    def get_returns_snapshot(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 252,
    ) -> list[ReturnsDay]:
        """Return daily returns snapshot."""

    # ── News ─────────────────────────────────────────────────────────────────

    def get_ticker_news(self, ticker: str, limit: int = 20) -> list[TickerNewsItem]:
        """Return per-ticker news from the news table."""

    # ── Admin-only ────────────────────────────────────────────────────────────

    def get_etl_job_states(self) -> list[EtlJobState]:
        """Return ETL job states."""

    def get_engine_status(self) -> list[EngineStatusEntry]:
        """Return engine_status key-value entries."""

    def get_price_ticks(self, ticker: str, limit: int = 100) -> list[PriceTick]:
        """Return recent price ticks for a ticker."""


class MacroRepository(Protocol):
    """Read-oriented macro indicator / regime repository contract."""

    def get_series_stats(self) -> list[MacroSeriesStat]:
        """Return per-series stats (latest value/date, count, source) for all series."""

    def series_exists(self, code: str) -> bool:
        """Return True when the series code has observations."""

    def get_observations(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 500,
    ) -> list[MacroObservation]:
        """Return observations for one series, most recent first."""

    def get_latest_points(self, codes: list[str] | None = None) -> list[MacroLatestPoint]:
        """Return the most recent observation for every series (optionally filtered)."""

    def get_latest_regime(self) -> MacroRegimeSnapshot | None:
        """Return the latest macro regime snapshot, or None when empty."""
