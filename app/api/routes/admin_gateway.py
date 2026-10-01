"""Manifest-controlled synchronous gateway to the co-located admin service."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.config import settings


@dataclass(frozen=True)
class RouteRule:
    """One approved admin-service route family."""

    prefix: str
    methods: frozenset[str]


_READ = frozenset({"GET"})
_READ_POST = frozenset({"GET", "POST"})
# Methods per family are exactly what TheEyeBetaProd admin-service implements
# (contracts/prod/admin_route_families.json, checked by
# tests/test_admin_gateway_contract.py), minus deliberate denials listed there.
ADMIN_ROUTE_MANIFEST: tuple[RouteRule, ...] = (
    RouteRule("auth/", frozenset({"GET", "POST", "DELETE"})),
    RouteRule("orders", _READ_POST),
    RouteRule("funds", _READ_POST),
    RouteRule("audit", _READ),
    RouteRule("agents", _READ_POST),
    RouteRule("briefings", _READ),
    RouteRule("guard", _READ_POST),
    RouteRule("master-admin", _READ),
    RouteRule("services", _READ_POST),
    RouteRule("backtest", _READ_POST),
    RouteRule("costs", _READ),
    RouteRule("data", _READ),
    RouteRule("desktop", _READ),
    # POST /admin/users (create operator) is deliberately not exposed publicly.
    RouteRule("users", _READ),
    RouteRule("edge", _READ),
    RouteRule("integrations", _READ),
    RouteRule("console", _READ_POST),
    RouteRule("terminal-data", _READ),
    RouteRule("sql/query", frozenset({"POST"})),
    RouteRule("sql/execute", frozenset({"POST"})),
    RouteRule("dataapi/locks", frozenset({"POST"})),
    RouteRule("proposals", _READ_POST),
    RouteRule("ops", _READ),
    RouteRule("workers", _READ_POST),
    RouteRule("trask", _READ_POST),
    RouteRule("alerts", _READ_POST),
    RouteRule("prelive", _READ),
    RouteRule("trading", _READ_POST),
    RouteRule("timers", _READ_POST),
    RouteRule("risk", _READ_POST),
    RouteRule("compliance", _READ),
    RouteRule("oms", _READ_POST),
    RouteRule("broker", _READ),
    RouteRule("macro", _READ_POST),
)

# Anything outside plain path characters is refused before routing: "\\"
# (alternate separator), "%" (double encoding survives one decode), and control
# characters. "?" and "#" are still percent-encoded on the way out (see
# _upstream_url) so they can never truncate or re-target the upstream path.
_FORBIDDEN_PATH_CHARS = re.compile(r"[\\%\x00-\x1f\x7f]")

_FORWARDED_HEADERS = frozenset(
    {
        "authorization",
        "content-type",
        "cookie",
        "x-confirm",
        "x-csrf-token",
        "x-dry-run",
        "x-idempotency-key",
        "x-request-id",
    }
)

router = APIRouter(prefix="/admin", tags=["admin-gateway"])


def _normalized_admin_path(path: str) -> str | None:
    """Return the path without outer slashes, or None if it is not a plain path."""
    normalized = path.strip("/")
    if not normalized or _FORBIDDEN_PATH_CHARS.search(normalized):
        return None
    if any(segment in {"", ".", ".."} for segment in normalized.split("/")):
        return None
    return normalized


def _upstream_url(normalized_path: str) -> str:
    """Build the admin-service URL with every path segment percent-encoded."""
    return f"{settings.admin_service_url.rstrip('/')}/admin/{quote(normalized_path, safe='/')}"


def is_allowed_admin_route(path: str, method: str) -> bool:
    """Return whether a normalized admin path/method is in the gateway manifest."""
    normalized = _normalized_admin_path(path)
    if normalized is None:
        return False
    upper_method = method.upper()
    for rule in ADMIN_ROUTE_MANIFEST:
        prefix = rule.prefix.strip("/")
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return upper_method in rule.methods
    return False


def _requires_idempotency_key(path: str, method: str) -> bool:
    """Require idempotency for proxied state changes except authentication lifecycle routes."""
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and not path.startswith("auth/")


def _safe_headers(request: Request) -> dict[str, str]:
    headers = {
        key.lower(): value
        for key, value in request.headers.items()
        if key.lower() in _FORWARDED_HEADERS
    }
    # Keys are lower-cased so this only fills a missing ID, never duplicates one.
    headers.setdefault("x-request-id", getattr(request.state, "request_id", ""))
    return {key: value for key, value in headers.items() if value}


# Opaque catch-all proxy: excluded from OpenAPI (one function across five
# methods also produced duplicate operation IDs).
@router.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
)
async def proxy_admin_request(path: str, request: Request) -> Response:
    """Forward one approved request without interpreting administrator identity."""
    if not settings.admin_gateway_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin gateway disabled")
    if not is_allowed_admin_route(path, request.method):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin route is not exposed")
    normalized_path = _normalized_admin_path(path) or ""
    if _requires_idempotency_key(normalized_path, request.method) and not request.headers.get(
        "X-Idempotency-Key"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="X-Idempotency-Key header is required for admin mutations",
        )
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.admin_gateway_max_body_bytes:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Request too large")
    body = await request.body()
    if len(body) > settings.admin_gateway_max_body_bytes:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Request too large")
    target = _upstream_url(normalized_path)
    try:
        async with httpx.AsyncClient(timeout=settings.admin_gateway_timeout_seconds) as client:
            upstream = await client.request(
                request.method,
                target,
                params=request.query_params.multi_items(),
                content=body,
                headers=_safe_headers(request),
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Admin command outcome is unknown; retry with the same idempotency key",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin service unavailable",
        ) from exc
    response_headers: dict[str, str] = {}
    for name in ("content-type", "x-request-id"):
        if value := upstream.headers.get(name):
            response_headers[name] = value
    response_headers["Cache-Control"] = "no-store"
    response = Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
    for cookie in upstream.headers.get_list("set-cookie"):
        response.headers.append("set-cookie", cookie)
    return response
