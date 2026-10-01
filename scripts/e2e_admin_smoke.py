#!/usr/bin/env python3
"""Deterministic post-deploy E2E check of the Admin path through DataAPI.

Needs no secrets. Proves, against a running DataAPI:
  1. /health is up and the database is reachable;
  2. the /admin/* gateway reaches Prod admin-service, which demands auth
     (401 on /admin/auth/me and a terminal-data route without credentials);
  3. routes DataAPI deliberately does not expose stay closed (404/405), and
     encoded traversal never reaches admin-service.

With ADMIN_BRIDGE_CLIENT_ID / ADMIN_BRIDGE_CLIENT_SECRET set (the
theeyebeta-prod-admin client), it also checks the data hop admin-service uses:
service token with the bridge's scopes, then /api/v1/admin/engine-status and
/api/v1/market-data/quotes. Secrets are read from the environment and never
printed.

Usage: python scripts/e2e_admin_smoke.py [BASE_URL]   (default http://127.0.0.1:7000)
Exit status 0 = all checks passed.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

import httpx

BRIDGE_SCOPES = ["admin:read", "market:read"]


@dataclass
class Check:
    name: str
    method: str
    path: str
    expect: tuple[int, ...]
    validate: Callable[[httpx.Response], str | None] | None = None


def _db_up(response: httpx.Response) -> str | None:
    return None if response.json().get("database") is True else "database is not reachable"


UNAUTHENTICATED_CHECKS = [
    Check("health + database", "GET", "/health", (200,), _db_up),
    # 401 from admin-service = gateway enabled, upstream reachable, auth required.
    # 503 = gateway disabled; 502/504 = admin-service down.
    Check("gateway reaches admin-service (auth required)", "GET", "/admin/auth/me", (401,)),
    Check("terminal data requires auth", "GET", "/admin/terminal-data/modules", (401,)),
    Check("admin-service health not exposed", "GET", "/admin/health", (404,)),
    Check("admin user creation not exposed", "POST", "/admin/users", (404, 405)),
    Check("admin DataAPI proxy not exposed", "GET", "/admin/dataapi/api/v1/context", (404,)),
    Check("encoded traversal refused", "GET", "/admin/auth/%2e%2e/users", (404,)),
]


def _request(client: httpx.Client, check: Check, headers: dict | None = None) -> tuple[bool, str]:
    try:
        response = client.request(check.method, check.path, headers=headers)
    except httpx.HTTPError as exc:
        return False, f"request failed: {type(exc).__name__}"
    if response.status_code not in check.expect:
        return False, f"HTTP {response.status_code}, expected {'/'.join(map(str, check.expect))}"
    if check.validate:
        problem = check.validate(response)
        if problem:
            return False, problem
    return True, f"HTTP {response.status_code}"


def run(client: httpx.Client, environ: dict[str, str] | None = None, out=sys.stdout) -> bool:
    environ = dict(os.environ) if environ is None else environ
    ok = True
    for check in UNAUTHENTICATED_CHECKS:
        passed, detail = _request(client, check)
        ok &= passed
        print(f"[{'PASS' if passed else 'FAIL'}] {check.name}: {detail}", file=out)

    client_id = environ.get("ADMIN_BRIDGE_CLIENT_ID")
    secret = environ.get("ADMIN_BRIDGE_CLIENT_SECRET")
    if not (client_id and secret):
        print("[SKIP] bridge data hop: ADMIN_BRIDGE_CLIENT_ID/SECRET not set", file=out)
        return ok

    token_response = client.post(
        "/api/v1/auth/service-token", auth=(client_id, secret), json={"requested_scopes": BRIDGE_SCOPES}
    )
    if token_response.status_code != 200:
        print(f"[FAIL] bridge service token: HTTP {token_response.status_code}", file=out)
        return False
    print("[PASS] bridge service token: HTTP 200", file=out)
    headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
    for check in (
        Check("bridge engine status", "GET", "/api/v1/admin/engine-status", (200,)),
        Check("bridge market quotes", "GET", "/api/v1/market-data/quotes?symbols=AAPL", (200,)),
    ):
        passed, detail = _request(client, check, headers)
        ok &= passed
        print(f"[{'PASS' if passed else 'FAIL'}] {check.name}: {detail}", file=out)
    return ok


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("E2E_BASE_URL", "http://127.0.0.1:7000")
    print(f"Admin E2E against {base_url}")
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        return 0 if run(client) else 1


if __name__ == "__main__":
    sys.exit(main())
