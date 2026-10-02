"""Admin gateway proxy behavior: what is forwarded, what is refused, what comes back."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes import admin_gateway
from app.core.config import settings
from app.main import app


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch):
    """Route the gateway's outbound httpx client to an in-process handler."""
    calls: list[httpx.Request] = []
    state: dict = {"handler": lambda request: httpx.Response(200, json={"ok": True})}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return state["handler"](request)

    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(settings, "admin_gateway_enabled", True)
    monkeypatch.setattr(settings, "admin_service_url", "http://127.0.0.1:7200")
    monkeypatch.setattr(admin_gateway.httpx, "AsyncClient", client_factory)
    state["calls"] = calls
    return state


def test_gateway_disabled_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_gateway_enabled", False)
    response = TestClient(app).get("/admin/orders")
    assert response.status_code == 503


def test_unlisted_route_is_refused_without_calling_upstream(upstream) -> None:
    response = TestClient(app).get("/admin/secrets/export")
    assert response.status_code == 404
    assert upstream["calls"] == []


def test_read_only_family_refuses_mutation(upstream) -> None:
    response = TestClient(app).post("/admin/audit", headers={"X-Idempotency-Key": "k1"}, json={})
    assert response.status_code == 404
    assert upstream["calls"] == []


def test_mutation_requires_idempotency_key(upstream) -> None:
    response = TestClient(app).post("/admin/orders", json={"symbol": "AAPL"})
    assert response.status_code == 422
    assert upstream["calls"] == []


def test_auth_lifecycle_does_not_require_idempotency_key(upstream) -> None:
    response = TestClient(app).post("/admin/auth/login", json={"u": "x"})
    assert response.status_code == 200
    assert len(upstream["calls"]) == 1


def test_forwards_only_allowlisted_headers_path_query_and_body(upstream) -> None:
    response = TestClient(app).post(
        "/admin/orders/submit?dry=1&tag=a&tag=b",
        headers={
            "Authorization": "Bearer abc",
            "Cookie": "session=s1",
            "X-CSRF-Token": "csrf",
            "X-Idempotency-Key": "idem-1",
            "X-Request-ID": "req-1",
            "X-Forwarded-For": "1.2.3.4",
            "X-Internal-Override": "yes",
        },
        content=b'{"qty":1}',
    )
    assert response.status_code == 200
    (sent,) = upstream["calls"]
    assert str(sent.url.copy_with(query=None)) == "http://127.0.0.1:7200/admin/orders/submit"
    assert sent.url.params.get_list("tag") == ["a", "b"]
    assert sent.content == b'{"qty":1}'
    assert sent.headers["authorization"] == "Bearer abc"
    assert sent.headers["cookie"] == "session=s1"
    assert sent.headers["x-csrf-token"] == "csrf"
    assert sent.headers["x-idempotency-key"] == "idem-1"
    assert sent.headers["x-request-id"] == "req-1"
    assert "x-forwarded-for" not in sent.headers
    assert "x-internal-override" not in sent.headers


def test_response_headers_are_filtered_and_cookies_preserved(upstream) -> None:
    upstream["handler"] = lambda request: httpx.Response(
        201,
        content=b'{"id":7}',
        headers=[
            ("content-type", "application/json"),
            ("x-request-id", "up-1"),
            ("server", "admin-service/9.9"),
            ("x-internal-debug", "stack"),
            ("set-cookie", "a=1; HttpOnly"),
            ("set-cookie", "b=2; HttpOnly"),
        ],
    )
    response = TestClient(app).get("/admin/orders")
    assert response.status_code == 201
    assert response.content == b'{"id":7}'
    assert response.headers["cache-control"] == "no-store"
    assert "x-internal-debug" not in response.headers
    assert response.headers.get("server") != "admin-service/9.9"
    assert response.headers.get_list("set-cookie") == ["a=1; HttpOnly", "b=2; HttpOnly"]


def test_oversized_body_is_refused(upstream, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_gateway_max_body_bytes", 8)
    response = TestClient(app).post("/admin/orders", headers={"X-Idempotency-Key": "k"}, content=b"0123456789")
    assert response.status_code == 413
    assert upstream["calls"] == []


def test_upstream_timeout_is_504_with_retry_guidance(upstream) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    upstream["handler"] = timeout
    response = TestClient(app).post("/admin/orders", headers={"X-Idempotency-Key": "k"}, json={})
    assert response.status_code == 504
    assert "idempotency key" in response.json()["detail"]


def test_upstream_down_is_503(upstream) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    upstream["handler"] = refused
    response = TestClient(app).get("/admin/orders")
    assert response.status_code == 503


def test_request_id_is_generated_when_client_sends_none(upstream) -> None:
    response = TestClient(app).get("/admin/orders")
    assert response.status_code == 200
    (sent,) = upstream["calls"]
    assert len(sent.headers.get_list("x-request-id")) == 1
    assert sent.headers["x-request-id"]


@pytest.mark.parametrize(
    "path",
    [
        "/admin/audit/%2e%2e/sql/execute",
        "/admin/audit/%252e%252e/sql/execute",
        "/admin/audit/..%2fsql/execute",
        "/admin/audit/x%5c..%5csql",
        "/admin/audit//log",
        "/admin/audit/%00log",
        "/admin/audit/%25",
    ],
)
def test_encoded_traversal_and_odd_paths_never_reach_upstream(upstream, path: str) -> None:
    response = TestClient(app).get(path)
    assert response.status_code == 404
    assert upstream["calls"] == []


def test_encoded_query_and_fragment_characters_stay_in_the_path_segment(upstream) -> None:
    response = TestClient(app).get("/admin/orders/a%3Fstatus%3Dall%23x")
    assert response.status_code == 200
    (sent,) = upstream["calls"]
    assert sent.url.raw_path == b"/admin/orders/a%3Fstatus%3Dall%23x"
    assert sent.url.query == b""


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/admin/orders/1"),
        ("PATCH", "/admin/services/x"),
        ("DELETE", "/admin/workers/x"),
        ("GET", "/admin/events/stream"),
    ],
)
def test_methods_and_families_prod_does_not_serve_are_refused(upstream, method: str, path: str) -> None:
    response = TestClient(app).request(method, path, headers={"X-Idempotency-Key": "k"})
    assert response.status_code == 404
    assert upstream["calls"] == []
