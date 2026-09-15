"""Admin routes — dashboard UI + API endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.dependencies.services import get_account_service, get_admin_service, get_market_data_service
from app.api.routes.admin_dashboard_html import DASHBOARD_HTML as _DASHBOARD_HTML
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ADMIN_READ, SCOPE_ADMIN_WRITE
from app.core.subject_rate_limit import require_account_delete_rate_limit, require_admin_rate_limit
from app.repositories.sql_market_data import CURATED_QUERY_NAMES
from app.schemas.accounts import (
    AccountListResponse,
    AccountResponse,
    CreateAccountRequest,
    DeleteAccountRequest,
)
from app.schemas.market import (
    AdminAuditEventsResponse,
    EngineStatusResponse,
    EtlJobStatesResponse,
    PriceTicksResponse,
    WorkerHeartbeatsResponse,
)
from app.services.account_service import AccountService
from app.services.admin_service import AdminService
from app.services.market_data_service import MarketDataService

logger = logging.getLogger("dataapi.audit")

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/audit-events", response_model=AdminAuditEventsResponse)
def get_audit_events(
    limit: int = Query(default=50, ge=1, le=500),
    category: str | None = Query(default=None, max_length=80),
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: AdminService = Depends(get_admin_service),
) -> AdminAuditEventsResponse:
    """Return admin audit events from orchestration tables."""
    return service.get_audit_events(limit=limit, category=category)


@router.get("/dashboard-data")
def get_dashboard_data(
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """Return all dashboard data as JSON."""
    data = service.get_dashboard_data()
    return JSONResponse(content=data)


@router.get("/named-query")
def execute_named_query(
    request: Request,
    query_name: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=100, ge=1, le=1000),
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    _rl=Depends(require_admin_rate_limit),
    service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """Execute a server-side curated named query."""
    if query_name not in CURATED_QUERY_NAMES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Unknown query_name: {query_name!r}")
    logger.warning(
        "admin_named_query auth_subject=%s query_name=%s limit=%d",
        getattr(request.state, "auth_subject", "unknown"),
        query_name,
        limit,
    )
    result = service.execute_named_query(query_name, limit=limit)
    return JSONResponse(content=result)


@router.get("/queries")
def list_named_queries(
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
) -> JSONResponse:
    """Return the list of available curated query names."""
    return JSONResponse(content={"queries": sorted(CURATED_QUERY_NAMES)})


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(
    include_inactive: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: AccountService = Depends(get_account_service),
) -> AccountListResponse:
    """List end-user accounts (iam.users) for the ops dashboard."""
    rows = service.list_accounts(include_inactive=include_inactive, limit=limit)
    accounts = [AccountResponse(**row) for row in rows]
    return AccountListResponse(accounts=accounts, total=len(accounts))


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    body: CreateAccountRequest,
    request: Request,
    _=Depends(require_scopes([SCOPE_ADMIN_WRITE])),
    _rl=Depends(require_admin_rate_limit),
    service: AccountService = Depends(get_account_service),
) -> AccountResponse:
    """Create a new end-user account (iam.users)."""
    actor_subject = getattr(request.state, "auth_subject", "unknown")
    result = service.create_account(
        email=body.email,
        display_name=body.display_name,
        organization=body.organization,
        plan=body.plan,
        actor_subject=actor_subject,
    )
    return AccountResponse(**result)


@router.delete("/accounts/{user_uuid}", response_model=AccountResponse)
def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    user_uuid: uuid.UUID = Path(...),
    _=Depends(require_scopes([SCOPE_ADMIN_WRITE])),
    _rl=Depends(require_admin_rate_limit),
    _drl=Depends(require_account_delete_rate_limit),
    service: AccountService = Depends(get_account_service),
) -> AccountResponse:
    """Deactivate an end-user account. Requires a valid operator approval code.

    This is a soft delete: iam.users.is_active is set to false, which triggers
    automatic revocation of the account's API keys. Nothing is hard-deleted.

    Capped at 1 request/minute per subject (on top of the general admin rate
    limit) so brute-forcing the approval code isn't practical regardless of
    the code's length.
    """
    actor_subject = getattr(request.state, "auth_subject", "unknown")
    logger.warning(
        "admin_account_delete_attempt auth_subject=%s user_uuid=%s",
        actor_subject,
        user_uuid,
    )
    result = service.delete_account(
        user_uuid=str(user_uuid),
        approval_code=body.approval_code,
        actor_subject=actor_subject,
        reason=body.reason,
    )
    return AccountResponse(**result)


@router.get("/etl-jobs", response_model=EtlJobStatesResponse)
def get_etl_jobs(
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> EtlJobStatesResponse:
    """Return ETL job state for all registered jobs."""
    return service.get_etl_job_states()


@router.get("/engine-status", response_model=EngineStatusResponse)
def get_engine_status(
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> EngineStatusResponse:
    """Return engine key-value status entries."""
    return service.get_engine_status()


@router.get("/worker-heartbeats", response_model=WorkerHeartbeatsResponse)
def get_worker_heartbeats(
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> WorkerHeartbeatsResponse:
    """Return engine worker heartbeat records."""
    return service.get_worker_heartbeats()


@router.get("/price-ticks/{ticker}", response_model=PriceTicksResponse)
def get_price_ticks(
    ticker: str = Path(pattern=r"^[A-Za-z0-9.\-]{1,10}$"),
    limit: int = Query(default=100, ge=1, le=1000),
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: MarketDataService = Depends(get_market_data_service),
) -> PriceTicksResponse:
    """Return recent intraday price ticks for a ticker (admin only)."""
    return service.get_price_ticks(ticker=ticker.upper(), limit=limit)


@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard() -> HTMLResponse:
    """Serve the admin dashboard HTML page. Auth is handled client-side via token."""
    return HTMLResponse(content=_DASHBOARD_HTML)
