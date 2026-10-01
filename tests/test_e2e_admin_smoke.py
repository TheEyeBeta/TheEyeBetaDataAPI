"""scripts/e2e_admin_smoke.py against the app with a mocked admin-service.

The same script runs after every production deploy (ci.yml deploy job); the
authenticated bridge hop is exercised on Prod's schema in tests/contract.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "e2e_admin_smoke.py"


def load_smoke():
    spec = importlib.util.spec_from_file_location("e2e_admin_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def admin_service(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Prod admin-service stand-in: every unauthenticated call is 401."""
    from app.api.routes import admin_gateway

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"detail": "Not authenticated"})

    real = httpx.AsyncClient
    monkeypatch.setattr(settings, "admin_gateway_enabled", True)
    monkeypatch.setattr(settings, "admin_service_url", "http://127.0.0.1:7200")
    monkeypatch.setattr(
        admin_gateway.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    return calls


@pytest.fixture
def db_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HealthService, "get_health", lambda self: HealthResponse(status="healthy", database=True))


def test_smoke_passes_against_healthy_stack(admin_service, db_up) -> None:
    out = io.StringIO()
    assert load_smoke().run(TestClient(app), environ={}, out=out), out.getvalue()
    assert "FAIL" not in out.getvalue()
    # Only the two auth-required probes reach admin-service; refused routes never do.
    assert sorted(r.url.path for r in admin_service) == ["/admin/auth/me", "/admin/terminal-data/modules"]


def test_smoke_fails_when_database_is_down(admin_service, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HealthService, "get_health", lambda self: HealthResponse(status="healthy", database=False))
    out = io.StringIO()
    assert not load_smoke().run(TestClient(app), environ={}, out=out)
    assert "[FAIL] health + database" in out.getvalue()


def test_smoke_fails_when_gateway_disabled(db_up, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_gateway_enabled", False)
    out = io.StringIO()
    assert not load_smoke().run(TestClient(app), environ={}, out=out)
    assert "HTTP 503" in out.getvalue()


def test_smoke_fails_if_a_blocked_route_is_ever_exposed(admin_service, db_up, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import admin_gateway

    widened = (*admin_gateway.ADMIN_ROUTE_MANIFEST, admin_gateway.RouteRule("health", frozenset({"GET"})))
    monkeypatch.setattr(admin_gateway, "ADMIN_ROUTE_MANIFEST", widened)
    out = io.StringIO()
    assert not load_smoke().run(TestClient(app), environ={}, out=out)
    assert "[FAIL] admin-service health not exposed" in out.getvalue()
