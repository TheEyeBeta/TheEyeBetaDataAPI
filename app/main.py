"""FastAPI app entry point for TheEyeBetaDataAPI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.context import router as context_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.request_context import RequestContextMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

setup_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Internet-exposed AI Data API with allowlisted database access.",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.parsed_trusted_hosts)

if settings.parsed_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    )

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(context_router)
app.include_router(chat_router)


@app.get("/")
def root() -> dict[str, str]:
    """Simple root endpoint."""
    return {"name": settings.app_name, "version": settings.app_version, "status": "ok"}
