"""Tests for client IP extraction when proxy headers are enabled."""

from starlette.requests import Request

from app.core.client_ip import get_client_ip
from app.core.config import settings


def _build_request(headers: dict[str, str] | None = None, client: tuple[str, int] = ("127.0.0.1", 55000)) -> Request:
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_ignores_forwarded_headers_when_not_trusted(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    request = _build_request(headers={"CF-Connecting-IP": "203.0.113.10"})
    assert get_client_ip(request) == "127.0.0.1"


def test_uses_cf_connecting_ip_when_trusted(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    request = _build_request(headers={"CF-Connecting-IP": "203.0.113.10"})
    assert get_client_ip(request) == "203.0.113.10"


def test_uses_first_xff_ip_when_trusted(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    request = _build_request(headers={"X-Forwarded-For": "198.51.100.9, 10.0.0.2"})
    assert get_client_ip(request) == "198.51.100.9"


def test_falls_back_to_socket_client_on_invalid_forwarded_ip(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    request = _build_request(headers={"CF-Connecting-IP": "not-an-ip"})
    assert get_client_ip(request) == "127.0.0.1"
