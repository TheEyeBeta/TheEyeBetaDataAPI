"""Prompt-injection and unsafe request guardrails."""

from __future__ import annotations


BLOCKED_PATTERNS = [
    "drop table",
    "delete from",
    "truncate",
    "alter table",
    "insert into",
    "update ",
    "grant ",
    "revoke ",
    "ignore previous instructions",
    "system prompt",
    "show secrets",
    "database password",
]


def is_safe_question(question: str) -> bool:
    """Return True if a user question passes basic safety checks."""
    q = question.lower().strip()
    return not any(pattern in q for pattern in BLOCKED_PATTERNS)
