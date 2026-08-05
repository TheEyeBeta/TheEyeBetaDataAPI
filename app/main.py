"""FastAPI app entry point for TheEyeBetaDataAPI."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.error_handlers import register_error_handlers
from app.api.routes.admin import router as admin_router
from app.api.routes.admin_gateway import router as admin_gateway_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.context import router as context_router
from app.api.routes.data import router as data_router
from app.api.routes.financials import router as financials_router
from app.api.routes.fixed_income import router as fixed_income_router
from app.api.routes.health import router as health_router
from app.api.routes.indicators import router as indicators_router
from app.api.routes.macro import router as macro_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.news import router as news_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.reference import router as reference_router
from app.api.routes.sectors import router as sectors_router
from app.api.routes.signals import router as signals_router
from app.api.routes.symbols import router as symbols_router
from app.api.routes.tickers import router as tickers_router
from app.api.routes.universe import router as universe_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.request_context import RequestContextMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

setup_logging()


@asynccontextmanager
async def lifespan(_application: FastAPI):
    yield
    from app.db.session import engine
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Internet-exposed AI Data API with allowlisted database access.",
    lifespan=lifespan,
)

Instrumentator(
    excluded_handlers=["/metrics", "/health"],
    should_group_status_codes=False,
).instrument(app).expose(app, include_in_schema=False)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.parsed_trusted_hosts)

if settings.parsed_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "Idempotency-Key",
            "X-Confirm",
            "X-Dry-Run",
            "X-CSRF-Token",
        ],
    )

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(context_router)
app.include_router(data_router)
app.include_router(chat_router)
app.include_router(market_data_router)
app.include_router(sectors_router)
app.include_router(universe_router)
app.include_router(symbols_router)
app.include_router(analytics_router)
app.include_router(signals_router)
app.include_router(portfolio_router)
app.include_router(reference_router)
app.include_router(tickers_router)
app.include_router(financials_router)
app.include_router(indicators_router)
app.include_router(macro_router, prefix="/v1/macro")
app.include_router(macro_router, prefix="/api/v1/macro", include_in_schema=False)
app.include_router(fixed_income_router, prefix="/api/v1/fixed-income")
app.include_router(news_router)
app.include_router(admin_router)
app.include_router(admin_gateway_router)

register_error_handlers(app)


@app.get("/")
def root() -> dict[str, str]:
    """Simple root endpoint."""
    return {"name": settings.app_name, "version": settings.app_version, "status": "ok"}
