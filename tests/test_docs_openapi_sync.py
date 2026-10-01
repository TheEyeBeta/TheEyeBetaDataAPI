"""docs/API_REFERENCE.md must document exactly the routes the OpenAPI schema serves.

Each documented endpoint is a heading of the form ### `METHOD /path`; aliases
may follow on the same heading, e.g. (alias: `GET /other`).
The /admin/* gateway is documented by family in its own section and checked
against Prod in tests/test_admin_gateway_contract.py instead.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/[^`]*)`")


def _documented() -> set[tuple[str, str]]:
    text = (ROOT / "docs" / "API_REFERENCE.md").read_text(encoding="utf-8")
    headings = (line for line in text.splitlines() if line.startswith("### "))
    return {(method, path) for line in headings for method, path in ENDPOINT.findall(line)}


def _served() -> set[tuple[str, str]]:
    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        if path.startswith("/api/") or path == "/health"
        for method in operations
    }


def test_every_served_route_is_documented() -> None:
    missing = sorted(_served() - _documented())
    assert not missing, f"add to docs/API_REFERENCE.md: {missing}"


def test_every_documented_route_is_served() -> None:
    stale = sorted(_documented() - _served())
    assert not stale, f"documented but not served (remove or fix): {stale}"


def test_readme_route_table_mentions_every_route_family() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    families = {path.split("/")[3] for _, path in _served() if path.startswith("/api/v1/")}
    missing = sorted(family for family in families if f"/api/v1/{family}" not in readme)
    assert not missing, f"README.md route table is missing: {missing}"
