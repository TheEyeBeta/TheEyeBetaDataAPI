"""SQLAlchemy repository implementation for market data."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.errors import DatabaseUnavailableError, ValidationAppError
from app.domain.models import (
    AdminAuditEvent,
    BalanceSheetQ,
    CapEvent,
    CashFlowQ,
    CompanyFundamentals,
    CorporateAction,
    Country,
    Currency,
    EngineStatusEntry,
    EtlJobState,
    Exchange,
    Industry,
    IncomeStatementQ,
    MarketNewsItem,
    PortfolioPosition,
    PortfolioValuation,
    PriceDay,
    PriceTick,
    QualityQ,
    ResolvedSymbol,
    ReturnsDay,
    RiskDay,
    Sector,
    SectorDaily,
    SignalRecord,
    TechnicalDay,
    TickerDetail,
    TickerNewsItem,
    TickerSnapshot,
    TickerSummary,
    TradingCalendarDay,
    UniverseCapEntry,
    ValuationDay,
)
from app.repositories.interfaces import MarketDataRepository

logger = logging.getLogger("dataapi.repository")


def _to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _to_datetime(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _to_date(value: Any) -> date | None:
    return value if isinstance(value, date) else None


# Server-side allowlist of parameterised admin queries over the canonical
# theeyebeta schema. Only :limit is accepted as a parameter.
_CURATED_ADMIN_QUERIES: dict[str, str] = {
    "all_tickers": (
        "SELECT symbol AS ticker,"
        " COALESCE(metadata->>'company_name', metadata->>'name', symbol) AS company_name,"
        " active AS is_active"
        " FROM theeyebeta.instruments ORDER BY symbol LIMIT :limit"
    ),
    "latest_prices": (
        "SELECT i.symbol AS ticker, ls.last_price, ls.price_change_pct, ls.rsi_14, ls.updated_at"
        " FROM theeyebeta.latest_snapshots ls"
        " JOIN theeyebeta.instruments i ON i.id = ls.instrument_id"
        " ORDER BY ls.updated_at DESC LIMIT :limit"
    ),
    "latest_signals": (
        "SELECT i.symbol AS ticker, ls.latest_signal, ls.signal_confidence,"
        " ls.signal_strategy, ls.signal_ts"
        " FROM theeyebeta.latest_snapshots ls"
        " JOIN theeyebeta.instruments i ON i.id = ls.instrument_id"
        " WHERE ls.latest_signal IS NOT NULL"
        " ORDER BY ls.signal_ts DESC LIMIT :limit"
    ),
    "orders": (
        "SELECT id, client_order_id, broker_order_id, portfolio_id, instrument_id, side, order_type,"
        " qty, limit_price, stop_price, time_in_force, status, approved_by, approved_at,"
        " submitted_at, filled_qty, avg_fill_price, created_at, updated_at"
        " FROM theeyebeta.orders ORDER BY created_at DESC LIMIT :limit"
    ),
    "portfolio": (
        "SELECT id, portfolio_id, instrument_id, qty, avg_entry_price, market_value, unrealized_pnl,"
        " realized_pnl, opened_at, updated_at"
        " FROM theeyebeta.positions ORDER BY market_value DESC NULLS LAST LIMIT :limit"
    ),
    "command_log": (
        "SELECT id, actor, action, entity_type, entity_id, ts"
        " FROM theeyebeta.audit_log ORDER BY ts DESC LIMIT :limit"
    ),
    "market_news": (
        "SELECT id, provider, url, headline, summary, source, category, related, published_at, fetched_at"
        " FROM theeyebeta.market_news ORDER BY published_at DESC LIMIT :limit"
    ),
    "heartbeats": (
        "SELECT worker_id, worker_type, status, last_heartbeat, started_at, restart_count, last_error"
        " FROM theeyebeta.worker_heartbeats ORDER BY worker_id LIMIT :limit"
    ),
    "table_stats": (
        "SELECT schemaname, relname AS tablename, n_live_tup AS row_count"
        " FROM pg_stat_user_tables WHERE schemaname = 'theeyebeta'"
        " ORDER BY n_live_tup DESC LIMIT :limit"
    ),
}

CURATED_QUERY_NAMES: frozenset[str] = frozenset(_CURATED_ADMIN_QUERIES)


class SQLMarketDataRepository(MarketDataRepository):
    """SQL-backed market data repository with explicit mapping."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def check_health(self) -> bool:
        try:
            self._session.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as exc:
            logger.exception("db health query failed")
            raise DatabaseUnavailableError("Unable to reach database") from exc

    def get_active_tickers(self, limit: int = 50) -> list[TickerSummary]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        symbol AS ticker,
                        COALESCE(metadata->>'company_name', metadata->>'name', symbol) AS company_name
                    FROM theeyebeta.instruments
                    WHERE active = true
                    ORDER BY symbol
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
            return [TickerSummary(ticker=str(row["ticker"]), company_name=str(row["company_name"])) for row in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_active_tickers failed")
            raise DatabaseUnavailableError("Unable to fetch active tickers") from exc

    def search_symbols(self, query: str, limit: int = 25) -> list[TickerSummary]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        symbol AS ticker,
                        COALESCE(metadata->>'company_name', metadata->>'name', symbol) AS company_name
                    FROM theeyebeta.instruments
                    WHERE active = true
                      AND (
                        UPPER(symbol) LIKE UPPER(:prefix)
                        OR UPPER(COALESCE(metadata->>'company_name', metadata->>'name', symbol)) LIKE UPPER(:name_like)
                      )
                    ORDER BY symbol
                    LIMIT :limit
                    """
                ),
                {"prefix": f"{query}%", "name_like": f"%{query}%", "limit": limit},
            ).mappings().all()
            return [TickerSummary(ticker=str(row["ticker"]), company_name=str(row["company_name"])) for row in rows]
        except SQLAlchemyError as exc:
            logger.exception("search_symbols failed")
            raise DatabaseUnavailableError("Unable to search symbols") from exc

    def resolve_symbol(self, symbol: str) -> list[ResolvedSymbol]:
        """Return at most two exact matches so callers can reject ambiguous symbols."""
        try:
            rows = (
                self._session.execute(
                    text(
                        """
                        SELECT
                            i.id AS instrument_id,
                            COALESCE(
                                NULLIF(BTRIM(i.metadata->>'company_name'), ''),
                                NULLIF(BTRIM(i.metadata->>'name'), ''),
                                i.symbol
                            ) AS name,
                            e.code AS exchange,
                            e.currency_iso AS currency,
                            i.isin,
                            i.cusip,
                            i.figi,
                            i.asset_class,
                            i.active
                        FROM theeyebeta.instruments i
                        JOIN theeyebeta.exchanges e ON e.id = i.exchange_id
                        WHERE UPPER(i.symbol) = UPPER(:symbol)
                        ORDER BY i.id
                        LIMIT 2
                        """
                    ),
                    {"symbol": symbol},
                )
                .mappings()
                .all()
            )
            return [
                ResolvedSymbol(
                    instrument_id=int(row["instrument_id"]),
                    name=str(row["name"]),
                    exchange=str(row["exchange"]),
                    currency=str(row["currency"]),
                    isin=str(row["isin"]) if row.get("isin") else None,
                    cusip=str(row["cusip"]) if row.get("cusip") else None,
                    figi=str(row["figi"]) if row.get("figi") else None,
                    asset_class=str(row["asset_class"]),
                    active=bool(row["active"]),
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("resolve_symbol failed")
            raise DatabaseUnavailableError("Unable to resolve symbol") from exc

    def get_latest_snapshot(self, ticker: str) -> TickerSnapshot | None:
        try:
            row = self._session.execute(
                text(
                    """
                    SELECT
                        i.symbol AS ticker,
                        COALESCE(i.metadata->>'company_name', i.metadata->>'name', i.symbol) AS company_name,
                        ls.last_price,
                        ls.price_change_pct,
                        ls.rsi_14,
                        ls.sma_10,
                        ls.sma_50,
                        ls.sma_200,
                        ls.macd,
                        ls.macd_signal,
                        ls.macd_hist,
                        ls.updated_at
                    FROM theeyebeta.latest_snapshots ls
                    JOIN theeyebeta.instruments i ON i.id = ls.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    """
                ),
                {"ticker": ticker},
            ).mappings().first()
            if not row:
                return None
            return TickerSnapshot(
                ticker=str(row["ticker"]),
                company_name=str(row["company_name"]),
                last_price=_to_float(row.get("last_price")),
                price_change_pct=_to_float(row.get("price_change_pct")),
                rsi_14=_to_float(row.get("rsi_14")),
                sma_10=_to_float(row.get("sma_10")),
                sma_50=_to_float(row.get("sma_50")),
                sma_200=_to_float(row.get("sma_200")),
                macd=_to_float(row.get("macd")),
                macd_signal=_to_float(row.get("macd_signal")),
                macd_hist=_to_float(row.get("macd_hist")),
                updated_at=_to_datetime(row.get("updated_at")),
            )
        except SQLAlchemyError as exc:
            logger.exception("get_latest_snapshot failed")
            raise DatabaseUnavailableError("Unable to fetch latest snapshot") from exc

    def get_recent_news(self, limit: int = 10) -> list[MarketNewsItem]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT headline, source, category, published_at
                    FROM theeyebeta.market_news
                    ORDER BY published_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
            return [
                MarketNewsItem(
                    headline=str(row["headline"]),
                    source=str(row["source"]) if row.get("source") is not None else None,
                    category=str(row["category"]) if row.get("category") is not None else None,
                    published_at=_to_datetime(row.get("published_at")),
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_recent_news failed")
            raise DatabaseUnavailableError("Unable to fetch recent news") from exc

    def get_latest_signals(self, limit: int = 20, ticker: str | None = None) -> list[SignalRecord]:
        try:
            params: dict[str, Any] = {"limit": limit}
            if ticker:
                params["ticker"] = ticker

            rows = self._session.execute(
                text(
                    f"""
                    SELECT
                        i.symbol AS ticker,
                        ls.signal_strategy AS strategy_name,
                        ls.latest_signal AS signal,
                        ls.signal_confidence AS confidence,
                        ls.last_price AS entry_price,
                        NULL::numeric AS target_price,
                        NULL::numeric AS stop_loss,
                        ls.signal_ts AS ts
                    FROM theeyebeta.latest_snapshots ls
                    JOIN theeyebeta.instruments i ON i.id = ls.instrument_id
                    WHERE ls.latest_signal IS NOT NULL
                      {'AND UPPER(i.symbol) = UPPER(:ticker)' if ticker else ''}
                    ORDER BY ls.signal_ts DESC NULLS LAST, i.symbol ASC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
            return [
                SignalRecord(
                    ticker=str(row["ticker"]),
                    strategy_name=str(row["strategy_name"]) if row.get("strategy_name") is not None else None,
                    signal=str(row["signal"]),
                    confidence=_to_float(row.get("confidence")),
                    entry_price=_to_float(row.get("entry_price")),
                    target_price=_to_float(row.get("target_price")),
                    stop_loss=_to_float(row.get("stop_loss")),
                    timestamp=_to_datetime(row.get("ts")),
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_latest_signals failed")
            raise DatabaseUnavailableError("Unable to fetch latest signals") from exc

    def get_portfolio_valuation(self) -> PortfolioValuation | None:
        try:
            row = self._session.execute(
                text(
                    """
                    SELECT
                        MAX(updated_at)::date AS valuation_date,
                        SUM(market_value) AS total_value,
                        NULL::numeric AS cash_balance,
                        SUM(market_value) AS positions_value,
                        SUM(qty * avg_entry_price) AS total_cost_basis,
                        SUM(unrealized_pnl) AS unrealized_pnl,
                        SUM(realized_pnl) AS realized_pnl,
                        NULL::text AS currency_code,
                        MAX(updated_at) AS created_at
                    FROM theeyebeta.positions
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if not row or row.get("total_value") is None:
                return None
            currency = row.get("currency_code")
            return PortfolioValuation(
                valuation_date=_to_date(row.get("valuation_date")),
                total_value=_to_float(row.get("total_value")),
                cash_balance=_to_float(row.get("cash_balance")),
                positions_value=_to_float(row.get("positions_value")),
                total_cost_basis=_to_float(row.get("total_cost_basis")),
                unrealized_pnl=_to_float(row.get("unrealized_pnl")),
                realized_pnl=_to_float(row.get("realized_pnl")),
                currency_code=str(currency) if currency is not None else None,
                created_at=_to_datetime(row.get("created_at")),
            )
        except SQLAlchemyError as exc:
            logger.exception("get_portfolio_valuation failed")
            raise DatabaseUnavailableError("Unable to fetch portfolio valuation") from exc

    def get_portfolio_positions(self, limit: int = 100) -> list[PortfolioPosition]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        i.symbol AS ticker,
                        COALESCE(i.metadata->>'company_name', i.metadata->>'name', i.symbol) AS company_name,
                        p.qty AS quantity,
                        p.avg_entry_price AS average_cost,
                        ls.last_price,
                        COALESCE(p.market_value, p.qty * ls.last_price) AS market_value,
                        p.unrealized_pnl,
                        p.updated_at AS last_updated
                    FROM theeyebeta.positions p
                    JOIN theeyebeta.instruments i ON i.id = p.instrument_id
                    LEFT JOIN theeyebeta.latest_snapshots ls ON ls.instrument_id = p.instrument_id
                    ORDER BY market_value DESC NULLS LAST, i.symbol
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
            return [
                PortfolioPosition(
                    ticker=str(row["ticker"]),
                    company_name=str(row["company_name"]),
                    quantity=float(row["quantity"]),
                    average_cost=_to_float(row.get("average_cost")),
                    last_price=_to_float(row.get("last_price")),
                    market_value=_to_float(row.get("market_value")),
                    unrealized_pnl=_to_float(row.get("unrealized_pnl")),
                    last_updated=_to_datetime(row.get("last_updated")),
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_portfolio_positions failed")
            raise DatabaseUnavailableError("Unable to fetch portfolio positions") from exc

    def get_admin_audit_events(self, limit: int = 50, category: str | None = None) -> list[AdminAuditEvent]:
        try:
            where_clause = ""
            params: dict[str, Any] = {"limit": limit}
            if category:
                where_clause = "WHERE event_category = :category"
                params["category"] = category
            rows = self._session.execute(
                text(
                    f"""
                    SELECT
                        event_id::text AS event_id,
                        event_type,
                        event_category,
                        source_type,
                        source_id,
                        target_type,
                        target_id,
                        severity,
                        payload,
                        created_at
                    FROM theeyebeta.trask_audit_events_archive
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
            return [
                AdminAuditEvent(
                    event_id=str(row["event_id"]),
                    event_type=str(row["event_type"]) if row.get("event_type") is not None else None,
                    event_category=str(row["event_category"]) if row.get("event_category") is not None else None,
                    source_type=str(row["source_type"]) if row.get("source_type") is not None else None,
                    source_id=str(row["source_id"]) if row.get("source_id") is not None else None,
                    target_type=str(row["target_type"]) if row.get("target_type") is not None else None,
                    target_id=str(row["target_id"]) if row.get("target_id") is not None else None,
                    severity=str(row["severity"]) if row.get("severity") is not None else None,
                    payload=row.get("payload") if isinstance(row.get("payload"), dict) else None,
                    created_at=_to_datetime(row.get("created_at")),
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_admin_audit_events failed")
            raise DatabaseUnavailableError("Unable to fetch admin audit events") from exc

    def get_table_row_counts(self) -> list[dict[str, Any]]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT relname AS table, n_live_tup AS row_count
                    FROM pg_stat_user_tables
                    WHERE schemaname = 'theeyebeta'
                    ORDER BY n_live_tup DESC, relname
                    """
                )
            ).mappings().all()
            return [{"table": str(r["table"]), "row_count": int(r["row_count"])} for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_table_row_counts failed")
            raise DatabaseUnavailableError("Unable to fetch table counts") from exc

    def get_engine_worker_heartbeats(self) -> list[dict[str, Any]]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        worker_id AS worker_name,
                        status,
                        last_heartbeat,
                        EXTRACT(EPOCH FROM (NOW() - last_heartbeat))::int AS seconds_ago,
                        metadata
                    FROM theeyebeta.worker_heartbeats
                    ORDER BY worker_id
                    """
                )
            ).mappings().all()
            return [
                {
                    "worker_name": str(row["worker_name"]),
                    "status": str(row["status"]) if row.get("status") else "unknown",
                    "last_heartbeat": str(row["last_heartbeat"]) if row.get("last_heartbeat") else None,
                    "seconds_ago": int(row["seconds_ago"]) if row.get("seconds_ago") is not None else None,
                    "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else None,
                }
                for row in rows
            ]
        except SQLAlchemyError:
            logger.warning("engine_worker_heartbeats table not available")
            return []

    def execute_readonly_query(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        raise ValidationAppError("Arbitrary SQL is disabled; use the read-only table API")

    def execute_named_query(self, query_name: str, limit: int = 100) -> list[dict[str, Any]]:
        sql = _CURATED_ADMIN_QUERIES.get(query_name)
        if sql is None:
            raise ValidationAppError(f"Unknown query name: {query_name!r}")
        try:
            rows = self._session.execute(text(sql), {"limit": limit}).mappings().all()
            return [
                {k: (str(v) if v is not None else None) for k, v in dict(row).items()}
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("execute_named_query failed query_name=%s", query_name)
            raise DatabaseUnavailableError(f"Query failed: {exc}") from exc

    def get_database_version(self) -> str:
        try:
            row = self._session.execute(text("SELECT version()")).mappings().first()
            return str(row["version"]) if row else "unknown"
        except SQLAlchemyError:
            return "unavailable"

    def get_active_ticker_count(self) -> int:
        try:
            row = self._session.execute(
                text("SELECT COUNT(*) AS cnt FROM theeyebeta.instruments WHERE active = true")
            ).mappings().first()
            return int(row["cnt"]) if row else 0
        except SQLAlchemyError:
            return -1

    def get_service_client_summary(self) -> list[dict[str, Any]]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        sc.client_id,
                        sc.display_name,
                        sc.is_active,
                        sc.created_at,
                        (SELECT COUNT(*) FROM iam.service_client_scopes scs
                         WHERE scs.client_id = sc.client_id) AS scope_count
                    FROM iam.service_clients sc
                    ORDER BY sc.client_id
                    """
                )
            ).mappings().all()
            return [
                {
                    "client_id": str(row["client_id"]),
                    "display_name": str(row["display_name"]) if row.get("display_name") else None,
                    "is_active": bool(row["is_active"]),
                    "created_at": str(row["created_at"]) if row.get("created_at") else None,
                    "scope_count": int(row["scope_count"]) if row.get("scope_count") is not None else 0,
                }
                for row in rows
            ]
        except SQLAlchemyError:
            logger.warning("iam.service_clients table not available")
            return []

    # ── Reference / lookup ────────────────────────────────────────────────────

    def get_countries(self) -> list[Country]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT DISTINCT
                        country_iso2 AS country_code,
                        country_iso2 AS country_name,
                        NULL::text AS default_timezone
                    FROM theeyebeta.exchanges
                    WHERE country_iso2 IS NOT NULL
                    ORDER BY country_iso2
                    """
                )
            ).mappings().all()
            return [Country(country_code=str(r["country_code"]), country_name=str(r["country_name"]), default_timezone=str(r["default_timezone"]) if r.get("default_timezone") else None) for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_countries failed")
            raise DatabaseUnavailableError("Unable to fetch countries") from exc

    def get_currencies(self) -> list[Currency]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT DISTINCT
                        currency_iso AS currency_code,
                        currency_iso AS currency_name,
                        NULL::text AS symbol
                    FROM theeyebeta.exchanges
                    WHERE currency_iso IS NOT NULL
                    ORDER BY currency_iso
                    """
                )
            ).mappings().all()
            return [Currency(currency_code=str(r["currency_code"]), currency_name=str(r["currency_name"]), symbol=str(r["symbol"]) if r.get("symbol") else None) for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_currencies failed")
            raise DatabaseUnavailableError("Unable to fetch currencies") from exc

    def get_exchanges(self) -> list[Exchange]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        id AS exchange_id,
                        name,
                        code AS mic_code,
                        country_iso2 AS country_code,
                        timezone
                    FROM theeyebeta.exchanges
                    ORDER BY name
                    """
                )
            ).mappings().all()
            return [
                Exchange(
                    exchange_id=int(r["exchange_id"]),
                    name=str(r["name"]),
                    mic_code=str(r["mic_code"]) if r.get("mic_code") else None,
                    country_code=str(r["country_code"]) if r.get("country_code") else None,
                    timezone=str(r["timezone"]) if r.get("timezone") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_exchanges failed")
            raise DatabaseUnavailableError("Unable to fetch exchanges") from exc

    def get_sectors(self) -> list[Sector]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT DENSE_RANK() OVER (ORDER BY sector)::int AS sector_id, sector AS sector_name
                    FROM (
                        SELECT DISTINCT sector
                        FROM theeyebeta.instruments
                        WHERE sector IS NOT NULL AND sector <> ''
                    ) sectors
                    ORDER BY sector
                    """
                )
            ).mappings().all()
            return [Sector(sector_id=int(r["sector_id"]), sector_name=str(r["sector_name"])) for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_sectors failed")
            raise DatabaseUnavailableError("Unable to fetch sectors") from exc

    def get_industries(self, sector_id: int | None = None) -> list[Industry]:
        try:
            if sector_id is not None:
                rows = self._session.execute(
                    text(
                        """
                        WITH sectors AS (
                            SELECT sector, DENSE_RANK() OVER (ORDER BY sector)::int AS sector_id
                            FROM (
                                SELECT DISTINCT sector
                                FROM theeyebeta.instruments
                                WHERE sector IS NOT NULL AND sector <> ''
                            ) s
                        ),
                        industries AS (
                            SELECT DISTINCT s.sector_id, i.industry
                            FROM theeyebeta.instruments i
                            JOIN sectors s ON s.sector = i.sector
                            WHERE i.industry IS NOT NULL AND i.industry <> ''
                        )
                        SELECT
                            DENSE_RANK() OVER (ORDER BY sector_id, industry)::int AS industry_id,
                            sector_id,
                            industry AS industry_name
                        FROM industries
                        WHERE sector_id = :sid
                        ORDER BY industry
                        """
                    ),
                    {"sid": sector_id},
                ).mappings().all()
            else:
                rows = self._session.execute(
                    text(
                        """
                        WITH sectors AS (
                            SELECT sector, DENSE_RANK() OVER (ORDER BY sector)::int AS sector_id
                            FROM (
                                SELECT DISTINCT sector
                                FROM theeyebeta.instruments
                                WHERE sector IS NOT NULL AND sector <> ''
                            ) s
                        ),
                        industries AS (
                            SELECT DISTINCT s.sector_id, i.industry
                            FROM theeyebeta.instruments i
                            JOIN sectors s ON s.sector = i.sector
                            WHERE i.industry IS NOT NULL AND i.industry <> ''
                        )
                        SELECT
                            DENSE_RANK() OVER (ORDER BY sector_id, industry)::int AS industry_id,
                            sector_id,
                            industry AS industry_name
                        FROM industries
                        ORDER BY industry
                        """
                    )
                ).mappings().all()
            return [Industry(industry_id=int(r["industry_id"]), sector_id=int(r["sector_id"]), industry_name=str(r["industry_name"])) for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_industries failed")
            raise DatabaseUnavailableError("Unable to fetch industries") from exc

    def get_trading_calendar(self, start: date | None = None, end: date | None = None, limit: int = 90) -> list[TradingCalendarDay]:
        try:
            where_parts = []
            params: dict[str, Any] = {"limit": limit}
            if start:
                where_parts.append("calendar_date >= :start")
                params["start"] = start
            if end:
                where_parts.append("calendar_date <= :end")
                params["end"] = end
            where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            rows = self._session.execute(
                text(f"SELECT calendar_date, is_trading_day, market_name, holiday_name, notes FROM theeyebeta.trading_calendar {where} ORDER BY calendar_date DESC LIMIT :limit"),  # noqa: S608
                params,
            ).mappings().all()
            return [
                TradingCalendarDay(
                    calendar_date=r["calendar_date"],
                    is_trading_day=bool(r["is_trading_day"]),
                    market_name=str(r["market_name"]) if r.get("market_name") else None,
                    holiday_name=str(r["holiday_name"]) if r.get("holiday_name") else None,
                    notes=str(r["notes"]) if r.get("notes") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_trading_calendar failed")
            raise DatabaseUnavailableError("Unable to fetch trading calendar") from exc

    # ── Ticker detail ─────────────────────────────────────────────────────────

    def get_ticker_detail(self, ticker: str) -> TickerDetail | None:
        try:
            row = self._session.execute(
                text(
                    """
                    SELECT
                        i.symbol AS ticker,
                        COALESCE(i.metadata->>'company_name', i.metadata->>'name', i.symbol) AS company_name,
                        i.asset_class AS asset_type,
                        e.country_iso2 AS country_code,
                        e.timezone,
                        e.currency_iso AS currency_code,
                        i.active AS is_active,
                        NULL::int AS sector_id,
                        NULL::int AS industry_id,
                        NULL::text AS website,
                        i.metadata->>'description' AS description,
                        NULL::int AS founded_year,
                        NULL::int AS employees,
                        i.isin,
                        i.cusip,
                        i.figi
                    FROM theeyebeta.instruments i
                    LEFT JOIN theeyebeta.exchanges e ON e.id = i.exchange_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    """
                ),
                {"ticker": ticker},
            ).mappings().first()
            if not row:
                return None
            identifiers = [
                {"id_type": id_type, "id_value": str(row[id_type])}
                for id_type in ("isin", "cusip", "figi")
                if row.get(id_type)
            ]
            return TickerDetail(
                ticker=str(row["ticker"]),
                company_name=str(row["company_name"]),
                asset_type=str(row["asset_type"]) if row.get("asset_type") else None,
                country_code=str(row["country_code"]) if row.get("country_code") else None,
                timezone=str(row["timezone"]) if row.get("timezone") else None,
                currency_code=str(row["currency_code"]) if row.get("currency_code") else None,
                is_active=bool(row["is_active"]),
                sector_id=int(row["sector_id"]) if row.get("sector_id") is not None else None,
                industry_id=int(row["industry_id"]) if row.get("industry_id") is not None else None,
                website=str(row["website"]) if row.get("website") else None,
                description=str(row["description"]) if row.get("description") else None,
                founded_year=int(row["founded_year"]) if row.get("founded_year") is not None else None,
                employees=int(row["employees"]) if row.get("employees") is not None else None,
                identifiers=identifiers,
            )
        except SQLAlchemyError as exc:
            logger.exception("get_ticker_detail failed")
            raise DatabaseUnavailableError("Unable to fetch ticker detail") from exc

    def get_price_history(self, ticker: str, start: date | None = None, end: date | None = None, limit: int = 252) -> list[PriceDay]:
        try:
            where_parts = ["UPPER(i.symbol) = UPPER(:ticker)"]
            params: dict[str, Any] = {"ticker": ticker, "limit": limit}
            if start:
                where_parts.append("p.ts::date >= :start")
                params["start"] = start
            if end:
                where_parts.append("p.ts::date <= :end")
                params["end"] = end
            where = " AND ".join(where_parts)
            rows = self._session.execute(
                text(
                    f"""
                    SELECT date, open, high, low, close, adj_close, volume, vwap
                    FROM (
                        SELECT DISTINCT ON (p.ts::date)
                               p.ts::date AS date, p.open, p.high, p.low,
                               p.close, p.adj_close, p.volume, p.vwap
                        FROM theeyebeta.prices_daily p
                        JOIN theeyebeta.instruments i ON i.id = p.instrument_id
                        WHERE {where}
                        ORDER BY p.ts::date, p.ts DESC
                    ) deduped
                    ORDER BY date DESC
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                PriceDay(
                    date=r["date"],
                    open=_to_float(r.get("open")),
                    high=_to_float(r.get("high")),
                    low=_to_float(r.get("low")),
                    close=_to_float(r.get("close")),
                    adj_close=_to_float(r.get("adj_close")),
                    volume=_to_float(r.get("volume")),
                    vwap=_to_float(r.get("vwap")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_price_history failed")
            raise DatabaseUnavailableError("Unable to fetch price history") from exc

    def get_corporate_actions(self, ticker: str, limit: int = 50) -> list[CorporateAction]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        ca.id AS action_id,
                        ca.ex_date AS action_date,
                        ca.action_type,
                        CASE
                            WHEN ca.ratio_num IS NOT NULL AND ca.ratio_den IS NOT NULL AND ca.ratio_den <> 0
                            THEN ca.ratio_num / ca.ratio_den
                            ELSE NULL
                        END AS split_ratio,
                        ca.cash_amount AS dividend_amount,
                        ca.metadata::text AS notes
                    FROM theeyebeta.corporate_actions ca
                    JOIN theeyebeta.instruments i ON i.id = ca.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    ORDER BY ca.ex_date DESC
                    LIMIT :limit
                    """
                ),
                {"ticker": ticker, "limit": limit},
            ).mappings().all()
            return [
                CorporateAction(
                    action_id=int(r["action_id"]),
                    action_date=_to_date(r.get("action_date")),
                    action_type=str(r["action_type"]),
                    split_ratio=_to_float(r.get("split_ratio")),
                    dividend_amount=_to_float(r.get("dividend_amount")),
                    notes=str(r["notes"]) if r.get("notes") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_corporate_actions failed")
            raise DatabaseUnavailableError("Unable to fetch corporate actions") from exc

    def get_company_fundamentals(self, ticker: str) -> CompanyFundamentals | None:
        try:
            row = self._session.execute(
                text(
                    """
                    SELECT f.sector, f.industry, f.sub_industry, f.ceo, f.full_time_employees,
                           f.headquarters_city, f.headquarters_state, f.headquarters_country,
                           f.market_cap, f.enterprise_value, f.shares_outstanding, f.float_shares,
                           f.pe_ratio, f.pe_forward, f.peg_ratio, f.price_to_book, f.price_to_sales,
                           f.ev_to_ebitda, f.ev_to_revenue, f.dividend_rate, f.dividend_yield,
                           f.ex_dividend_date, f.payout_ratio, f.currency, f.source, f.last_updated
                    FROM theeyebeta.fundamentals_company f
                    JOIN theeyebeta.instruments i ON i.id = f.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    """
                ),
                {"ticker": ticker},
            ).mappings().first()
            if not row:
                return None
            return CompanyFundamentals(
                sector=str(row["sector"]) if row.get("sector") else None,
                industry=str(row["industry"]) if row.get("industry") else None,
                sub_industry=str(row["sub_industry"]) if row.get("sub_industry") else None,
                ceo=str(row["ceo"]) if row.get("ceo") else None,
                full_time_employees=int(row["full_time_employees"]) if row.get("full_time_employees") is not None else None,
                headquarters_city=str(row["headquarters_city"]) if row.get("headquarters_city") else None,
                headquarters_state=str(row["headquarters_state"]) if row.get("headquarters_state") else None,
                headquarters_country=str(row["headquarters_country"]) if row.get("headquarters_country") else None,
                market_cap=_to_float(row.get("market_cap")),
                enterprise_value=_to_float(row.get("enterprise_value")),
                shares_outstanding=_to_float(row.get("shares_outstanding")),
                float_shares=_to_float(row.get("float_shares")),
                pe_ratio=_to_float(row.get("pe_ratio")),
                pe_forward=_to_float(row.get("pe_forward")),
                peg_ratio=_to_float(row.get("peg_ratio")),
                price_to_book=_to_float(row.get("price_to_book")),
                price_to_sales=_to_float(row.get("price_to_sales")),
                ev_to_ebitda=_to_float(row.get("ev_to_ebitda")),
                ev_to_revenue=_to_float(row.get("ev_to_revenue")),
                dividend_rate=_to_float(row.get("dividend_rate")),
                dividend_yield=_to_float(row.get("dividend_yield")),
                ex_dividend_date=_to_date(row.get("ex_dividend_date")),
                payout_ratio=_to_float(row.get("payout_ratio")),
                currency=str(row["currency"]) if row.get("currency") else None,
                source=str(row["source"]) if row.get("source") else None,
                last_updated=_to_datetime(row.get("last_updated")),
            )
        except SQLAlchemyError as exc:
            logger.exception("get_company_fundamentals failed")
            raise DatabaseUnavailableError("Unable to fetch company fundamentals") from exc

    # ── Financial statements ──────────────────────────────────────────────────

    def _quarterly_params(self, ticker: str, limit: int) -> tuple[str, dict[str, Any]]:
        return "UPPER(i.symbol) = UPPER(:ticker)", {"ticker": ticker, "limit": limit}

    def get_income_statements(self, ticker: str, limit: int = 12) -> list[IncomeStatementQ]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT fi.period_end, fi.fiscal_year, fi.fiscal_quarter,
                           fi.revenue, fi.gross_profit, fi.ebit, fi.ebitda,
                           fi.interest_expense, fi.net_income, fi.eps_basic, fi.eps_diluted
                    FROM theeyebeta.fund_income_q fi
                    JOIN theeyebeta.instruments i ON i.id = fi.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    ORDER BY fi.period_end DESC
                    LIMIT :limit
                    """
                ),
                {"ticker": ticker, "limit": limit},
            ).mappings().all()
            return [
                IncomeStatementQ(
                    period_end=_to_date(r.get("period_end")),
                    fiscal_year=int(r["fiscal_year"]) if r.get("fiscal_year") is not None else None,
                    fiscal_quarter=int(r["fiscal_quarter"]) if r.get("fiscal_quarter") is not None else None,
                    revenue=_to_float(r.get("revenue")),
                    gross_profit=_to_float(r.get("gross_profit")),
                    ebit=_to_float(r.get("ebit")),
                    ebitda=_to_float(r.get("ebitda")),
                    interest_expense=_to_float(r.get("interest_expense")),
                    net_income=_to_float(r.get("net_income")),
                    eps_basic=_to_float(r.get("eps_basic")),
                    eps_diluted=_to_float(r.get("eps_diluted")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_income_statements failed")
            raise DatabaseUnavailableError("Unable to fetch income statements") from exc

    def get_balance_sheets(self, ticker: str, limit: int = 12) -> list[BalanceSheetQ]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT fb.period_end, fb.fiscal_year, fb.fiscal_quarter,
                           fb.total_assets, fb.total_liabilities, fb.total_equity,
                           fb.total_debt, fb.cash_and_equivalents, fb.shares_outstanding
                    FROM theeyebeta.fund_balance_q fb
                    JOIN theeyebeta.instruments i ON i.id = fb.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    ORDER BY fb.period_end DESC
                    LIMIT :limit
                    """
                ),
                {"ticker": ticker, "limit": limit},
            ).mappings().all()
            return [
                BalanceSheetQ(
                    period_end=_to_date(r.get("period_end")),
                    fiscal_year=int(r["fiscal_year"]) if r.get("fiscal_year") is not None else None,
                    fiscal_quarter=int(r["fiscal_quarter"]) if r.get("fiscal_quarter") is not None else None,
                    total_assets=_to_float(r.get("total_assets")),
                    total_liabilities=_to_float(r.get("total_liabilities")),
                    total_equity=_to_float(r.get("total_equity")),
                    total_debt=_to_float(r.get("total_debt")),
                    cash_and_equivalents=_to_float(r.get("cash_and_equivalents")),
                    shares_outstanding=_to_float(r.get("shares_outstanding")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_balance_sheets failed")
            raise DatabaseUnavailableError("Unable to fetch balance sheets") from exc

    def get_cash_flows(self, ticker: str, limit: int = 12) -> list[CashFlowQ]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT fc.period_end, fc.fiscal_year, fc.fiscal_quarter,
                           fc.ocf, fc.capex, fc.fcf, fc.working_cap_change, fc.stock_based_comp
                    FROM theeyebeta.fund_cashflow_q fc
                    JOIN theeyebeta.instruments i ON i.id = fc.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    ORDER BY fc.period_end DESC
                    LIMIT :limit
                    """
                ),
                {"ticker": ticker, "limit": limit},
            ).mappings().all()
            return [
                CashFlowQ(
                    period_end=_to_date(r.get("period_end")),
                    fiscal_year=int(r["fiscal_year"]) if r.get("fiscal_year") is not None else None,
                    fiscal_quarter=int(r["fiscal_quarter"]) if r.get("fiscal_quarter") is not None else None,
                    ocf=_to_float(r.get("ocf")),
                    capex=_to_float(r.get("capex")),
                    fcf=_to_float(r.get("fcf")),
                    working_cap_change=_to_float(r.get("working_cap_change")),
                    stock_based_comp=_to_float(r.get("stock_based_comp")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_cash_flows failed")
            raise DatabaseUnavailableError("Unable to fetch cash flows") from exc

    def get_quality_metrics(self, ticker: str, limit: int = 12) -> list[QualityQ]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        f.period_end,
                        EXTRACT(YEAR FROM f.period_end)::int AS fiscal_year,
                        NULL::int AS fiscal_quarter,
                        NULL::numeric AS nopat,
                        NULL::numeric AS invested_capital,
                        NULL::numeric AS roic,
                        f.roe,
                        NULL::numeric AS roa,
                        NULL::numeric AS roce,
                        NULL::numeric AS wacc,
                        NULL::numeric AS cost_of_equity,
                        NULL::numeric AS cost_of_debt,
                        NULL::numeric AS roic_wacc_spread,
                        f.debt_to_equity AS debt_equity,
                        NULL::numeric AS net_debt_ebitda,
                        NULL::numeric AS interest_coverage,
                        NULL::numeric AS ocf,
                        f.free_cash_flow AS fcf
                    FROM theeyebeta.fundamentals f
                    JOIN theeyebeta.instruments i ON i.id = f.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    ORDER BY f.period_end DESC
                    LIMIT :limit
                    """
                ),
                {"ticker": ticker, "limit": limit},
            ).mappings().all()
            return [
                QualityQ(
                    period_end=_to_date(r.get("period_end")),
                    fiscal_year=int(r["fiscal_year"]) if r.get("fiscal_year") is not None else None,
                    fiscal_quarter=int(r["fiscal_quarter"]) if r.get("fiscal_quarter") is not None else None,
                    nopat=_to_float(r.get("nopat")),
                    invested_capital=_to_float(r.get("invested_capital")),
                    roic=_to_float(r.get("roic")),
                    roe=_to_float(r.get("roe")),
                    roa=_to_float(r.get("roa")),
                    roce=_to_float(r.get("roce")),
                    wacc=_to_float(r.get("wacc")),
                    cost_of_equity=_to_float(r.get("cost_of_equity")),
                    cost_of_debt=_to_float(r.get("cost_of_debt")),
                    roic_wacc_spread=_to_float(r.get("roic_wacc_spread")),
                    debt_equity=_to_float(r.get("debt_equity")),
                    net_debt_ebitda=_to_float(r.get("net_debt_ebitda")),
                    interest_coverage=_to_float(r.get("interest_coverage")),
                    ocf=_to_float(r.get("ocf")),
                    fcf=_to_float(r.get("fcf")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_quality_metrics failed")
            raise DatabaseUnavailableError("Unable to fetch quality metrics") from exc

    # ── Indicator time-series ─────────────────────────────────────────────────

    def _date_range_params(self, ticker: str, start: date | None, end: date | None, limit: int) -> tuple[str, dict[str, Any]]:
        parts = ["UPPER(inst.symbol) = UPPER(:ticker)"]
        params: dict[str, Any] = {"ticker": ticker, "limit": limit}
        if start:
            parts.append("i.date >= :start")
            params["start"] = start
        if end:
            parts.append("i.date <= :end")
            params["end"] = end
        return " AND ".join(parts), params

    def get_technical_indicators(self, ticker: str, start: date | None = None, end: date | None = None, limit: int = 252) -> list[TechnicalDay]:
        try:
            where, params = self._date_range_params(ticker, start, end, limit)
            rows = self._session.execute(
                text(
                    f"""
                    SELECT i.date, i.sma_10, i.sma_50, i.sma_200, i.ema_10, i.ema_50, i.ema_200,
                           i.ema_12, i.ema_26, i.rsi_14, i.macd, i.macd_signal, i.macd_hist,
                           i.roc_10, i.roc_20, i.golden_cross_sma, i.death_cross_sma
                    FROM theeyebeta.ind_technical_daily i
                    JOIN theeyebeta.instruments inst ON inst.id = i.instrument_id
                    WHERE {where}
                    ORDER BY i.date DESC
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                TechnicalDay(
                    date=r["date"],
                    sma_10=_to_float(r.get("sma_10")), sma_50=_to_float(r.get("sma_50")), sma_200=_to_float(r.get("sma_200")),
                    ema_10=_to_float(r.get("ema_10")), ema_50=_to_float(r.get("ema_50")), ema_200=_to_float(r.get("ema_200")),
                    ema_12=_to_float(r.get("ema_12")), ema_26=_to_float(r.get("ema_26")),
                    rsi_14=_to_float(r.get("rsi_14")),
                    macd=_to_float(r.get("macd")), macd_signal=_to_float(r.get("macd_signal")), macd_hist=_to_float(r.get("macd_hist")),
                    roc_10=_to_float(r.get("roc_10")), roc_20=_to_float(r.get("roc_20")),
                    golden_cross_sma=bool(r["golden_cross_sma"]) if r.get("golden_cross_sma") is not None else None,
                    death_cross_sma=bool(r["death_cross_sma"]) if r.get("death_cross_sma") is not None else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_technical_indicators failed")
            raise DatabaseUnavailableError("Unable to fetch technical indicators") from exc

    def get_risk_indicators(self, ticker: str, start: date | None = None, end: date | None = None, limit: int = 252) -> list[RiskDay]:
        try:
            where, params = self._date_range_params(ticker, start, end, limit)
            rows = self._session.execute(
                text(
                    f"""
                    SELECT i.date, i.atr_14, i.hist_vol_20d, i.hist_vol_60d, i.beta_sp500_60d,
                           i.worst_drop_1d, i.worst_drop_5d, i.worst_drop_10d,
                           i.max_drawdown_1y, i.max_drawdown_2y,
                           i.sharpe_60d, i.sortino_60d, i.calmar_1y
                    FROM theeyebeta.ind_risk_daily i
                    JOIN theeyebeta.instruments inst ON inst.id = i.instrument_id
                    WHERE {where}
                    ORDER BY i.date DESC
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                RiskDay(
                    date=r["date"],
                    atr_14=_to_float(r.get("atr_14")),
                    hist_vol_20d=_to_float(r.get("hist_vol_20d")), hist_vol_60d=_to_float(r.get("hist_vol_60d")),
                    beta_sp500_60d=_to_float(r.get("beta_sp500_60d")),
                    worst_drop_1d=_to_float(r.get("worst_drop_1d")), worst_drop_5d=_to_float(r.get("worst_drop_5d")), worst_drop_10d=_to_float(r.get("worst_drop_10d")),
                    max_drawdown_1y=_to_float(r.get("max_drawdown_1y")), max_drawdown_2y=_to_float(r.get("max_drawdown_2y")),
                    sharpe_60d=_to_float(r.get("sharpe_60d")), sortino_60d=_to_float(r.get("sortino_60d")), calmar_1y=_to_float(r.get("calmar_1y")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_risk_indicators failed")
            raise DatabaseUnavailableError("Unable to fetch risk indicators") from exc

    def get_valuation_indicators(self, ticker: str, start: date | None = None, end: date | None = None, limit: int = 252) -> list[ValuationDay]:
        try:
            where, params = self._date_range_params(ticker, start, end, limit)
            rows = self._session.execute(
                text(
                    f"""
                    SELECT i.date, i.market_cap, i.enterprise_value,
                           i.pe_ttm, i.forward_pe, i.ps_ttm, i.pb, i.ev_ebitda, i.ev_ebit, i.ev_fcf,
                           i.earnings_yield, i.fcf_yield,
                           i.pct_chg_1w, i.pct_chg_3m, i.pct_chg_6m, i.pct_chg_9m, i.pct_chg_ytd, i.pct_chg_1y
                    FROM theeyebeta.ind_valuation_daily i
                    JOIN theeyebeta.instruments inst ON inst.id = i.instrument_id
                    WHERE {where}
                    ORDER BY i.date DESC
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                ValuationDay(
                    date=r["date"],
                    market_cap=_to_float(r.get("market_cap")), enterprise_value=_to_float(r.get("enterprise_value")),
                    pe_ttm=_to_float(r.get("pe_ttm")), forward_pe=_to_float(r.get("forward_pe")),
                    ps_ttm=_to_float(r.get("ps_ttm")), pb=_to_float(r.get("pb")),
                    ev_ebitda=_to_float(r.get("ev_ebitda")), ev_ebit=_to_float(r.get("ev_ebit")), ev_fcf=_to_float(r.get("ev_fcf")),
                    earnings_yield=_to_float(r.get("earnings_yield")), fcf_yield=_to_float(r.get("fcf_yield")),
                    pct_chg_1w=_to_float(r.get("pct_chg_1w")), pct_chg_3m=_to_float(r.get("pct_chg_3m")),
                    pct_chg_6m=_to_float(r.get("pct_chg_6m")), pct_chg_9m=_to_float(r.get("pct_chg_9m")),
                    pct_chg_ytd=_to_float(r.get("pct_chg_ytd")), pct_chg_1y=_to_float(r.get("pct_chg_1y")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_valuation_indicators failed")
            raise DatabaseUnavailableError("Unable to fetch valuation indicators") from exc

    def get_returns_snapshot(self, ticker: str, start: date | None = None, end: date | None = None, limit: int = 252) -> list[ReturnsDay]:
        try:
            where, params = self._date_range_params(ticker, start, end, limit)
            rows = self._session.execute(
                text(
                    f"""
                    SELECT i.date, i.ret_1w, i.ret_1m, i.ret_3m, i.ret_6m, i.ret_9m, i.ret_ytd, i.ret_1y,
                           i.price_field, i.computed_at
                    FROM theeyebeta.returns_snapshot_daily i
                    JOIN theeyebeta.instruments inst ON inst.id = i.instrument_id
                    WHERE {where}
                    ORDER BY i.date DESC
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                ReturnsDay(
                    date=r["date"],
                    ret_1w=_to_float(r.get("ret_1w")), ret_1m=_to_float(r.get("ret_1m")),
                    ret_3m=_to_float(r.get("ret_3m")), ret_6m=_to_float(r.get("ret_6m")),
                    ret_9m=_to_float(r.get("ret_9m")), ret_ytd=_to_float(r.get("ret_ytd")),
                    ret_1y=_to_float(r.get("ret_1y")),
                    price_field=str(r["price_field"]) if r.get("price_field") else None,
                    computed_at=_to_datetime(r.get("computed_at")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_returns_snapshot failed")
            raise DatabaseUnavailableError("Unable to fetch returns snapshot") from exc

    # ── News ──────────────────────────────────────────────────────────────────

    def get_ticker_news(self, ticker: str, limit: int = 20) -> list[TickerNewsItem]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT n.news_id, n.source, n.title, n.url, n.published_at,
                           n.summary, n.sentiment, n.sentiment_score
                    FROM theeyebeta.ticker_news n
                    JOIN theeyebeta.instruments i ON i.id = n.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    ORDER BY n.published_at DESC
                    LIMIT :limit
                    """
                ),
                {"ticker": ticker, "limit": limit},
            ).mappings().all()
            return [
                TickerNewsItem(
                    news_id=int(r["news_id"]),
                    source=str(r["source"]) if r.get("source") else None,
                    title=str(r["title"]) if r.get("title") else None,
                    url=str(r["url"]) if r.get("url") else None,
                    published_at=_to_datetime(r.get("published_at")),
                    summary=str(r["summary"]) if r.get("summary") else None,
                    sentiment=str(r["sentiment"]) if r.get("sentiment") else None,
                    sentiment_score=_to_float(r.get("sentiment_score")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_ticker_news failed")
            raise DatabaseUnavailableError("Unable to fetch ticker news") from exc

    # ── Admin-only ────────────────────────────────────────────────────────────

    def get_etl_job_states(self) -> list[EtlJobState]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        sync_name AS job_name,
                        started_at AS last_run_at,
                        completed_at::date AS last_successful_date,
                        status,
                        error_message AS last_error
                    FROM theeyebeta.provider_sync_runs
                    ORDER BY started_at DESC
                    """
                )
            ).mappings().all()
            return [
                EtlJobState(
                    job_name=str(r["job_name"]),
                    last_run_at=_to_datetime(r.get("last_run_at")),
                    last_successful_date=_to_date(r.get("last_successful_date")),
                    status=str(r["status"]) if r.get("status") else None,
                    last_error=str(r["last_error"]) if r.get("last_error") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_etl_job_states failed")
            raise DatabaseUnavailableError("Unable to fetch ETL job states") from exc

    def get_engine_status(self) -> list[EngineStatusEntry]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        component_id AS key,
                        state AS value,
                        updated_at
                    FROM theeyebeta.trask_components
                    ORDER BY component_id
                    """
                )
            ).mappings().all()
            return [
                EngineStatusEntry(
                    key=str(r["key"]),
                    value=str(r["value"]) if r.get("value") is not None else None,
                    updated_at=_to_datetime(r.get("updated_at")),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_engine_status failed")
            raise DatabaseUnavailableError("Unable to fetch engine status") from exc

    def get_price_ticks(self, ticker: str, limit: int = 100) -> list[PriceTick]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT pt.tick_id, pt.ts, pt.price, pt.open, pt.high, pt.low, pt.close,
                           pt.volume, pt.source
                    FROM theeyebeta.price_ticks pt
                    JOIN theeyebeta.instruments i ON i.id = pt.instrument_id
                    WHERE UPPER(i.symbol) = UPPER(:ticker)
                    ORDER BY pt.ts DESC
                    LIMIT :limit
                    """
                ),
                {"ticker": ticker, "limit": limit},
            ).mappings().all()
            return [
                PriceTick(
                    tick_id=int(r["tick_id"]),
                    ts=_to_datetime(r.get("ts")),
                    price=_to_float(r.get("price")),
                    open=_to_float(r.get("open")),
                    high=_to_float(r.get("high")),
                    low=_to_float(r.get("low")),
                    close=_to_float(r.get("close")),
                    volume=_to_float(r.get("volume")),
                    source=str(r["source"]) if r.get("source") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_price_ticks failed")
            raise DatabaseUnavailableError("Unable to fetch price ticks") from exc

    # ── Sector / universe ──────────────────────────────────────────────────────

    def get_sector_daily(self, sector: str | None = None, limit: int = 252) -> list[SectorDaily]:
        try:
            where = "WHERE sector = :sector" if sector else ""
            params: dict[str, Any] = {"limit": limit}
            if sector:
                params["sector"] = sector
            rows = self._session.execute(
                text(
                    f"""
                    SELECT sector, as_of_date, n_instruments, avg_return_1d, avg_return_5d, avg_return_30d,
                           median_rsi_14, pct_above_sma_50, pct_above_sma_200, rel_strength_spx_30d,
                           rotation_rank, volume_ratio_20d, top_contributors
                    FROM theeyebeta.sector_daily
                    {where}
                    ORDER BY as_of_date DESC, rotation_rank ASC NULLS LAST
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                SectorDaily(
                    sector=str(r["sector"]),
                    as_of_date=r["as_of_date"],
                    n_instruments=int(r["n_instruments"]),
                    avg_return_1d=_to_float(r.get("avg_return_1d")),
                    avg_return_5d=_to_float(r.get("avg_return_5d")),
                    avg_return_30d=_to_float(r.get("avg_return_30d")),
                    median_rsi_14=_to_float(r.get("median_rsi_14")),
                    pct_above_sma_50=_to_float(r.get("pct_above_sma_50")),
                    pct_above_sma_200=_to_float(r.get("pct_above_sma_200")),
                    rel_strength_spx_30d=_to_float(r.get("rel_strength_spx_30d")),
                    rotation_rank=int(r["rotation_rank"]) if r.get("rotation_rank") is not None else None,
                    volume_ratio_20d=_to_float(r.get("volume_ratio_20d")),
                    top_contributors=list(r.get("top_contributors") or []),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_sector_daily failed")
            raise DatabaseUnavailableError("Unable to fetch sector daily data") from exc

    def get_universe_active(self, min_market_cap: float = 500_000_000, limit: int = 200) -> list[UniverseCapEntry]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT symbol, as_of_date, market_cap, close_price, shares_outstanding, source
                    FROM (
                        SELECT DISTINCT ON (symbol)
                               symbol, as_of_date, market_cap, close_price, shares_outstanding, source
                        FROM theeyebeta.market_cap_daily
                        ORDER BY symbol, as_of_date DESC
                    ) latest
                    WHERE market_cap >= :min_cap
                    ORDER BY market_cap DESC
                    LIMIT :limit
                    """
                ),
                {"min_cap": min_market_cap, "limit": limit},
            ).mappings().all()
            return [
                UniverseCapEntry(
                    symbol=str(r["symbol"]),
                    as_of_date=r["as_of_date"],
                    market_cap=float(r["market_cap"]),
                    close_price=_to_float(r.get("close_price")),
                    shares_outstanding=int(r["shares_outstanding"]) if r.get("shares_outstanding") is not None else None,
                    source=str(r["source"]) if r.get("source") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_universe_active failed")
            raise DatabaseUnavailableError("Unable to fetch universe cap data") from exc

    def get_cap_events(self, since: date | None = None, limit: int = 100) -> list[CapEvent]:
        try:
            where = "WHERE trade_date >= :since" if since else ""
            params: dict[str, Any] = {"limit": limit}
            if since:
                params["since"] = since
            rows = self._session.execute(
                text(
                    f"""
                    SELECT id, trade_date, symbol, event_type, market_cap, prior_market_cap,
                           action_required, universe_updated
                    FROM theeyebeta.audit_cap_events
                    {where}
                    ORDER BY trade_date DESC, id DESC
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                CapEvent(
                    id=int(r["id"]),
                    trade_date=r["trade_date"],
                    symbol=str(r["symbol"]),
                    event_type=str(r["event_type"]),
                    market_cap=_to_float(r.get("market_cap")),
                    prior_market_cap=_to_float(r.get("prior_market_cap")),
                    action_required=str(r["action_required"]) if r.get("action_required") else None,
                    universe_updated=bool(r["universe_updated"]),
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_cap_events failed")
            raise DatabaseUnavailableError("Unable to fetch cap events") from exc
