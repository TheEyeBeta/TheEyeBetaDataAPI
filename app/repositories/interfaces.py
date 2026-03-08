"""Repository contracts."""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.models import (
    AdminAuditEvent,
    InternalJobReceipt,
    MarketNewsItem,
    PortfolioPosition,
    PortfolioValuation,
    SignalRecord,
    TickerSnapshot,
    TickerSummary,
    TradeOrderResult,
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

    def get_database_version(self) -> str:
        """Return PostgreSQL version string."""

    def get_active_ticker_count(self) -> int:
        """Return count of active tickers."""

    def get_service_client_summary(self) -> list[dict[str, Any]]:
        """Return summary of service clients from iam schema."""
