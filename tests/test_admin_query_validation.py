"""Tests for the admin curated query behavior."""

import pytest

from app.domain.errors import ValidationAppError
from app.repositories.sql_market_data import SQLMarketDataRepository


class _FakeSession:
    """Minimal session stub that records executed SQL without hitting a DB."""

    def __init__(self):
        self.last_query = None
        self.last_params = None

    def execute(self, stmt, params=None):
        self.last_query = str(stmt)
        self.last_params = params

        class _Result:
            def mappings(self_inner):
                class _Mappings:
                    def all(self_inner2):
                        return []
                return _Mappings()

        return _Result()


def _repo() -> SQLMarketDataRepository:
    return SQLMarketDataRepository(_FakeSession())


@pytest.mark.parametrize("query", [
    "SELECT * FROM theeyebeta.instruments",
    "SELECT COUNT(*) FROM theeyebeta.instruments",
    "INSERT INTO tickers VALUES (1)",
    "UPDATE tickers SET is_active = false",
    "DELETE FROM tickers",
    "DROP TABLE tickers",
    "ALTER TABLE tickers ADD COLUMN foo TEXT",
    "TRUNCATE tickers",
    "CREATE TABLE evil (id INT)",
    "GRANT ALL ON tickers TO PUBLIC",
    "REVOKE SELECT ON tickers FROM user",
])
def test_arbitrary_sql_queries_are_disabled(query: str) -> None:
    repo = _repo()
    with pytest.raises(ValidationAppError, match="Arbitrary SQL is disabled"):
        repo.execute_readonly_query(query, limit=10)


# ---------- Named query allowlist ----------

@pytest.mark.parametrize("query_name", [
    "all_tickers",
    "latest_prices",
    "latest_signals",
    "orders",
    "portfolio",
    "command_log",
    "market_news",
    "heartbeats",
    "table_stats",
])
def test_known_named_queries_are_executed(query_name: str) -> None:
    repo = _repo()
    result = repo.execute_named_query(query_name, limit=5)
    assert isinstance(result, list)


def test_unknown_named_query_is_rejected() -> None:
    repo = _repo()
    with pytest.raises(ValidationAppError, match="Unknown query name"):
        repo.execute_named_query("DROP TABLE tickers", limit=5)


def test_named_query_with_sql_injection_name_is_rejected() -> None:
    repo = _repo()
    with pytest.raises(ValidationAppError):
        repo.execute_named_query("'; DROP TABLE tickers; --", limit=5)
