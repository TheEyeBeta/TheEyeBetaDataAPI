"""Pytest configuration for TheEyeBetaDataAPI."""

import os


# Ensure required settings exist before app modules import `settings = Settings()`.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://readonly_user:change_me@127.0.0.1:5432/theeyebeta",
)
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-which-is-24chars-min")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ISSUER", "theeyebeta-dataapi-test")
os.environ.setdefault("JWT_AUDIENCE", "theeyebeta-clients-test")
os.environ.setdefault("USER_JWT_SECRET", "test-user-jwt-secret-which-is-24chars")
os.environ.setdefault("USER_JWT_ALGORITHM", "HS256")
os.environ.setdefault("SERVICE_TOKEN_EXPIRES_MINUTES", "60")
os.environ.setdefault("SERVICE_CLIENT_AUTH_MODE", "environment")
os.environ.setdefault(
    "SERVICE_CLIENTS_JSON",
    '{"trade-engine":{"secret":"trade-engine-secret-which-is-24chars","scopes":["trades:write","portfolio:read","internal:jobs"]},'
    '"vi-app":{"secret":"vi-app-secret-which-is-24chars!!","scopes":["market:read","symbols:read","analytics:read","advisor:read","signals:read"]},'
    '"admin-tool":{"secret":"admin-tool-secret-which-is-24chars","scopes":["admin:*","internal:jobs"]}}',
)
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "120")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")
os.environ.setdefault("API_HOST", "127.0.0.1")
os.environ.setdefault("API_PORT", "7000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
os.environ.setdefault("TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
os.environ.setdefault("TRUST_PROXY_HEADERS", "false")
