"""Postgres-backed integration tests for the IAM paths.

Skipped unless TEST_POSTGRES_URL points at a scratch server whose role can
CREATE DATABASE and CREATE ROLE (e.g. the `postgres` superuser of a throwaway
container). Never point it at a real database.

The session creates a fresh database, applies the repo's deploy/iam_*.sql and
deploy/db_security.sql, then runs app code as the least-privilege
`api_service` role, so every test also proves the grants in db_security.sql.
Provisioning helpers (iam.provision_*) run as the owner, as operators do.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
IAM_SQL_FILES = (
    "iam_api_key_schema.sql",
    "iam_user_api_key_schema.sql",
    "iam_refresh_tokens.sql",
    "iam_auth_audit.sql",
)
APP_ROLE = "api_service"


def _libpq(url: URL) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _apply_sql_file(conninfo: str, path: Path) -> None:
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def pg_urls() -> Iterator[tuple[URL, URL]]:
    """Yield (owner_url, app_url) for a freshly provisioned test database."""
    raw = os.environ.get("TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("TEST_POSTGRES_URL not set; skipping Postgres integration tests")

    admin_url = make_url(raw)
    db_name = f"dataapi_it_{secrets.token_hex(4)}"
    app_password = secrets.token_urlsafe(24)

    with psycopg.connect(_libpq(admin_url), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{db_name}"')

    owner_url = admin_url.set(database=db_name)
    owner_conninfo = _libpq(owner_url)
    try:
        with psycopg.connect(owner_conninfo, autocommit=True) as conn:
            # Stand-in for the Prod-owned theeyebeta schema so grants can apply.
            conn.execute("CREATE SCHEMA theeyebeta")
            conn.execute("CREATE TABLE theeyebeta.instruments (id int PRIMARY KEY, symbol text NOT NULL)")
            conn.execute("INSERT INTO theeyebeta.instruments VALUES (1, 'AAPL')")
        for name in IAM_SQL_FILES:
            _apply_sql_file(owner_conninfo, REPO_ROOT / "deploy" / name)
        _apply_sql_file(owner_conninfo, REPO_ROOT / "deploy" / "db_security.sql")
        with psycopg.connect(owner_conninfo, autocommit=True) as conn:
            conn.execute(f"ALTER ROLE {APP_ROLE} WITH LOGIN PASSWORD '{app_password}'")

        app_url = owner_url.set(username=APP_ROLE, password=app_password)
        yield owner_url, app_url
    finally:
        with psycopg.connect(_libpq(admin_url), autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')


@pytest.fixture(scope="session")
def owner_engine(pg_urls: tuple[URL, URL]) -> Iterator[Engine]:
    engine = create_engine(pg_urls[0], isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_sessionmaker(pg_urls: tuple[URL, URL]) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(pg_urls[1])
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


@pytest.fixture
def app_session(app_sessionmaker: sessionmaker[Session]) -> Iterator[Session]:
    session = app_sessionmaker()
    try:
        yield session
    finally:
        session.close()
