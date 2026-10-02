"""Postgres-backed integration tests for the IAM paths.

Skipped unless TEST_POSTGRES_URL points at a scratch server whose role can
CREATE DATABASE and CREATE ROLE (e.g. the `postgres` superuser of a throwaway
container). Never point it at a real database.

The session creates a fresh database in production layout (tests/pg_support.py:
Prod's theeyebeta schema snapshot + Prod's api_readonly grants + deploy/iam_*.sql
+ deploy/db_security.sql), then runs app code as the least-privilege
`api_service` role, so every test also proves the grants.
Provisioning helpers (iam.provision_*) run as the owner, as operators do.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from tests.pg_support import APP_ROLE, build_production_layout, create_database, drop_database


@pytest.fixture(scope="session")
def pg_urls() -> Iterator[tuple[URL, URL]]:
    """Yield (owner_url, app_url) for a fresh database in production layout."""
    raw = os.environ.get("TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("TEST_POSTGRES_URL not set; skipping Postgres integration tests")

    admin_url = make_url(raw)
    db_name = f"dataapi_it_{secrets.token_hex(4)}"
    app_password = secrets.token_urlsafe(24)
    owner_url = create_database(admin_url, db_name)
    try:
        build_production_layout(owner_url, app_password)
        yield owner_url, owner_url.set(username=APP_ROLE, password=app_password)
    finally:
        drop_database(admin_url, db_name)


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
