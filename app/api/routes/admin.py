"""Admin routes — dashboard UI + API endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.dependencies.services import get_account_service, get_admin_service, get_market_data_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ADMIN_READ, SCOPE_ADMIN_WRITE
from app.core.subject_rate_limit import require_admin_rate_limit
from app.repositories.sql_market_data import CURATED_QUERY_NAMES
from app.schemas.accounts import AccountResponse, CreateAccountRequest, DeleteAccountRequest
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
    service: AccountService = Depends(get_account_service),
) -> AccountResponse:
    """Deactivate an end-user account. Requires a valid operator approval code.

    This is a soft delete: iam.users.is_active is set to false, which triggers
    automatic revocation of the account's API keys. Nothing is hard-deleted.
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


_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>TheEyeBeta DataAPI — Admin</title>
<style>
  :root {
    --bg: #0a0e14; --bg-elevated: #0d1117; --surface: #151b23; --surface-hover: #1c2333;
    --border: #262e3a; --border-light: #313d4f;
    --text: #e2e8f0; --text-secondary: #94a3b8; --text-muted: #64748b;
    --accent: #3b82f6; --accent-hover: #2563eb; --accent-glow: rgba(59,130,246,0.15);
    --green: #22c55e; --green-bg: rgba(34,197,94,0.1); --green-border: rgba(34,197,94,0.25);
    --red: #ef4444; --red-bg: rgba(239,68,68,0.1); --red-border: rgba(239,68,68,0.25);
    --yellow: #eab308; --yellow-bg: rgba(234,179,8,0.1); --yellow-border: rgba(234,179,8,0.25);
    --orange: #f97316;
    --radius: 10px; --radius-lg: 14px;
    --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
    --shadow-lg: 0 4px 12px rgba(0,0,0,0.4);
    --transition: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif; font-size: 14px; line-height: 1.5; min-height: 100vh; overflow-x: hidden; }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--border-light); }

  /* Header */
  .header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .logo-icon { width: 32px; height: 32px; background: linear-gradient(135deg, var(--accent), #8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; color: #fff; flex-shrink: 0; }
  .header h1 { font-size: 17px; font-weight: 700; letter-spacing: -0.3px; }
  .header h1 .brand { background: linear-gradient(135deg, var(--accent), #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
  .header .meta { color: var(--text-muted); font-size: 12px; display: flex; align-items: center; gap: 8px; }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34,197,94,0.4); } 50% { opacity: 0.8; box-shadow: 0 0 0 6px rgba(34,197,94,0); } }

  /* Auth Bar */
  .auth-bar { background: var(--bg-elevated); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; gap: 8px; align-items: center; }
  .auth-bar input { flex: 1; min-width: 0; background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 10px 14px; border-radius: var(--radius); font-size: 13px; transition: border-color var(--transition); }
  .auth-bar input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
  .auth-bar input::placeholder { color: var(--text-muted); }

  /* Buttons */
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 18px; border-radius: var(--radius); cursor: pointer; font-size: 13px; font-weight: 600; border: none; transition: all var(--transition); white-space: nowrap; }
  .btn-primary { background: var(--accent); color: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.2); }
  .btn-primary:hover { background: var(--accent-hover); transform: translateY(-1px); box-shadow: var(--shadow); }
  .btn-primary:active { transform: translateY(0); }
  .btn-secondary { background: var(--surface); border: 1px solid var(--border); color: var(--text-secondary); }
  .btn-secondary:hover { background: var(--surface-hover); border-color: var(--border-light); color: var(--text); }
  .btn-ghost { background: transparent; color: var(--text-secondary); padding: 9px 12px; }
  .btn-ghost:hover { background: var(--surface); color: var(--text); }
  #auth-status { font-size: 12px; font-weight: 500; }
  .refresh-wrap { margin-left: auto; display: flex; align-items: center; gap: 8px; }

  /* Auto-refresh */
  .auto-refresh { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }
  .auto-refresh label { cursor: pointer; display: flex; align-items: center; gap: 4px; }
  .toggle { position: relative; width: 32px; height: 18px; }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .toggle .slider { position: absolute; inset: 0; background: var(--border); border-radius: 9px; cursor: pointer; transition: var(--transition); }
  .toggle .slider:before { content: ''; position: absolute; width: 14px; height: 14px; left: 2px; bottom: 2px; background: #fff; border-radius: 50%; transition: var(--transition); }
  .toggle input:checked + .slider { background: var(--accent); }
  .toggle input:checked + .slider:before { transform: translateX(14px); }

  /* Container */
  .container { max-width: 1440px; margin: 0 auto; padding: 20px; }

  /* Stat Cards Row */
  .stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
  .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px 20px; transition: all var(--transition); }
  .stat-card:hover { border-color: var(--border-light); box-shadow: var(--shadow); }
  .stat-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); margin-bottom: 6px; }
  .stat-value { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; line-height: 1.2; }
  .stat-sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

  /* Grid Layout */
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; margin-bottom: 20px; }

  /* Cards */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; transition: all var(--transition); }
  .card:hover { border-color: var(--border-light); }
  .card-header { padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.01); }
  .card-header-icon { width: 28px; height: 28px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 14px; margin-right: 10px; }
  .card-header-left { display: flex; align-items: center; }
  .card-header .tag { font-size: 10px; padding: 3px 8px; border-radius: 6px; background: var(--accent-glow); color: var(--accent); font-weight: 600; text-transform: none; letter-spacing: 0; }
  .card-body { padding: 16px 18px; }

  /* Status Indicator */
  .status-indicator { display: inline-flex; align-items: center; gap: 7px; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .status-dot.green { background: var(--green); box-shadow: 0 0 6px rgba(34,197,94,0.4); }
  .status-dot.red { background: var(--red); box-shadow: 0 0 6px rgba(239,68,68,0.4); }
  .status-dot.yellow { background: var(--yellow); box-shadow: 0 0 6px rgba(234,179,8,0.4); }

  /* Key-Value Rows */
  .kv { display: flex; justify-content: space-between; align-items: center; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
  .kv:last-child { border-bottom: none; }
  .kv .label { color: var(--text-muted); font-size: 13px; }
  .kv .value { font-weight: 600; font-size: 13px; }
  .kv .value.green { color: var(--green); }
  .kv .value.red { color: var(--red); }

  /* Tables */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--text-muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 12px; border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.01); position: sticky; top: 0; z-index: 1; }
  td { padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.03); }
  tr:hover td { background: rgba(255,255,255,0.015); }
  tr:last-child td { border-bottom: none; }

  /* Badges */
  .badge { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; letter-spacing: 0.2px; }
  .badge-green { background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }
  .badge-red { background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }
  .badge-yellow { background: var(--yellow-bg); color: var(--yellow); border: 1px solid var(--yellow-border); }

  /* Query Section */
  .query-section { margin-top: 0; }
  .query-section textarea { width: 100%; min-height: 100px; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 14px 16px; border-radius: var(--radius); font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 13px; line-height: 1.6; resize: vertical; transition: border-color var(--transition); }
  .query-section textarea:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
  .query-section textarea::placeholder { color: var(--text-muted); }
  .query-controls { display: flex; gap: 10px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
  .query-controls select { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 9px 12px; border-radius: var(--radius); font-size: 13px; cursor: pointer; }
  .query-controls select:focus { outline: none; border-color: var(--accent); }
  .result-table-wrap { max-height: 500px; overflow: auto; margin-top: 16px; border: 1px solid var(--border); border-radius: var(--radius); }
  .result-table-wrap table { font-size: 12px; }
  .result-table-wrap th { background: var(--bg-elevated); }

  /* Quick Query Buttons */
  .quick-queries { display: flex; flex-wrap: wrap; gap: 8px; }
  .quick-queries .btn { font-size: 12px; padding: 7px 14px; }

  /* Loading & Error */
  .loading { color: var(--text-muted); padding: 24px; text-align: center; font-size: 13px; }
  .loading-spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error-msg { color: var(--red); padding: 12px 16px; font-size: 13px; background: var(--red-bg); border: 1px solid var(--red-border); border-radius: var(--radius); margin-top: 12px; }

  /* Full Width */
  .full-width { grid-column: 1 / -1; }

  /* Section Labels */
  .section-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); margin-bottom: 12px; padding-left: 2px; }

  /* Worker Row for mobile */
  .worker-row-mobile { display: none; }

  /* ==================== RESPONSIVE ==================== */
  @media (max-width: 768px) {
    .header { padding: 12px 16px; }
    .header h1 { font-size: 15px; }
    .header .meta { display: none; }
    .auth-bar { padding: 10px 16px; flex-wrap: wrap; }
    .auth-bar input { flex-basis: 100%; }
    .refresh-wrap { margin-left: 0; width: 100%; justify-content: space-between; }
    .container { padding: 12px; }
    .stat-row { grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 14px; }
    .stat-card { padding: 14px 16px; }
    .stat-value { font-size: 22px; }
    .grid { grid-template-columns: 1fr; gap: 12px; margin-bottom: 14px; }
    .card-body { padding: 12px 14px; }
    .card-header { padding: 12px 14px; }

    /* Responsive tables — card layout on mobile */
    .table-responsive table { display: block; }
    .table-responsive thead { display: none; }
    .table-responsive tbody { display: block; }
    .table-responsive tr { display: flex; flex-wrap: wrap; padding: 10px 0; border-bottom: 1px solid var(--border); gap: 4px 16px; }
    .table-responsive tr:last-child { border-bottom: none; }
    .table-responsive td { display: inline-flex; padding: 2px 0; border: none; font-size: 13px; }
    .table-responsive td:before { content: attr(data-label); color: var(--text-muted); margin-right: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
    .table-responsive tr:hover td { background: transparent; }

    .query-section textarea { min-height: 80px; font-size: 12px; }
    .query-controls { gap: 8px; }
    .quick-queries .btn { font-size: 11px; padding: 6px 10px; }
    .result-table-wrap { max-height: 300px; }
  }

  @media (max-width: 420px) {
    .stat-row { grid-template-columns: 1fr 1fr; gap: 8px; }
    .stat-card { padding: 12px; }
    .stat-value { font-size: 20px; }
    .logo-icon { width: 28px; height: 28px; font-size: 14px; border-radius: 6px; }
    .header h1 { font-size: 14px; }
  }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo-icon">E</div>
    <h1><span class="brand">TheEyeBeta</span> Admin</h1>
  </div>
  <div class="meta">
    <span class="live-dot" id="live-dot" style="display:none"></span>
    <span id="timestamp">Not connected</span>
  </div>
</div>

<div class="auth-bar">
  <input type="password" id="token-input" placeholder="Paste bearer token (admin:read scope)" autocomplete="off">
  <button class="btn btn-primary" onclick="authenticate()">Connect</button>
  <span id="auth-status"></span>
  <div class="refresh-wrap">
    <div class="auto-refresh">
      <label class="toggle"><input type="checkbox" id="auto-refresh-toggle" onchange="toggleAutoRefresh()"><span class="slider"></span></label>
      <span>Auto 30s</span>
    </div>
    <button class="btn btn-ghost" onclick="loadDashboard()" title="Refresh">&#x21bb; Refresh</button>
  </div>
</div>

<div class="container">
  <!-- Stat Cards -->
  <div class="stat-row" id="stat-row">
    <div class="stat-card">
      <div class="stat-label">API Status</div>
      <div class="stat-value" id="stat-api" style="color:var(--text-muted)">--</div>
      <div class="stat-sub" id="stat-api-sub">Waiting for auth</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Database</div>
      <div class="stat-value" id="stat-db" style="color:var(--text-muted)">--</div>
      <div class="stat-sub" id="stat-db-sub">Waiting for auth</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Active Tickers</div>
      <div class="stat-value" id="stat-tickers" style="color:var(--text-muted)">--</div>
      <div class="stat-sub" id="stat-tickers-sub">&nbsp;</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Workers</div>
      <div class="stat-value" id="stat-workers" style="color:var(--text-muted)">--</div>
      <div class="stat-sub" id="stat-workers-sub">&nbsp;</div>
    </div>
  </div>

  <!-- Status Cards Row -->
  <div class="section-label">System Overview</div>
  <div class="grid" id="status-grid">
    <div class="card">
      <div class="card-header"><div class="card-header-left"><div class="card-header-icon" style="background:var(--accent-glow);color:var(--accent)">&#9881;</div>Data API Server</div></div>
      <div class="card-body" id="api-status"><div class="loading">Authenticate to view</div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-header-left"><div class="card-header-icon" style="background:var(--green-bg);color:var(--green)">&#9731;</div>Database</div></div>
      <div class="card-body" id="db-status"><div class="loading">Authenticate to view</div></div>
    </div>
  </div>

  <div class="section-label">Engine & Data</div>
  <div class="grid">
    <div class="card">
      <div class="card-header"><div class="card-header-left"><div class="card-header-icon" style="background:rgba(249,115,22,0.1);color:var(--orange)">&#9889;</div>Engine Workers</div><span class="tag" id="worker-count-tag">0 workers</span></div>
      <div class="card-body table-responsive" id="engine-status"><div class="loading">Authenticate to view</div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-header-left"><div class="card-header-icon" style="background:rgba(139,92,246,0.1);color:#8b5cf6">&#9638;</div>Table Row Counts</div></div>
      <div class="card-body table-responsive" id="table-counts"><div class="loading">Authenticate to view</div></div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-header"><div class="card-header-left"><div class="card-header-icon" style="background:var(--yellow-bg);color:var(--yellow)">&#9733;</div>Service Clients</div></div>
      <div class="card-body table-responsive" id="service-clients"><div class="loading">Authenticate to view</div></div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-header-left"><div class="card-header-icon" style="background:var(--red-bg);color:var(--red)">&#9888;</div>Recent Audit Events</div></div>
      <div class="card-body table-responsive" id="audit-events"><div class="loading">Authenticate to view</div></div>
    </div>
  </div>

  <!-- Query Section -->
  <div class="section-label">Query Console</div>
  <div class="card full-width query-section">
    <div class="card-header">
      <div class="card-header-left"><div class="card-header-icon" style="background:var(--accent-glow);color:var(--accent)">&#62;&gt;</div>SQL Query</div>
      <span class="tag">Read-only</span>
    </div>
    <div class="card-body">
      <select id="query-name" style="width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;margin-bottom:8px">
        <option value="all_tickers">All Tickers</option>
        <option value="latest_prices">Latest Prices</option>
        <option value="latest_signals">Latest Signals</option>
        <option value="orders">Orders</option>
        <option value="portfolio">Portfolio Positions</option>
        <option value="command_log">Audit Log</option>
        <option value="market_news">Market News</option>
        <option value="heartbeats">Worker Heartbeats</option>
        <option value="table_stats">Table Stats</option>
      </select>
      <div class="query-controls">
        <button class="btn btn-primary" onclick="runQuery()">Execute</button>
        <select id="query-limit">
          <option value="25">25 rows</option>
          <option value="50">50 rows</option>
          <option value="100" selected>100 rows</option>
          <option value="500">500 rows</option>
        </select>
        <span id="query-status" style="color:var(--text-muted);font-size:12px;font-weight:500"></span>
      </div>
      <div id="query-results"></div>
    </div>
  </div>
</div>

<script>
let TOKEN = '';
let autoRefreshTimer = null;
const BASE = window.location.origin;

function authenticate() {
  TOKEN = document.getElementById('token-input').value.trim();
  if (!TOKEN) { setAuthStatus('Enter a token', 'red'); return; }
  setAuthStatus('Connecting...', 'yellow');
  loadDashboard();
}

function setAuthStatus(msg, color) {
  const el = document.getElementById('auth-status');
  el.textContent = msg;
  el.style.color = `var(--${color || 'text-muted'})`;
}

function toggleAutoRefresh() {
  const on = document.getElementById('auto-refresh-toggle').checked;
  if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
  if (on && TOKEN) { autoRefreshTimer = setInterval(loadDashboard, 30000); }
}

async function apiFetch(path) {
  const resp = await fetch(BASE + path, {
    headers: { 'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/json' }
  });
  if (!resp.ok) {
    const body = await resp.text();
    let message = body;
    let code = '';
    try {
      const parsed = JSON.parse(body);
      message = parsed.error?.message || body;
      code = parsed.error?.code || '';
    } catch {
      // Keep the raw response body when the server returns non-JSON content.
    }
    const err = new Error(`${resp.status}: ${message}`);
    err.status = resp.status;
    err.code = code;
    throw err;
  }
  return resp.json();
}

async function loadDashboard() {
  if (!TOKEN) return;
  try {
    const data = await apiFetch('/api/v1/admin/dashboard-data');
    setAuthStatus('Connected', 'green');
    document.getElementById('live-dot').style.display = 'inline-block';
    document.getElementById('timestamp').textContent = new Date(data.timestamp).toLocaleString();

    // Stat cards
    const apiOk = data.api.status === 'running';
    document.getElementById('stat-api').textContent = apiOk ? 'Online' : 'Down';
    document.getElementById('stat-api').style.color = apiOk ? 'var(--green)' : 'var(--red)';
    document.getElementById('stat-api-sub').textContent = data.api.version;

    const dbOk = data.database.connected;
    document.getElementById('stat-db').textContent = dbOk ? 'Connected' : 'Down';
    document.getElementById('stat-db').style.color = dbOk ? 'var(--green)' : 'var(--red)';
    document.getElementById('stat-db-sub').textContent = dbOk ? data.database.version.split(' ').slice(0,2).join(' ') : 'Unreachable';

    const tickerCount = data.active_tickers || 0;
    document.getElementById('stat-tickers').textContent = tickerCount.toLocaleString();
    document.getElementById('stat-tickers').style.color = 'var(--text)';
    document.getElementById('stat-tickers-sub').textContent = 'monitored';

    const workers = data.engine_workers || [];
    const healthyWorkers = workers.filter(w => w.status === 'running' && (w.seconds_ago === null || w.seconds_ago <= 120)).length;
    document.getElementById('stat-workers').textContent = healthyWorkers + '/' + workers.length;
    document.getElementById('stat-workers').style.color = healthyWorkers === workers.length ? 'var(--green)' : (healthyWorkers > 0 ? 'var(--yellow)' : 'var(--red)');
    document.getElementById('stat-workers-sub').textContent = healthyWorkers === workers.length ? 'all healthy' : (workers.length - healthyWorkers) + ' degraded';

    renderApiStatus(data.api);
    renderDbStatus(data.database);
    renderEngineWorkers(workers);
    renderTableCounts(data.tables);
    renderServiceClients(data.service_clients);
    renderAuditEvents(data.recent_events);

    // Start auto-refresh if toggled
    if (document.getElementById('auto-refresh-toggle').checked && !autoRefreshTimer) {
      autoRefreshTimer = setInterval(loadDashboard, 30000);
    }
  } catch (e) {
    setAuthStatus('Auth failed: ' + e.message, 'red');
    document.getElementById('live-dot').style.display = 'none';
  }
}

function renderApiStatus(api) {
  document.getElementById('api-status').innerHTML = `
    <div class="kv"><span class="label">Status</span><span class="value green"><span class="status-indicator"><span class="status-dot green"></span>${api.status}</span></span></div>
    <div class="kv"><span class="label">Name</span><span class="value">${escapeHtml(api.name)}</span></div>
    <div class="kv"><span class="label">Version</span><span class="value">${escapeHtml(api.version)}</span></div>
    <div class="kv"><span class="label">Environment</span><span class="value">${escapeHtml(api.environment)}</span></div>
    <div class="kv"><span class="label">Bind</span><span class="value">${escapeHtml(api.host)}:${api.port}</span></div>
  `;
}

function renderDbStatus(db) {
  const color = db.connected ? 'green' : 'red';
  const label = db.connected ? 'Connected' : 'Disconnected';
  document.getElementById('db-status').innerHTML = `
    <div class="kv"><span class="label">Connection</span><span class="value ${color}"><span class="status-indicator"><span class="status-dot ${color}"></span>${label}</span></span></div>
    <div class="kv"><span class="label">Version</span><span class="value" style="font-size:12px">${escapeHtml(db.version)}</span></div>
    <div class="kv"><span class="label">URL</span><span class="value" style="font-size:11px;word-break:break-all;max-width:60%">${escapeHtml(db.url_masked)}</span></div>
  `;
}

function renderEngineWorkers(workers) {
  if (!workers || workers.length === 0) {
    document.getElementById('engine-status').innerHTML = '<div class="loading">No heartbeat data</div>';
    document.getElementById('worker-count-tag').textContent = '0 workers';
    return;
  }
  document.getElementById('worker-count-tag').textContent = workers.length + ' workers';
  let html = '<table><thead><tr><th>Worker</th><th>Status</th><th>Last Beat</th><th>Ago</th></tr></thead><tbody>';
  for (const w of workers) {
    const stale = w.seconds_ago !== null && w.seconds_ago > 120;
    const color = stale ? 'red' : (w.status === 'running' ? 'green' : 'yellow');
    const ago = w.seconds_ago !== null ? (w.seconds_ago < 60 ? w.seconds_ago + 's' : Math.round(w.seconds_ago/60) + 'm') : '&#8212;';
    const beat = w.last_heartbeat ? escapeHtml(w.last_heartbeat) : '&#8212;';
    html += '<tr>';
    html += '<td data-label="Worker">' + escapeHtml(w.worker_name) + '</td>';
    html += '<td data-label="Status"><span class="badge badge-' + color + '">' + escapeHtml(w.status) + '</span></td>';
    html += '<td data-label="Beat" style="font-size:11px">' + beat + '</td>';
    html += '<td data-label="Ago">' + ago + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  document.getElementById('engine-status').innerHTML = html;
}

function renderTableCounts(tables) {
  if (!tables || tables.length === 0) {
    document.getElementById('table-counts').innerHTML = '<div class="loading">No data</div>';
    return;
  }
  let html = '<table><thead><tr><th>Table</th><th style="text-align:right">Rows</th></tr></thead><tbody>';
  for (const t of tables) {
    const val = t.row_count < 0 ? '<span style="color:var(--red)">N/A</span>' : t.row_count.toLocaleString();
    html += '<tr><td data-label="Table">' + escapeHtml(t.table) + '</td><td data-label="Rows" style="text-align:right;font-variant-numeric:tabular-nums">' + val + '</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('table-counts').innerHTML = html;
}

function renderServiceClients(clients) {
  if (!clients || clients.length === 0) {
    document.getElementById('service-clients').innerHTML = '<div class="loading">No service clients found</div>';
    return;
  }
  let html = '<table><thead><tr><th>Client ID</th><th>Name</th><th>Active</th><th>Scopes</th></tr></thead><tbody>';
  for (const c of clients) {
    const active = c.is_active ? '<span class="badge badge-green">active</span>' : '<span class="badge badge-red">inactive</span>';
    html += '<tr>';
    html += '<td data-label="ID" style="font-family:monospace;font-size:11px">' + escapeHtml(c.client_id) + '</td>';
    html += '<td data-label="Name">' + escapeHtml(c.display_name || '&#8212;') + '</td>';
    html += '<td data-label="Active">' + active + '</td>';
    html += '<td data-label="Scopes">' + c.scope_count + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  document.getElementById('service-clients').innerHTML = html;
}

function renderAuditEvents(events) {
  if (!events || events.length === 0) {
    document.getElementById('audit-events').innerHTML = '<div class="loading">No recent events</div>';
    return;
  }
  let html = '<table><thead><tr><th>Type</th><th>Category</th><th>Severity</th><th>Time</th></tr></thead><tbody>';
  for (const e of events) {
    const sev = e.severity || 'info';
    const sevColor = sev === 'error' ? 'red' : (sev === 'warning' ? 'yellow' : 'green');
    html += '<tr>';
    html += '<td data-label="Type">' + escapeHtml(e.event_type || '&#8212;') + '</td>';
    html += '<td data-label="Category">' + escapeHtml(e.event_category || '&#8212;') + '</td>';
    html += '<td data-label="Severity"><span class="badge badge-' + sevColor + '">' + escapeHtml(sev) + '</span></td>';
    html += '<td data-label="Time" style="font-size:11px;white-space:nowrap">' + escapeHtml(e.created_at || '&#8212;') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  document.getElementById('audit-events').innerHTML = html;
}

async function runQuery() {
  if (!TOKEN) { setAuthStatus('Authenticate first', 'red'); return; }
  const queryName = document.getElementById('query-name').value;
  if (!queryName) return;
  const limit = document.getElementById('query-limit').value;
  const statusEl = document.getElementById('query-status');
  statusEl.innerHTML = '<span class="loading-spinner"></span>Executing...';
  try {
    const t0 = performance.now();
    const data = await apiFetch('/api/v1/admin/named-query?query_name=' + encodeURIComponent(queryName) + '&limit=' + limit);
    const ms = Math.round(performance.now() - t0);
    statusEl.textContent = data.row_count + ' rows in ' + ms + 'ms';
    renderQueryResults(data.rows);
  } catch (e) {
    statusEl.textContent = '';
    const resultsEl = document.getElementById('query-results');
    if (e.code === 'DATABASE_UNAVAILABLE') {
      resultsEl.innerHTML = '';
      return;
    }
    resultsEl.innerHTML = '<div class="error-msg">' + escapeHtml(e.message) + '</div>';
  }
}

function renderQueryResults(rows) {
  const wrap = document.getElementById('query-results');
  if (!rows || rows.length === 0) {
    wrap.innerHTML = '<div class="loading">No results</div>';
    return;
  }
  const cols = Object.keys(rows[0]);
  let html = '<div class="result-table-wrap"><table><thead><tr>';
  for (const c of cols) html += '<th>' + escapeHtml(c) + '</th>';
  html += '</tr></thead><tbody>';
  for (const row of rows) {
    html += '<tr>';
    for (const c of cols) {
      const raw = row[c];
      const val = raw !== null ? String(raw) : '<span style="color:var(--text-muted);font-style:italic">null</span>';
      html += '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (raw !== null ? escapeHtml(val) : val) + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  wrap.innerHTML = html;
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// Keyboard shortcut: Ctrl+Enter to run query
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const active = document.activeElement;
    if (active && (active.id === 'query-name' || active.id === 'query-limit')) { e.preventDefault(); runQuery(); }
  }
});
</script>
</body>
</html>
"""
