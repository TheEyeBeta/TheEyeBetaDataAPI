"""Context routes for constrained DB-backed AI context."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import AuthContext, require_auth
from app.db.queries import fetch_active_tickers, fetch_latest_snapshot, fetch_recent_news
from app.db.session import get_db_session

router = APIRouter()


@router.get("/api/v1/context")
def get_context(
    ticker: str | None = Query(default=None, description="Optional ticker for focused context"),
    ticker_limit: int = Query(default=25, ge=1, le=200),
    news_limit: int = Query(default=10, ge=1, le=50),
    _: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    """Get safe context payload for an external AI client."""
    session = get_db_session()
    try:
        payload: dict[str, Any] = {
            "tickers": fetch_active_tickers(session, limit=ticker_limit),
            "news": fetch_recent_news(session, limit=news_limit),
        }
        if ticker:
            payload["ticker_snapshot"] = fetch_latest_snapshot(session, ticker=ticker)
        return payload
    finally:
        session.close()
