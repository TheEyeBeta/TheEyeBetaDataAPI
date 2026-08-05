"""Read-only generic data access use-cases."""

from __future__ import annotations

from datetime import date

from app.auth.models import Principal
from app.auth.scopes import (
    SCOPE_ADMIN_READ,
    SCOPE_ADVISOR_READ,
    SCOPE_ANALYTICS_READ,
    SCOPE_MARKET_READ,
    SCOPE_PORTFOLIO_READ,
    SCOPE_SIGNALS_READ,
    SCOPE_SYMBOLS_READ,
    has_required_scopes,
)
from app.domain.errors import AuthorizationError
from app.repositories.sql_data import SQLReadOnlyDataRepository
from app.schemas.data import DataColumnsResponse, DataRowsResponse, DataTableInfo, DataTablesResponse

BASIC_DATA_TABLES: frozenset[str] = frozenset(
    {
        "corporate_actions",
        "exchanges",
        "fund_balance_q",
        "fund_cashflow_q",
        "fund_income_q",
        "fundamentals",
        "fundamentals_company",
        "fixed_income_curve_metrics",
        "fixed_income_signals",
        "holidays",
        "ind_risk_daily",
        "ind_technical_daily",
        "ind_valuation_daily",
        "instruments",
        "latest_snapshots",
        "macro_indicators",
        "macro_regime_snapshots",
        "market_calendars",
        "market_cap_daily",
        "market_news",
        "news_articles",
        "news_enriched",
        "price_ticks",
        "prices_daily",
        "prices_intraday",
        "public_ticker_map",
        "returns_snapshot_daily",
        "sector_daily",
        "signals",
        "signals_v1_archive",
        "ticker_news",
        "trading_calendar",
    }
)

_BASIC_READ_SCOPES: tuple[str, ...] = (
    SCOPE_MARKET_READ,
    SCOPE_SYMBOLS_READ,
    SCOPE_ANALYTICS_READ,
    SCOPE_ADVISOR_READ,
    SCOPE_SIGNALS_READ,
    SCOPE_PORTFOLIO_READ,
)

_HIGH_VOLUME_TABLES: frozenset[str] = frozenset(
    {"prices_daily", "prices_intraday", "price_ticks", "signals", "signals_v1_archive"}
)


class DataService:
    """Authorize and serve read-only table data."""

    def __init__(self, repository: SQLReadOnlyDataRepository) -> None:
        self._repository = repository

    def list_tables(self, principal: Principal) -> DataTablesResponse:
        tables = self._visible_tables(principal)
        return DataTablesResponse(tables=tables)

    def list_columns(self, principal: Principal, table: str) -> DataColumnsResponse:
        self._ensure_table_visible(principal, table)
        return DataColumnsResponse(table=table, columns=self._repository.list_columns(table))

    def query_rows(
        self,
        *,
        principal: Principal,
        table: str,
        limit: int,
        offset: int,
        order_by: str | None,
        order_dir: str,
        filters: list[str],
        symbol: str | None,
        date_column: str | None,
        start: date | None,
        end: date | None,
    ) -> DataRowsResponse:
        self._ensure_table_visible(principal, table)
        self._validate_high_volume_query(table=table, symbol=symbol, start=start, end=end, limit=limit)
        rows = self._repository.query_rows(
            table=table,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters,
            symbol=symbol,
            date_column=date_column,
            start=start,
            end=end,
        )
        return DataRowsResponse(table=table, limit=limit, offset=offset, row_count=len(rows), rows=rows)

    def _visible_tables(self, principal: Principal) -> list[DataTableInfo]:
        if principal.delegated:
            raise AuthorizationError("Delegated Lens tokens cannot use generic table access")
        all_tables = self._repository.list_tables()
        if self._is_admin(principal):
            return [table.model_copy(update={"basic_access": table.name in BASIC_DATA_TABLES}) for table in all_tables]
        self._require_basic_read(principal)
        return [
            table.model_copy(update={"basic_access": True})
            for table in all_tables
            if table.name in BASIC_DATA_TABLES
        ]

    def _ensure_table_visible(self, principal: Principal, table: str) -> None:
        if principal.delegated:
            raise AuthorizationError("Delegated Lens tokens cannot use generic table access")
        if self._is_admin(principal):
            return
        self._require_basic_read(principal)
        if table not in BASIC_DATA_TABLES:
            raise AuthorizationError("Table requires admin:read scope")

    @staticmethod
    def _validate_high_volume_query(
        *, table: str, symbol: str | None, start: date | None, end: date | None, limit: int
    ) -> None:
        """Require bounded instrument and time predicates for hypertable-scale reads."""
        if table not in _HIGH_VOLUME_TABLES:
            return
        if not symbol:
            raise AuthorizationError("High-volume tables require a symbol filter")
        if start is None or end is None:
            raise AuthorizationError("High-volume tables require start and end dates")
        if start > end:
            raise AuthorizationError("start must not be after end")
        if limit > 500:
            raise AuthorizationError("High-volume table limit must not exceed 500")

    @staticmethod
    def _is_admin(principal: Principal) -> bool:
        return has_required_scopes(principal.scopes, [SCOPE_ADMIN_READ])

    @staticmethod
    def _require_basic_read(principal: Principal) -> None:
        if not any(has_required_scopes(principal.scopes, [scope]) for scope in _BASIC_READ_SCOPES):
            raise AuthorizationError("A read scope is required")
