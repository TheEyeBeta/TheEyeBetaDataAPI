"""Tests for JWKS-based user JWT decoding."""

from app.auth.models import PrincipalType
from app.auth.tokens import _decode_user_token
from app.core.config import settings


class _FakeSigningKey:
    key = "fake-public-key"


class _FakeJwksClient:
    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:  # noqa: ARG002
        return _FakeSigningKey()


def test_decode_user_token_with_jwks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "user_jwt_jwks_url", "https://issuer.example/.well-known/jwks.json")
    monkeypatch.setattr(settings, "user_jwt_issuer", "https://issuer.example")
    monkeypatch.setattr(settings, "user_jwt_audience", "dataapi-audience")
    monkeypatch.setattr(settings, "user_jwt_algorithms", "RS256")

    monkeypatch.setattr("app.auth.tokens._get_jwks_client", lambda: _FakeJwksClient())

    def _fake_decode(token, key, algorithms, issuer, audience):  # noqa: ANN001, ANN201
        assert token == "fake-jwt-token"
        assert key == "fake-public-key"
        assert algorithms == ["RS256"]
        assert issuer == "https://issuer.example"
        assert audience == "dataapi-audience"
        return {"sub": "user-jwks-1", "scope": "market:read advisor:read"}

    monkeypatch.setattr("app.auth.tokens.jwt.decode", _fake_decode)

    principal = _decode_user_token("fake-jwt-token")
    assert principal is not None
    assert principal.principal_type == PrincipalType.USER
    assert principal.subject == "user-jwks-1"
    assert principal.scopes == frozenset({"market:read", "advisor:read"})
