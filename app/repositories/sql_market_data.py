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
    InternalJobReceipt,
    MarketNewsItem,
    PortfolioPosition,
    PortfolioValuation,
    SignalRecord,
    TickerSnapshot,
    TickerSummary,
    TradeOrderResult,
)
from app.repositories.interfaces import MarketDataRepository

logger = logging.getLogger("dataapi.repository")


def _to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _to_datetime(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _to_date(value: Any) -> date | None:
    return value if isinstance(value, date) else None


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
                      {f'AND UPPER(t.ticker) = UPPER(:ticker)' if ticker else ''}
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
        normalized = query.strip().rstrip(";").strip()
        upper = normalized.upper()
        if not upper.startswith("SELECT"):
            raise ValidationAppError("Only SELECT queries are allowed")
        forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE", "EXECUTE"}
        for keyword in forbidden:
            if keyword in upper:
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
