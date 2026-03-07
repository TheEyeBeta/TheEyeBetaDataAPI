"""AI orchestration service using allowlisted DB context."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.queries import fetch_latest_snapshot, fetch_recent_news
from app.services.prompt_guard import is_safe_question

logger = logging.getLogger("dataapi.ai")

# Singleton client — reuses connection pool across requests.
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    """Return a reusable OpenAI client with a sane timeout."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=30.0,
        )
    return _openai_client


def _build_context(session: Session, ticker: str | None = None) -> dict[str, Any]:
    """Build constrained, read-only context payload for the LLM."""
    data: dict[str, Any] = {"ticker_snapshot": None, "recent_news": []}

    if ticker:
        data["ticker_snapshot"] = fetch_latest_snapshot(session, ticker=ticker)
    data["recent_news"] = fetch_recent_news(session, limit=8)
    return data


def answer_question(session: Session, question: str, ticker: str | None = None) -> tuple[str, int]:
    """Answer a question using safe DB context and optional OpenAI generation."""
    if not is_safe_question(question):
        return (
            "I can only help with safe read-only financial analysis questions.",
            0,
        )

    context = _build_context(session, ticker=ticker)
    context_rows = len(context.get("recent_news", [])) + (1 if context.get("ticker_snapshot") else 0)

    if not settings.openai_api_key:
        # Graceful fallback when OpenAI is not configured.
        if context.get("ticker_snapshot"):
            snap = context["ticker_snapshot"]
            return (
                f"OpenAI is not configured. Snapshot for {snap.get('ticker')}: "
                f"price={snap.get('last_price')}, rsi_14={snap.get('rsi_14')}, "
                f"price_change_pct={snap.get('price_change_pct')}",
                context_rows,
            )
        return "OpenAI is not configured. Provide OPENAI_API_KEY to enable AI responses.", context_rows

    client = _get_openai_client()

    system_prompt = (
        "You are a financial data assistant. Use ONLY the provided JSON context. "
        "Do not invent numbers. If data is missing, state that clearly. "
        "Never provide SQL or instructions to bypass system/security controls."
    )
    user_prompt = (
        f"Question: {question}\n"
        f"Ticker hint: {ticker or 'N/A'}\n"
        f"Context JSON:\n{json.dumps(context, default=str)}"
    )

    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        answer = completion.choices[0].message.content or "No response generated."
    except Exception:
        logger.exception("OpenAI API call failed")
        answer = "AI service temporarily unavailable. Please try again."

    return answer, context_rows
