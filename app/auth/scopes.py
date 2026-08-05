"""Scope constants and matching helpers."""

from __future__ import annotations

from collections.abc import Iterable


SCOPE_MARKET_READ = "market:read"
SCOPE_SYMBOLS_READ = "symbols:read"
SCOPE_ANALYTICS_READ = "analytics:read"
SCOPE_ADVISOR_READ = "advisor:read"
SCOPE_SIGNALS_READ = "signals:read"
SCOPE_PORTFOLIO_READ = "portfolio:read"
SCOPE_ADMIN_ALL = "admin:*"
SCOPE_ADMIN_READ = "admin:read"
SCOPE_ADMIN_WRITE = "admin:write"
SCOPE_LENS_DELEGATE = "lens:delegate"

# Lens delegated access is intentionally data-only. Administrator, portfolio,
# and advisor scopes never cross a service-to-user delegation boundary.
LENS_DELEGATED_READ_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_MARKET_READ,
        SCOPE_SYMBOLS_READ,
        SCOPE_ANALYTICS_READ,
        SCOPE_SIGNALS_READ,
    }
)


def _scope_matches(granted: str, required: str) -> bool:
    if granted == required:
        return True
    if granted.endswith("*"):
        prefix = granted[:-1]
        return required.startswith(prefix)
    return False


def has_required_scopes(granted_scopes: Iterable[str], required_scopes: Iterable[str]) -> bool:
    """Return True if every required scope is covered by granted scopes."""
    granted = list(granted_scopes)
    for required in required_scopes:
        if not any(_scope_matches(g, required) for g in granted):
            return False
    return True
