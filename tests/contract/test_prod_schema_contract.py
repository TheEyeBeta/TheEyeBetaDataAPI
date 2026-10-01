"""Every data endpoint, served from TheEyeBetaProd's real schema as api_service.

Rows come from tests/contract/seed.sql. Calls mirror the real consumers:
- Lens (AI-Financial-Advisor backend/websearch_service/app/services/dataapi_client.py):
  HTTP Basic -> /api/v1/auth/service-token with requested_scopes [] , same paths/params.
- TheEyeBetaProd admin-service (services/admin_service/api/dataapi.py, terminal.py):
  token with its seven default scopes, GET proxied paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.contract.conftest import ContractEnv, ServiceCredential

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts" / "prod"


def _token(client: TestClient, cred: ServiceCredential, requested: list[str]) -> str:
    response = client.post(
        "/api/v1/auth/service-token",
        auth=(cred.client_id, cred.secret),
        json={"requested_scopes": requested},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Fields both consumers read.
    assert body["access_token"]
    assert isinstance(body["expires_minutes"], int) and body["expires_minutes"] > 0
    assert "refresh_token" not in body  # neither consumer opts in to refresh
    return body["access_token"]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def lens_token(client: TestClient, contract_env: ContractEnv) -> str:
    return _token(client, contract_env.lens, [])  # Lens sends SERVICE_REQUESTED_SCOPES="" by default


@pytest.fixture(scope="module")
def bridge_token(client: TestClient, contract_env: ContractEnv) -> str:
    return _token(client, contract_env.admin_bridge, list(contract_env.admin_bridge.scopes))


def _get(client: TestClient, token: str, path: str, params: dict | None = None):
    return client.get(path, params=params or {}, headers={"Authorization": f"Bearer {token}"})


# --------------------------------------------------------------------------
# Lens: endpoints within its granted scopes must serve real data.
# --------------------------------------------------------------------------

LENS_OK = [
    ("/api/v1/market-data/quotes", {"symbols": "AAPL,MSFT"}, "quotes"),
    ("/api/v1/symbols/search", {"q": "AAP", "limit": 25}, "results"),
    ("/api/v1/context", {"ticker_limit": 10, "news_limit": 8, "ticker": "AAPL"}, "tickers"),
    ("/api/v1/advisor/context", {"ticker": "AAPL"}, "tickers"),
    ("/api/v1/news/market", {"limit": 15}, "news"),
    ("/api/v1/tickers/AAPL/price-history", {"limit": 30}, None),
    ("/api/v1/tickers/AAPL/corporate-actions", {"limit": 50}, None),
    ("/api/v1/reference/countries", None, None),
    ("/api/v1/reference/currencies", None, None),
    ("/api/v1/reference/exchanges", None, None),
    ("/api/v1/reference/sectors", None, None),
    ("/api/v1/reference/industries", None, None),
    ("/api/v1/reference/calendar", {"limit": 90}, None),
]


@pytest.mark.parametrize(("path", "params", "key"), LENS_OK, ids=[p for p, _, _ in LENS_OK])
def test_lens_endpoint_serves_prod_schema(client, lens_token, path, params, key) -> None:
    response = _get(client, lens_token, path, params)
    assert response.status_code == 200, response.text
    if key:
        assert response.json()[key], f"{path}: expected seeded rows in '{key}'"


def test_lens_quotes_carry_prod_view_values(client, lens_token) -> None:
    quotes = _get(client, lens_token, "/api/v1/market-data/quotes", {"symbols": "AAPL"}).json()["quotes"]
    assert quotes and quotes[0]["ticker"] == "AAPL"


# Lens calls these too, but they need analytics:read, which Lens does not hold
# (live IAM row per docs/IAM_CONSUMER_INVENTORY.md). Recorded so a scope change
# is a deliberate decision; the SQL itself is exercised with the bridge token.
LENS_SCOPE_GAP = [
    "/api/v1/analytics/snapshots/AAPL",
    "/api/v1/tickers/AAPL/fundamentals",
    "/api/v1/financials/AAPL/income",
    "/api/v1/indicators/AAPL/technical",
]


@pytest.mark.parametrize("path", LENS_SCOPE_GAP)
def test_lens_calls_outside_its_scopes_are_403(client, lens_token, path) -> None:
    response = _get(client, lens_token, path)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --------------------------------------------------------------------------
# Every other data route with a token that holds the scope.
# --------------------------------------------------------------------------

BRIDGE_OK = [
    ("/api/v1/analytics/snapshots/AAPL", None),
    ("/api/v1/tickers/AAPL", None),
    ("/api/v1/tickers/AAPL/fundamentals", None),
    ("/api/v1/financials/AAPL/quality", {"limit": 12}),
    ("/api/v1/indicators/AAPL/technical", {"limit": 30}),
    ("/api/v1/signals/latest", {"limit": 20}),
    ("/api/v1/signals/latest", {"limit": 20, "ticker": "AAPL"}),
    ("/api/v1/symbols/resolve", {"symbol": "AAPL"}),
    ("/api/v1/sectors/daily", None),
    ("/api/v1/universe/active", {"min_market_cap": 0}),
    ("/api/v1/universe/cap-events", None),
    ("/api/v1/macro/series", None),
    ("/api/v1/macro/series/DGS10", None),
    ("/api/v1/macro/latest", {"codes": "DGS10,UNRATE"}),
    ("/api/v1/fixed-income/regime", None),
    ("/api/v1/fixed-income/history", None),
    ("/api/v1/fixed-income/signals", None),
    ("/api/v1/portfolio/state", {"owner_subject": "contract-user"}),
    ("/api/v1/data/tables", None),
    ("/api/v1/data/tables/instruments/columns", None),
    ("/api/v1/data/tables/instruments/rows", {"limit": 5}),
    ("/api/v1/data/tables/prices_daily/rows", {"symbol": "AAPL", "start": "2026-09-01", "end": "2026-09-30", "limit": 5}),
    ("/api/v1/admin/dashboard-data", None),
    ("/api/v1/admin/engine-status", None),
    ("/api/v1/admin/worker-heartbeats", None),
    ("/api/v1/admin/accounts", None),
    ("/api/v1/admin/queries", None),
]


@pytest.mark.parametrize(("path", "params"), BRIDGE_OK, ids=[f"{p}?{q or ''}" for p, q in BRIDGE_OK])
def test_route_serves_prod_schema(client, bridge_token, path, params) -> None:
    response = _get(client, bridge_token, path, params)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "query_name",
    ["all_tickers", "latest_prices", "latest_signals", "orders", "portfolio", "command_log", "market_news", "heartbeats", "table_stats"],
)
def test_admin_named_queries_run_on_prod_schema(client, bridge_token, query_name) -> None:
    response = _get(client, bridge_token, "/api/v1/admin/named-query", {"query_name": query_name, "limit": 5})
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------
# Routes that read host-only objects (contracts/prod/host_only_tables.txt).
# No Prod migration creates these, so they run against the shapes DataAPI
# declares in contracts/prod/host_only_assumed.sql: this proves DataAPI's SQL
# matches its own declared requirement, NOT that production has that shape.
# --------------------------------------------------------------------------

HOST_ONLY_ROUTES = [
    ("/api/v1/financials/AAPL/income", {"limit": 12}),
    ("/api/v1/financials/AAPL/balance", {"limit": 12}),
    ("/api/v1/financials/AAPL/cashflow", {"limit": 12}),
    ("/api/v1/indicators/AAPL/risk", {"limit": 30}),
    ("/api/v1/indicators/AAPL/valuation", {"limit": 30}),
    ("/api/v1/indicators/AAPL/returns", {"limit": 30}),
    ("/api/v1/news/ticker/AAPL", {"limit": 10}),
    ("/api/v1/admin/price-ticks/AAPL", None),
    ("/api/v1/admin/etl-jobs", None),
    ("/api/v1/admin/audit-events", {"limit": 5}),
]


@pytest.mark.parametrize(("path", "params"), HOST_ONLY_ROUTES, ids=[p for p, _ in HOST_ONLY_ROUTES])
def test_host_only_routes_match_declared_assumptions(client, bridge_token, path, params) -> None:
    response = _get(client, bridge_token, path, params)
    assert response.status_code == 200, response.text


def test_eps_still_comes_from_host_only_column(client, lens_token) -> None:
    context = _get(client, lens_token, "/api/v1/advisor/context", {"ticker": "AAPL"}).json()
    assert context["ticker_snapshot"]["eps"] == pytest.approx(6.42)
    assert context["ticker_snapshot"]["pe_ratio"] == pytest.approx(29.5)


# --------------------------------------------------------------------------
# Bookkeeping: every theeyebeta object referenced in app/ is either in the
# Prod snapshot or explicitly listed as host-only.
# --------------------------------------------------------------------------


def _listed(name: str) -> set[str]:
    lines = (CONTRACT_DIR / name).read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def test_every_referenced_object_is_accounted_for() -> None:
    import re

    app_dir = Path(__file__).resolve().parents[2] / "app"
    referenced: set[str] = set()
    for source in app_dir.rglob("*.py"):
        for match in re.finditer(r"\btheeyebeta\.([a-z_][a-z0-9_]*)", source.read_text(encoding="utf-8")):
            if match.group(1) != "store":  # hostname "theeyebeta.store", not a table
                referenced.add(match.group(1))
    snapshot, host_only = _listed("objects.txt"), _listed("host_only_tables.txt")
    assert not snapshot & host_only, "a table cannot be both in the Prod snapshot and host-only"
    unaccounted = referenced - snapshot - host_only
    assert not unaccounted, f"add to contracts/prod/objects.txt (if Prod creates it) or host_only_tables.txt: {sorted(unaccounted)}"


def test_host_only_tables_are_really_absent_from_prod_snapshot() -> None:
    snapshot_sql = (CONTRACT_DIR / "theeyebeta_schema.sql").read_text(encoding="utf-8")
    for table in _listed("host_only_tables.txt"):
        assert f"theeyebeta.{table} " not in snapshot_sql and f"theeyebeta.{table}\n" not in snapshot_sql, (
            f"{table} is now created by Prod migrations: move it to objects.txt and regenerate the snapshot"
        )


def test_assumed_file_covers_exactly_the_host_only_list() -> None:
    import re

    assumed = (CONTRACT_DIR / "host_only_assumed.sql").read_text(encoding="utf-8")
    created = set(re.findall(r"CREATE TABLE theeyebeta\.([a-z_0-9]+)", assumed))
    assert created == _listed("host_only_tables.txt")


def test_generic_rows_ticker_id_symbol_clause_runs_on_prod_schema(contract_env) -> None:
    """No granted table has ticker_id without instrument_id today, so check the clause directly."""
    from sqlalchemy import text

    from app.db.session import get_db_session
    from app.repositories.sql_data import TICKER_ID_SYMBOL_CLAUSE

    session = get_db_session()
    try:
        ids = session.execute(
            text(f"SELECT v.ticker_id FROM (VALUES (101::bigint), (102::bigint)) AS v(ticker_id) WHERE {TICKER_ID_SYMBOL_CLAUSE}"),
            {"symbol": "aapl"},
        ).scalars().all()
    finally:
        session.close()
    assert ids == [101]
