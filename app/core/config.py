"""Application settings."""

import json
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "TheEyeBetaDataAPI"
    app_version: str = "0.1.0"

    environment: str = "development"
    debug: bool = False

    database_url: str
    # DataAPI-issued token signing secret (service + delegated JWTs).
    # Prefer JWT_SIGNING_SECRET_CURRENT; JWT_SECRET remains the backwards-compatible alias.
    jwt_secret: str
    jwt_signing_secret_current: str | None = None
    jwt_signing_secret_previous: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "theeyebeta-dataapi"
    jwt_audience: str = "theeyebeta-clients"

    user_jwt_secret: str | None = None
    user_jwt_secret_previous: str | None = None
    user_jwt_algorithm: str = "HS256"
    user_jwt_jwks_url: str | None = None
    user_jwt_issuer: str | None = None
    user_jwt_audience: str | None = None
    user_jwt_algorithms: str = "RS256"

    service_token_expires_minutes: int = 60
    delegated_token_expires_minutes: int = 5
    # When false (default), iss/aud may be absent on inbound JWTs (grace period).
    # When true, every decode path requires and validates iss + aud.
    # Flip to true only after docs/IAM_CONSUMER_INVENTORY.md open questions are closed.
    jwt_require_iss_aud: bool = False
    # Phase 3: opted-in clients get this access-token TTL + a refresh token.
    short_lived_access_token_minutes: int = 15
    refresh_token_expires_days: int = 30
    # Phase 5: user API key lifetime policy.
    user_api_key_max_expires_days: int = 365
    user_api_key_backfill_days: int = 180
    service_client_auth_mode: str = "database"
    service_clients_json: str = "{}"
    service_mtls_enabled: bool = False
    service_mtls_subjects_json: str = "{}"
    service_mtls_header_client_id: str = "X-Service-Client-Id"
    service_mtls_header_subject: str = "X-Client-Cert-Subject"

    rate_limit_per_minute: int = 60
    redis_url: str | None = None
    rate_limit_redis_prefix: str = "dataapi:ratelimit"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Phase 5: user API key lifetime policy (provisioning / backfill).
    user_api_key_max_expires_days: int = 365
    user_api_key_backfill_days: int = 180

    api_host: str = "127.0.0.1"
    api_port: int = 7000
    cors_origins: str = ""

    trusted_hosts: str = "localhost,127.0.0.1"
    trust_proxy_headers: bool = False
    policy_enforcement_enabled: bool = False
    admin_gateway_enabled: bool = False
    admin_service_url: str = ""
    admin_gateway_timeout_seconds: int = 30
    admin_gateway_max_body_bytes: int = 1_048_576

    # Operator-supplied code word required to deactivate an end-user account
    # via the admin API. Never committed; set per-environment. Unset means the
    # delete endpoint fails closed (returns 403) rather than silently allowing
    # deletes with no gate.
    admin_account_approval_code: str | None = None

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = {"development", "staging", "production"}
        lowered = value.lower().strip()
        if lowered not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return lowered

    @field_validator("jwt_secret")
    @classmethod
    def validate_secrets_length(cls, value: str) -> str:
        if len(value.strip()) < 24:
            raise ValueError("secret values must be at least 24 characters")
        return value

    @field_validator(
        "jwt_signing_secret_current",
        "jwt_signing_secret_previous",
        "user_jwt_secret",
        "user_jwt_secret_previous",
    )
    @classmethod
    def validate_optional_secret_length(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if len(value.strip()) < 24:
            raise ValueError("optional JWT secrets must be at least 24 characters when set")
        return value

    @field_validator("api_port")
    @classmethod
    def validate_api_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("api_port must be between 1 and 65535")
        return value

    @field_validator("service_token_expires_minutes")
    @classmethod
    def validate_service_token_ttl(cls, value: int) -> int:
        if value < 5 or value > 1440:
            raise ValueError("service_token_expires_minutes must be between 5 and 1440")
        return value

    @field_validator("delegated_token_expires_minutes")
    @classmethod
    def validate_delegated_token_ttl(cls, value: int) -> int:
        if value < 1 or value > 15:
            raise ValueError("delegated_token_expires_minutes must be between 1 and 15")
        return value

    @field_validator("short_lived_access_token_minutes")
    @classmethod
    def validate_short_lived_ttl(cls, value: int) -> int:
        if value < 1 or value > 60:
            raise ValueError("short_lived_access_token_minutes must be between 1 and 60")
        return value

    @field_validator("refresh_token_expires_days")
    @classmethod
    def validate_refresh_ttl_days(cls, value: int) -> int:
        if value < 1 or value > 365:
            raise ValueError("refresh_token_expires_days must be between 1 and 365")
        return value

    @field_validator("user_api_key_max_expires_days", "user_api_key_backfill_days")
    @classmethod
    def validate_user_api_key_days(cls, value: int) -> int:
        if value < 1 or value > 3650:
            raise ValueError("user API key day settings must be between 1 and 3650")
        return value

    @field_validator("admin_gateway_timeout_seconds", "admin_gateway_max_body_bytes")
    @classmethod
    def validate_gateway_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("admin gateway limits must be positive")
        return value

    @field_validator("service_client_auth_mode")
    @classmethod
    def validate_service_client_auth_mode(cls, value: str) -> str:
        allowed = {"database", "environment", "hybrid"}
        normalized = value.lower().strip()
        if normalized not in allowed:
            raise ValueError(f"service_client_auth_mode must be one of {allowed}")
        return normalized

    @field_validator("service_mtls_header_client_id", "service_mtls_header_subject")
    @classmethod
    def validate_mtls_header_names(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("mTLS header names cannot be empty")
        return normalized

    @field_validator("rate_limit_redis_prefix")
    @classmethod
    def validate_redis_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("rate_limit_redis_prefix cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_production_wildcards(self) -> "Settings":
        if self.environment == "production":
            if "*" in self.parsed_trusted_hosts:
                raise ValueError("TRUSTED_HOSTS cannot include '*' in production")
            if "*" in self.parsed_cors_origins:
                raise ValueError("CORS_ORIGINS cannot include '*' in production")
            if self.user_jwt_jwks_url and not self.user_jwt_jwks_url.startswith(
                "https://"
            ):
                raise ValueError("USER_JWT_JWKS_URL must be https:// in production")
        if self.service_mtls_enabled and not self.trust_proxy_headers:
            raise ValueError("SERVICE_MTLS_ENABLED requires TRUST_PROXY_HEADERS=true")
        if self.admin_gateway_enabled:
            parsed_admin_url = urlparse(self.admin_service_url)
            if parsed_admin_url.scheme != "http" or parsed_admin_url.hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError(
                    "ADMIN_SERVICE_URL must be an http loopback URL when gateway is enabled"
                )
        if self.environment == "production" and not self.policy_enforcement_enabled:
            raise ValueError("POLICY_ENFORCEMENT_ENABLED must be true in production")
        if self.service_client_auth_mode in {"environment", "hybrid"}:
            # Validate env-configured service client JSON when used.
            _ = self.parsed_service_clients
        _ = self.parsed_service_mtls_subjects
        return self

    @property
    def parsed_cors_origins(self) -> list[str]:
        """Return comma-separated CORS origins as a list."""
        application_origins = [
            "https://admin.theeyebeta.store",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ]
        configured = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return list(dict.fromkeys([*application_origins, *configured]))

    @property
    def parsed_trusted_hosts(self) -> list[str]:
        """Return comma-separated trusted hosts as a list."""
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]

    @property
    def parsed_service_clients(self) -> dict[str, dict]:
        """Return configured service clients from JSON mapping."""
        raw = self.service_clients_json
        if isinstance(raw, dict):
            parsed = raw
        else:
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("service_clients_json must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("service_clients_json must be a JSON object")
        return parsed

    @property
    def parsed_service_mtls_subjects(self) -> dict[str, list[str]]:
        """Return service client -> certificate subject allowlist."""
        raw = self.service_mtls_subjects_json
        if isinstance(raw, dict):
            parsed = raw
        else:
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    "service_mtls_subjects_json must be valid JSON"
                ) from exc
        if not isinstance(parsed, dict):
            raise ValueError("service_mtls_subjects_json must be a JSON object")

        normalized: dict[str, list[str]] = {}
        for client_id, subjects in parsed.items():
            if isinstance(subjects, str):
                values = [subjects]
            elif isinstance(subjects, list):
                values = [str(value) for value in subjects]
            else:
                raise ValueError(
                    "service_mtls_subjects_json values must be string or string array"
                )
            cleaned = [value.strip() for value in values if value.strip()]
            if cleaned:
                normalized[str(client_id)] = cleaned
        return normalized

    @property
    def effective_jwt_signing_secret(self) -> str:
        """Secret used to sign new service/delegated tokens."""
        return self.jwt_signing_secret_current or self.jwt_secret

    @property
    def jwt_verify_secrets(self) -> list[str]:
        """Ordered secrets for verifying DataAPI-issued JWTs (current, then previous)."""
        secrets = [self.effective_jwt_signing_secret]
        previous = self.jwt_signing_secret_previous
        if previous and previous not in secrets:
            secrets.append(previous)
        return secrets

    @property
    def user_jwt_verify_secrets(self) -> list[str]:
        """Ordered secrets for verifying symmetric user JWTs (current, then previous)."""
        secrets: list[str] = []
        if self.user_jwt_secret:
            secrets.append(self.user_jwt_secret)
        if self.user_jwt_secret_previous and self.user_jwt_secret_previous not in secrets:
            secrets.append(self.user_jwt_secret_previous)
        return secrets

    @property
    def parsed_user_jwt_algorithms(self) -> list[str]:
        """Return user JWT algorithms list."""
        return [
            alg.strip() for alg in self.user_jwt_algorithms.split(",") if alg.strip()
        ]

    @property
    def openapi_docs_enabled(self) -> bool:
        """Expose /docs, /redoc, and /openapi.json outside production only."""
        return self.environment != "production"


def openapi_route_kwargs(environment: str) -> dict[str, str | None]:
    """Return FastAPI docs/OpenAPI URL kwargs for the given environment."""
    if environment == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


settings = Settings()
