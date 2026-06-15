"""SQLAlchemy repository implementation for market data."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.errors import DatabaseUnavailableError, ValidationAppError
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
    Industry,
    IncomeStatementQ,
    InternalJobReceipt,
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
from app.repositories.interfaces import MarketDataRepository

logger = logging.getLogger("dataapi.repository")


def _to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _to_datetime(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _to_date(value: Any) -> date | None:
    return value if isinstance(value, date) else None


# Server-side allowlist of parameterised admin queries.
# Only :limit is accepted as a parameter; no user-supplied SQL ever reaches the DB.
_CURATED_ADMIN_QUERIES: dict[str, str] = {
    "all_tickers": (
        "SELECT ticker, company_name, is_active FROM tickers ORDER BY ticker LIMIT :limit"
    ),
    "latest_prices": (
        "SELECT t.ticker, ls.last_price, ls.price_change_pct, ls.rsi_14, ls.updated_at"
        " FROM latest_snapshot ls"
        " JOIN tickers t ON t.ticker_id = ls.ticker_id"
        " ORDER BY ls.updated_at DESC LIMIT :limit"
    ),
    "latest_signals": (
        "SELECT t.ticker, ls.latest_signal, ls.signal_confidence,"
        " ls.signal_strategy, ls.signal_ts"
        " FROM latest_snapshot ls"
        " JOIN tickers t ON t.ticker_id = ls.ticker_id"
        " WHERE ls.latest_signal IS NOT NULL"
        " ORDER BY ls.signal_ts DESC LIMIT :limit"
    ),
    "recent_trades": (
        "SELECT * FROM paper_trades ORDER BY created_at DESC LIMIT :limit"
    ),
    "portfolio": (
        "SELECT * FROM portfolio_positions ORDER BY quantity DESC LIMIT :limit"
    ),
    "valuation": (
        "SELECT * FROM portfolio_valuation ORDER BY valuation_date DESC LIMIT :limit"
    ),
    "command_log": (
        "SELECT command_id, command_type, status, operator_id, created_at"
        " FROM trask_command_log ORDER BY created_at DESC LIMIT :limit"
    ),
    "market_news": (
        "SELECT * FROM market_news ORDER BY published_at DESC LIMIT :limit"
    ),
    "heartbeats": (
        "SELECT * FROM engine_worker_heartbeats ORDER BY worker_name LIMIT :limit"
    ),
    "table_stats": (
        "SELECT schemaname, relname AS tablename, n_live_tup AS row_count"
        " FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT :limit"
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
                    SELECT ticker, company_name
                    FROM tickers
                    WHERE is_active = true
                    ORDER BY ticker
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
                    SELECT ticker, company_name
                    FROM tickers
                    WHERE is_active = true
                      AND (UPPER(ticker) LIKE UPPER(:prefix) OR UPPER(company_name) LIKE UPPER(:name_like))
                    ORDER BY ticker
                    LIMIT :limit
                    """
                ),
                {"prefix": f"{query}%", "name_like": f"%{query}%", "limit": limit},
            ).mappings().all()
            return [TickerSummary(ticker=str(row["ticker"]), company_name=str(row["company_name"])) for row in rows]
        except SQLAlchemyError as exc:
            logger.exception("search_symbols failed")
            raise DatabaseUnavailableError("Unable to search symbols") from exc

    def get_latest_snapshot(self, ticker: str) -> TickerSnapshot | None:
        try:
            row = self._session.execute(
                text(
                    """
                    SELECT
                        t.ticker,
                        t.company_name,
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
                    FROM latest_snapshot ls
                    JOIN tickers t ON t.ticker_id = ls.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
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
                    FROM market_news
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
                        t.ticker,
                        ls.signal_strategy AS strategy_name,
                        ls.latest_signal AS signal,
                        ls.signal_confidence AS confidence,
                        ls.last_price AS entry_price,
                        NULL::numeric AS target_price,
                        NULL::numeric AS stop_loss,
                        ls.signal_ts AS ts
                    FROM latest_snapshot ls
                    JOIN tickers t ON t.ticker_id = ls.ticker_id
                    WHERE ls.latest_signal IS NOT NULL
                      {'AND UPPER(t.ticker) = UPPER(:ticker)' if ticker else ''}
                    ORDER BY ls.signal_ts DESC NULLS LAST, t.ticker ASC
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
                        valuation_date,
                        total_value,
                        cash_balance,
                        positions_value,
                        total_cost_basis,
                        unrealized_pnl,
                        realized_pnl,
                        currency_code,
                        created_at
                    FROM portfolio_valuation
                    ORDER BY valuation_date DESC, created_at DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if not row:
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
                        t.ticker,
                        t.company_name,
                        p.quantity,
                        p.average_cost,
                        ls.last_price,
                        (p.quantity * ls.last_price) AS market_value,
                        (p.quantity * (ls.last_price - p.average_cost)) AS unrealized_pnl,
                        p.last_updated
                    FROM portfolio_positions p
                    JOIN tickers t ON t.ticker_id = p.ticker_id
                    LEFT JOIN latest_snapshot ls ON ls.ticker_id = p.ticker_id
                    ORDER BY market_value DESC NULLS LAST, t.ticker
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
        normalized_symbol = symbol.strip().upper()
        normalized_side = side.strip().lower()
        trade_type = normalized_side.upper()
        if normalized_side not in {"buy", "sell"}:
            raise ValidationAppError("side must be buy or sell")
        if quantity <= 0:
            raise ValidationAppError("quantity must be greater than zero")

        try:
            existing = self._session.execute(
                text(
                    """
                    SELECT result, created_at
                    FROM trask_command_log
                    WHERE command_type = 'api_trade_order'
                      AND operator_id = :operator_id
                      AND params ->> 'idempotency_key' = :idempotency_key
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"operator_id": operator_subject, "idempotency_key": idempotency_key},
            ).mappings().first()
            if existing:
                raw_result = existing.get("result")
                result = raw_result if isinstance(raw_result, dict) else {}
                order_ref = str(result.get("order_ref", "unknown"))
                executed_price = _to_float(result.get("executed_price")) or 0.0
                total_cost = _to_float(result.get("total_cost")) or 0.0
                return TradeOrderResult(
                    order_ref=order_ref,
                    status="accepted",
                    idempotency_key=idempotency_key,
                    symbol=normalized_symbol,
                    side=normalized_side,
                    quantity=quantity,
                    executed_price=executed_price,
                    total_cost=total_cost,
                    accepted_at=_to_datetime(existing.get("created_at")),
                    idempotent_replay=True,
                )

            ticker_row = self._session.execute(
                text(
                    """
                    SELECT t.ticker_id, ls.last_price
                    FROM tickers t
                    LEFT JOIN latest_snapshot ls ON ls.ticker_id = t.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
                    LIMIT 1
                    """
                ),
                {"ticker": normalized_symbol},
            ).mappings().first()
            if not ticker_row:
                raise ValidationAppError(f"Unknown symbol: {normalized_symbol}")

            latest_price = _to_float(ticker_row.get("last_price"))
            execution_price = float(limit_price) if limit_price is not None else latest_price
            if execution_price is None:
                raise ValidationAppError(
                    f"Cannot place order for {normalized_symbol}: no latest price available and no limit_price provided"
                )

            total_cost = float(quantity) * execution_price
            trade_row = self._session.execute(
                text(
                    """
                    INSERT INTO paper_trades (
                        ticker_id,
                        trade_date,
                        trade_type,
                        quantity,
                        price,
                        fees,
                        slippage_bps,
                        total_cost,
                        notes,
                        created_at
                    )
                    VALUES (
                        :ticker_id,
                        NOW(),
                        :trade_type,
                        :quantity,
                        :price,
                        0,
                        0,
                        :total_cost,
                        :notes,
                        NOW()
                    )
                    RETURNING trade_id, trade_date
                    """
                ),
                {
                    "ticker_id": ticker_row["ticker_id"],
                    "trade_type": trade_type,
                    "quantity": quantity,
                    "price": execution_price,
                    "total_cost": total_cost,
                    "notes": f"operator={operator_subject};idempotency_key={idempotency_key}",
                },
            ).mappings().first()
            if not trade_row:
                raise DatabaseUnavailableError("Trade order insert did not return trade id")

            order_ref = f"paper-trade-{trade_row['trade_id']}"
            command_id = str(uuid.uuid4())
            params_json = json.dumps(
                {
                    "idempotency_key": idempotency_key,
                    "symbol": normalized_symbol,
                    "side": normalized_side,
                    "quantity": quantity,
                }
            )
            result_json = json.dumps(
                {
                    "order_ref": order_ref,
                    "executed_price": execution_price,
                    "total_cost": total_cost,
                }
            )
            self._session.execute(
                text(
                    """
                    INSERT INTO trask_command_log (
                        command_id,
                        command_type,
                        target_type,
                        target_id,
                        operator_id,
                        status,
                        params,
                        result,
                        created_at,
                        completed_at
                    )
                    VALUES (
                        :command_id,
                        'api_trade_order',
                        'paper_trade',
                        :target_id,
                        :operator_id,
                        'completed',
                        CAST(:params AS JSONB),
                        CAST(:result AS JSONB),
                        NOW(),
                        NOW()
                    )
                    """
                ),
                {
                    "command_id": command_id,
                    "target_id": str(trade_row["trade_id"]),
                    "operator_id": operator_subject,
                    "params": params_json,
                    "result": result_json,
                },
            )
            self._session.commit()
            return TradeOrderResult(
                order_ref=order_ref,
                status="accepted",
                idempotency_key=idempotency_key,
                symbol=normalized_symbol,
                side=normalized_side,
                quantity=quantity,
                executed_price=execution_price,
                total_cost=total_cost,
                accepted_at=_to_datetime(trade_row.get("trade_date")),
                idempotent_replay=False,
            )
        except ValidationAppError:
            self._session.rollback()
            raise
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.exception("create_trade_order failed")
            raise DatabaseUnavailableError("Unable to create trade order") from exc

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
                    FROM trask_recent_events
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
            tables = [
                "tickers", "latest_snapshot", "market_news", "paper_trades",
                "portfolio_positions", "portfolio_valuation",
                "trask_command_log", "trask_recent_events",
            ]
            results = []
            for table in tables:
                try:
                    row = self._session.execute(
                        text(f"SELECT COUNT(*) AS cnt FROM {table}")  # noqa: S608
                    ).mappings().first()
                    results.append({"table": table, "row_count": int(row["cnt"]) if row else 0})
                except SQLAlchemyError:
                    results.append({"table": table, "row_count": -1, "error": "table not found"})
                    self._session.rollback()
            return results
        except SQLAlchemyError as exc:
            logger.exception("get_table_row_counts failed")
            raise DatabaseUnavailableError("Unable to fetch table counts") from exc

    def get_engine_worker_heartbeats(self) -> list[dict[str, Any]]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        worker_name,
                        status,
                        last_heartbeat,
                        EXTRACT(EPOCH FROM (NOW() - last_heartbeat))::int AS seconds_ago,
                        metadata
                    FROM engine_worker_heartbeats
                    ORDER BY worker_name
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
        import re

        normalized = query.strip().rstrip(";").strip()

        # Reject embedded semicolons (multi-statement attacks).
        if ";" in normalized:
            raise ValidationAppError("Query must be a single statement")

        # Strip inline comments before keyword checks to prevent comment-based bypasses.
        stripped = re.sub(r"--[^\n]*", " ", normalized)
        stripped = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.DOTALL)
        # Collapse whitespace so keyword checks work on canonical form.
        canonical = re.sub(r"\s+", " ", stripped).strip().upper()

        if not canonical.startswith("SELECT"):
            raise ValidationAppError("Only SELECT queries are allowed")

        # WITH blocks enable CTEs that can wrap any DDL/DML — block them entirely.
        forbidden = {
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE",
            "GRANT", "REVOKE", "EXECUTE", "EXEC", "CALL", "COPY", "LOAD",
            "IMPORT", "EXPORT", "WITH", "SET", "SHOW", "EXPLAIN", "ANALYZE",
            "VACUUM", "REINDEX", "CLUSTER", "COMMENT", "NOTIFY", "LISTEN",
            "UNLISTEN", "CHECKPOINT", "DO",
        }
        for keyword in forbidden:
            # Match whole words only to avoid false positives (e.g. "NETWORK" containing "SET").
            if re.search(rf"\b{re.escape(keyword)}\b", canonical):
                raise ValidationAppError(f"Query contains forbidden keyword: {keyword}")

        try:
            limited_query = f"SELECT * FROM ({normalized}) AS _q LIMIT :_limit"
            rows = self._session.execute(text(limited_query), {"_limit": limit}).mappings().all()
            return [
                {k: (str(v) if v is not None else None) for k, v in dict(row).items()}
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("execute_readonly_query failed")
            raise DatabaseUnavailableError(f"Query failed: {exc}") from exc

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
                text("SELECT COUNT(*) AS cnt FROM tickers WHERE is_active = true")
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
                text("SELECT country_code, country_name, default_timezone FROM countries ORDER BY country_name")
            ).mappings().all()
            return [Country(country_code=str(r["country_code"]), country_name=str(r["country_name"]), default_timezone=str(r["default_timezone"]) if r.get("default_timezone") else None) for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_countries failed")
            raise DatabaseUnavailableError("Unable to fetch countries") from exc

    def get_currencies(self) -> list[Currency]:
        try:
            rows = self._session.execute(
                text("SELECT currency_code, currency_name, symbol FROM currencies ORDER BY currency_code")
            ).mappings().all()
            return [Currency(currency_code=str(r["currency_code"]), currency_name=str(r["currency_name"]), symbol=str(r["symbol"]) if r.get("symbol") else None) for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_currencies failed")
            raise DatabaseUnavailableError("Unable to fetch currencies") from exc

    def get_exchanges(self) -> list[Exchange]:
        try:
            rows = self._session.execute(
                text("SELECT exchange_id, name, mic_code, country_code, timezone FROM exchanges ORDER BY name")
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
                text("SELECT sector_id, sector_name FROM sectors ORDER BY sector_name")
            ).mappings().all()
            return [Sector(sector_id=int(r["sector_id"]), sector_name=str(r["sector_name"])) for r in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_sectors failed")
            raise DatabaseUnavailableError("Unable to fetch sectors") from exc

    def get_industries(self, sector_id: int | None = None) -> list[Industry]:
        try:
            if sector_id is not None:
                rows = self._session.execute(
                    text("SELECT industry_id, sector_id, industry_name FROM industries WHERE sector_id = :sid ORDER BY industry_name"),
                    {"sid": sector_id},
                ).mappings().all()
            else:
                rows = self._session.execute(
                    text("SELECT industry_id, sector_id, industry_name FROM industries ORDER BY industry_name")
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
                text(f"SELECT calendar_date, is_trading_day, market_name, holiday_name, notes FROM trading_calendar {where} ORDER BY calendar_date DESC LIMIT :limit"),  # noqa: S608
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
                        t.ticker, t.company_name, t.asset_type, t.country_code, t.timezone,
                        t.currency_code, t.is_active,
                        p.sector_id, p.industry_id, p.website, p.description,
                        p.founded_year, p.employees
                    FROM tickers t
                    LEFT JOIN ticker_profile p ON p.ticker_id = t.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
                    """
                ),
                {"ticker": ticker},
            ).mappings().first()
            if not row:
                return None
            id_rows = self._session.execute(
                text(
                    """
                    SELECT ti.id_type, ti.id_value
                    FROM ticker_identifiers ti
                    JOIN tickers t ON t.ticker_id = ti.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
                    """
                ),
                {"ticker": ticker},
            ).mappings().all()
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
                identifiers=[{"id_type": str(r["id_type"]), "id_value": str(r["id_value"])} for r in id_rows],
            )
        except SQLAlchemyError as exc:
            logger.exception("get_ticker_detail failed")
            raise DatabaseUnavailableError("Unable to fetch ticker detail") from exc

    def get_price_history(self, ticker: str, start: date | None = None, end: date | None = None, limit: int = 252) -> list[PriceDay]:
        try:
            where_parts = ["UPPER(t.ticker) = UPPER(:ticker)"]
            params: dict[str, Any] = {"ticker": ticker, "limit": limit}
            if start:
                where_parts.append("p.date >= :start")
                params["start"] = start
            if end:
                where_parts.append("p.date <= :end")
                params["end"] = end
            where = " AND ".join(where_parts)
            rows = self._session.execute(
                text(
                    f"""
                    SELECT p.date, p.open, p.high, p.low, p.close, p.adj_close, p.volume, p.vwap
                    FROM price_daily p
                    JOIN tickers t ON t.ticker_id = p.ticker_id
                    WHERE {where}
                    ORDER BY p.date DESC
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
                    SELECT ca.action_id, ca.action_date, ca.action_type,
                           ca.split_ratio, ca.dividend_amount, ca.notes
                    FROM corporate_actions ca
                    JOIN tickers t ON t.ticker_id = ca.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
                    ORDER BY ca.action_date DESC
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
                    FROM fundamentals_company f
                    JOIN tickers t ON t.ticker_id = f.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
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
        return "UPPER(t.ticker) = UPPER(:ticker)", {"ticker": ticker, "limit": limit}

    def get_income_statements(self, ticker: str, limit: int = 12) -> list[IncomeStatementQ]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT fi.period_end, fi.fiscal_year, fi.fiscal_quarter,
                           fi.revenue, fi.gross_profit, fi.ebit, fi.ebitda,
                           fi.interest_expense, fi.net_income, fi.eps_basic, fi.eps_diluted
                    FROM fund_income_q fi
                    JOIN tickers t ON t.ticker_id = fi.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
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
                    FROM fund_balance_q fb
                    JOIN tickers t ON t.ticker_id = fb.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
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
                    FROM fund_cashflow_q fc
                    JOIN tickers t ON t.ticker_id = fc.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
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
                    SELECT iq.period_end, iq.fiscal_year, iq.fiscal_quarter,
                           iq.nopat, iq.invested_capital, iq.roic, iq.roe, iq.roa, iq.roce,
                           iq.wacc, iq.cost_of_equity, iq.cost_of_debt, iq.roic_wacc_spread,
                           iq.debt_equity, iq.net_debt_ebitda, iq.interest_coverage, iq.ocf, iq.fcf
                    FROM ind_quality_q iq
                    JOIN tickers t ON t.ticker_id = iq.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
                    ORDER BY iq.period_end DESC
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
        parts = ["UPPER(t.ticker) = UPPER(:ticker)"]
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
                    FROM ind_technical_daily i
                    JOIN tickers t ON t.ticker_id = i.ticker_id
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
                    FROM ind_risk_daily i
                    JOIN tickers t ON t.ticker_id = i.ticker_id
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
                    FROM ind_valuation_daily i
                    JOIN tickers t ON t.ticker_id = i.ticker_id
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
                    FROM returns_snapshot_daily i
                    JOIN tickers t ON t.ticker_id = i.ticker_id
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
                    FROM news n
                    JOIN tickers t ON t.ticker_id = n.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
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
                    SELECT job_name, last_run_at, last_successful_date, status, last_error
                    FROM etl_job_state
                    ORDER BY job_name
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
                text("SELECT key, value, updated_at FROM engine_status ORDER BY key")
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
                    FROM price_ticks pt
                    JOIN tickers t ON t.ticker_id = pt.ticker_id
                    WHERE UPPER(t.ticker) = UPPER(:ticker)
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

    def enqueue_internal_job(
        self,
        *,
        operator_subject: str,
        command_type: str,
        params: dict[str, Any],
    ) -> InternalJobReceipt:
        try:
            command_id = str(uuid.uuid4())
            row = self._session.execute(
                text(
                    """
                    INSERT INTO trask_command_log (
                        command_id,
                        command_type,
                        target_type,
                        target_id,
                        operator_id,
                        status,
                        params,
                        created_at
                    )
                    VALUES (
                        :command_id,
                        :command_type,
                        'internal_job',
                        :target_id,
                        :operator_id,
                        'accepted',
                        CAST(:params AS JSONB),
                        NOW()
                    )
                    RETURNING command_id::text AS command_id, status, created_at
                    """
                ),
                {
                    "command_id": command_id,
                    "command_type": command_type,
                    "target_id": command_type,
                    "operator_id": operator_subject,
                    "params": json.dumps(params),
                },
            ).mappings().first()
            self._session.commit()
            if not row:
                raise DatabaseUnavailableError("Job enqueue did not return command metadata")
            return InternalJobReceipt(
                command_id=str(row["command_id"]),
                status=str(row["status"]),
                command_type=command_type,
                created_at=_to_datetime(row.get("created_at")),
            )
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.exception("enqueue_internal_job failed")
            raise DatabaseUnavailableError("Unable to enqueue internal job") from exc
