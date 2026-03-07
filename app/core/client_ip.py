"""Client IP extraction helpers."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

from app.core.config import settings


def _parse_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _forwarded_ip(request: Request) -> str | None:
    # Cloudflare injects this header with the real client address.
    cf_ip = _parse_ip(request.headers.get("CF-Connecting-IP"))
    if cf_ip:
        return cf_ip

    # Fall back to first address in X-Forwarded-For when enabled.
    xff = request.headers.get("X-Forwarded-For")
    if not xff:
        return None
    first = xff.split(",", 1)[0]
    return _parse_ip(first)


def get_client_ip(request: Request) -> str:
    """Return effective client IP based on trust_proxy_headers policy."""
    if settings.trust_proxy_headers:
        forwarded = _forwarded_ip(request)
        if forwarded:
            return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
