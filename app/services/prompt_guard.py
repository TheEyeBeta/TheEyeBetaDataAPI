"""Prompt-injection and unsafe request guardrails."""

from __future__ import annotations

import re

# Patterns that must not appear in user-supplied questions.
# Each entry is compiled with IGNORECASE. Whitespace between tokens is matched
# with \s* so that comment-insertion tricks (DROP/**/TABLE, drop\ntable) are caught.
_RAW_PATTERNS: list[str] = [
    # SQL DDL / DML
    r"drop\s+table",
    r"drop\s+database",
    r"drop\s+schema",
    r"delete\s+from",
    r"truncate\s+(?:table\s+)?\w",
    r"alter\s+table",
    r"insert\s+into",
    r"update\s+\w+\s+set",
    r"grant\s+\w",
    r"revoke\s+\w",
    # Prompt injection attempts
    r"ignore\s+(?:all\s+)?previous\s+instructions?",
    r"disregard\s+(?:all\s+)?previous\s+instructions?",
    r"forget\s+(?:all\s+)?previous\s+instructions?",
    r"you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?(?:different|new|another)",
    r"new\s+instructions?:",
    r"system\s+prompt",
    r"print\s+your\s+(?:system\s+)?prompt",
    r"reveal\s+(?:your\s+)?(?:instructions?|prompt|system)",
    # Credential / secret fishing
    r"show\s+(?:me\s+)?(?:the\s+)?(?:secrets?|passwords?|credentials?|api\s+keys?)",
    r"database\s+password",
    r"db\s+password",
    r"env(?:ironment)?\s+variables?",
    r"\.env\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _RAW_PATTERNS]


def _normalize(text: str) -> str:
    """Strip null bytes, SQL-style comments, and collapse whitespace for uniform matching."""
    text = text.replace("\x00", "")
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", text).strip()


def is_safe_question(question: str) -> bool:
    """Return True if a user question passes basic safety checks."""
    normalized = _normalize(question)
    return not any(pattern.search(normalized) for pattern in _COMPILED)
