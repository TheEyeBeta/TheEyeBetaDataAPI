"""Tests for the admin read-only SQL query validator."""

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


# ---------- Valid queries ----------

@pytest.mark.parametrize("query", [
    "SELECT * FROM tickers",
    "SELECT ticker, last_price FROM tickers WHERE is_active = true",
    "SELECT COUNT(*) FROM tickers",
    "  SELECT * FROM tickers  ",          # leading/trailing whitespace
    "SELECT * FROM tickers;",             # trailing semicolon stripped
    "SELECT ticker FROM tickers -- comment at end",
    "SELECT /* inline comment */ ticker FROM tickers",
])
def test_valid_select_queries_are_accepted(query: str) -> None:
    repo = _repo()
    result = repo.execute_readonly_query(query, limit=10)
    assert isinstance(result, list)


# ---------- Non-SELECT statements ----------

@pytest.mark.parametrize("query", [
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
def test_non_select_statements_are_rejected(query: str) -> None:
    repo = _repo()
    with pytest.raises(ValidationAppError):
        repo.execute_readonly_query(query, limit=10)


# ---------- CTE and dangerous keyword bypasses ----------

@pytest.mark.parametrize("query", [
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "SELECT 1; DROP TABLE tickers",       # embedded semicolon
    "SELECT 1; SELECT 2",                 # embedded semicolon (multi-statement)
    "SELECT * FROM tickers WHERE 1=1; --",  # embedded semicolon
])
def test_cte_and_semicolon_attacks_are_rejected(query: str) -> None:
    repo = _repo()
    with pytest.raises(ValidationAppError):
        repo.execute_readonly_query(query, limit=10)


# ---------- Comment-based keyword obfuscation ----------

@pytest.mark.parametrize("query", [
    "SELECT * FROM tickers WHERE 1=1 -- DROP TABLE tickers",  # DROP is in a comment — safe
])
def test_keywords_in_comments_are_stripped_and_safe(query: str) -> None:
    """Keywords that appear only inside comments must not block the query."""
    repo = _repo()
    result = repo.execute_readonly_query(query, limit=10)
    assert isinstance(result, list)


@pytest.mark.parametrize("query", [
    "SELECT /* DROP TABLE tickers */ ticker FROM tickers",
])
def test_keywords_in_block_comments_are_stripped_and_safe(query: str) -> None:
    repo = _repo()
    result = repo.execute_readonly_query(query, limit=10)
    assert isinstance(result, list)


# ---------- Named query allowlist ----------

@pytest.mark.parametrize("query_name", [
    "all_tickers",
    "latest_prices",
    "latest_signals",
    "recent_trades",
    "portfolio",
    "valuation",
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
