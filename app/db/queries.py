"""Allowlisted read-only DB query helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger("dataapi.db")


def fetch_active_tickers(session: Session, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch active tickers from a known table shape."""
    try:
        rows = session.execute(
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
        return [dict(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("fetch_active_tickers failed")
        return []


def fetch_latest_snapshot(session: Session, ticker: str) -> dict[str, Any] | None:
    """Fetch latest technical snapshot for one ticker."""
    try:
        row = session.execute(
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
        return dict(row) if row else None
    except SQLAlchemyError:
        logger.exception("fetch_latest_snapshot failed for ticker=%s", ticker)
        return None


def fetch_recent_news(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Fetch recent market news for context building."""
    try:
        rows = session.execute(
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
        return [dict(r) for r in rows]
    except SQLAlchemyError:
        logger.exception("fetch_recent_news failed")
        return []


def db_health(session: Session) -> bool:
    """Simple DB health check."""
    try:
        session.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        logger.exception("db_health check failed")
        return False
