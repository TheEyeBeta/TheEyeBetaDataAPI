"""AI orchestration service using allowlisted DB context."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.core.config import settings
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


def answer_question(question: str, ticker: str | None, context: dict[str, Any]) -> str:
    """Answer a question using provided safe context and optional OpenAI generation."""
    if not is_safe_question(question):
        return "I can only help with safe read-only financial analysis questions."

    if not settings.openai_api_key:
        # Graceful fallback when OpenAI is not configured.
        if context.get("ticker_snapshot"):
            snap = context["ticker_snapshot"]
            return (
                f"OpenAI is not configured. Snapshot for {snap.get('ticker')}: "
                f"price={snap.get('last_price')}, rsi_14={snap.get('rsi_14')}, "
                f"price_change_pct={snap.get('price_change_pct')}",
            )
        return "OpenAI is not configured. Provide OPENAI_API_KEY to enable AI responses."

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

    return answer
