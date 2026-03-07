"""Application settings."""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TheEyeBetaDataAPI"
    app_version: str = "0.1.0"

    environment: str = "development"
    debug: bool = False

    database_url: str
    api_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"

    rate_limit_per_minute: int = 60

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    api_host: str = "127.0.0.1"
    api_port: int = 7000
    cors_origins: str = ""

    trusted_hosts: str = "localhost,127.0.0.1"
    trust_proxy_headers: bool = False

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = {"development", "staging", "production"}
        lowered = value.lower().strip()
        if lowered not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return lowered

    @field_validator("api_key", "jwt_secret")
    @classmethod
    def validate_secrets_length(cls, value: str) -> str:
        if len(value.strip()) < 24:
            raise ValueError("secret values must be at least 24 characters")
        return value

    @field_validator("api_port")
    @classmethod
    def validate_api_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("api_port must be between 1 and 65535")
        return value

    @model_validator(mode="after")
    def validate_production_wildcards(self) -> "Settings":
        if self.environment == "production":
            if "*" in self.parsed_trusted_hosts:
                raise ValueError("TRUSTED_HOSTS cannot include '*' in production")
            if "*" in self.parsed_cors_origins:
                raise ValueError("CORS_ORIGINS cannot include '*' in production")
        return self

    @property
    def parsed_cors_origins(self) -> list[str]:
        """Return comma-separated CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def parsed_trusted_hosts(self) -> list[str]:
        """Return comma-separated trusted hosts as a list."""
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]


settings = Settings()
