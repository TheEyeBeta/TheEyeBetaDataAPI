"""Admin routes — dashboard UI + API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.dependencies.services import get_admin_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ADMIN_READ
from app.schemas.market import AdminAuditEventsResponse
from app.services.admin_service import AdminService

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


@router.get("/query")
def execute_query(
    q: str = Query(min_length=1, max_length=2000),
    limit: int = Query(default=100, ge=1, le=1000),
    _=Depends(require_scopes([SCOPE_ADMIN_READ])),
    service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """Execute a read-only SQL query."""
    result = service.execute_query(q, limit=limit)
    return JSONResponse(content=result)


@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard() -> HTMLResponse:
    """Serve the admin dashboard HTML page. Auth is handled client-side via token."""
    return HTMLResponse(content=_DASHBOARD_HTML)


_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TheEyeBeta DataAPI — Admin Dashboard</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #c9d1d9; --text-muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --red: #f85149; --yellow: #d29922; --orange: #db6d28;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }
  .header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 18px; font-weight: 600; }
  .header h1 span { color: var(--accent); }
  .header .meta { color: var(--text-muted); font-size: 12px; }
  .auth-bar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; gap: 8px; align-items: center; }
  .auth-bar input { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 13px; }
  .auth-bar button, .btn { background: var(--accent); color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; }
  .auth-bar button:hover, .btn:hover { opacity: 0.9; }
  .btn-secondary { background: var(--surface); border: 1px solid var(--border); color: var(--text); }
  .container { max-width: 1400px; margin: 0 auto; padding: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .card-header { padding: 12px 16px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); display: flex; align-items: center; justify-content: space-between; }
  .card-body { padding: 16px; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .status-dot.green { background: var(--green); }
  .status-dot.red { background: var(--red); }
  .status-dot.yellow { background: var(--yellow); }
  .kv { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border); }
  .kv:last-child { border-bottom: none; }
  .kv .label { color: var(--text-muted); }
  .kv .value { font-weight: 500; }
  .kv .value.green { color: var(--green); }
  .kv .value.red { color: var(--red); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--text-muted); font-weight: 500; padding: 8px; border-bottom: 1px solid var(--border); }
  td { padding: 8px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  .query-section { margin-top: 24px; }
  .query-section textarea { width: 100%; min-height: 80px; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 12px; border-radius: 6px; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 13px; resize: vertical; }
  .query-controls { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
  .query-controls select { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 8px; border-radius: 6px; }
  .result-table-wrap { max-height: 400px; overflow: auto; margin-top: 12px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .badge-green { background: rgba(63,185,80,0.15); color: var(--green); }
  .badge-red { background: rgba(248,81,73,0.15); color: var(--red); }
  .badge-yellow { background: rgba(210,153,34,0.15); color: var(--yellow); }
  .loading { color: var(--text-muted); padding: 24px; text-align: center; }
  .error-msg { color: var(--red); padding: 8px; font-size: 13px; }
  .full-width { grid-column: 1 / -1; }
  .worker-status { display: flex; align-items: center; gap: 6px; }
  #auth-status { font-size: 12px; }
</style>
</head>
<body>

<div class="header">
  <h1><span>TheEyeBeta</span> DataAPI Admin</h1>
  <div class="meta" id="timestamp"></div>
</div>

<div class="auth-bar">
  <input type="password" id="token-input" placeholder="Bearer token (from /api/v1/auth/service-token with admin:read scope)">
  <button onclick="authenticate()">Connect</button>
  <span id="auth-status"></span>
  <button class="btn-secondary" onclick="loadDashboard()" style="margin-left:auto">Refresh</button>
</div>

<div class="container">
  <!-- Connection Status Cards -->
  <div class="grid" id="status-grid">
    <div class="card">
      <div class="card-header">Data API Server</div>
      <div class="card-body" id="api-status"><div class="loading">Waiting for authentication...</div></div>
    </div>
    <div class="card">
      <div class="card-header">Database (Supabase/PostgreSQL)</div>
      <div class="card-body" id="db-status"><div class="loading">Waiting for authentication...</div></div>
    </div>
    <div class="card">
      <div class="card-header">Engine Workers</div>
      <div class="card-body" id="engine-status"><div class="loading">Waiting for authentication...</div></div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-header">Table Row Counts</div>
      <div class="card-body" id="table-counts"><div class="loading">—</div></div>
    </div>
    <div class="card">
      <div class="card-header">Service Clients (IAM)</div>
      <div class="card-body" id="service-clients"><div class="loading">—</div></div>
    </div>
    <div class="card">
      <div class="card-header">Recent Audit Events</div>
      <div class="card-body" id="audit-events"><div class="loading">—</div></div>
    </div>
  </div>

  <!-- Query Section -->
  <div class="card full-width query-section">
    <div class="card-header">
      Database Query Console
      <span style="font-size:11px;color:var(--text-muted);text-transform:none;letter-spacing:0">Read-only SELECT queries only</span>
    </div>
    <div class="card-body">
      <textarea id="query-input" placeholder="SELECT * FROM tickers WHERE is_active = true LIMIT 10"></textarea>
      <div class="query-controls">
        <button class="btn" onclick="runQuery()">Execute Query</button>
        <select id="query-limit">
          <option value="25">25 rows</option>
          <option value="50">50 rows</option>
          <option value="100" selected>100 rows</option>
          <option value="500">500 rows</option>
        </select>
        <span id="query-status" style="color:var(--text-muted);font-size:12px"></span>
      </div>
      <div id="query-results"></div>
    </div>
  </div>

  <!-- Preset Queries -->
  <div class="card full-width" style="margin-top:16px">
    <div class="card-header">Quick Queries (Engine Data)</div>
    <div class="card-body" style="display:flex;flex-wrap:wrap;gap:8px">
      <button class="btn btn-secondary" onclick="preset('SELECT ticker, company_name, is_active FROM tickers ORDER BY ticker LIMIT 50')">All Tickers</button>
      <button class="btn btn-secondary" onclick="preset('SELECT t.ticker, ls.last_price, ls.price_change_pct, ls.rsi_14, ls.updated_at FROM latest_snapshot ls JOIN tickers t ON t.ticker_id = ls.ticker_id ORDER BY ls.updated_at DESC LIMIT 25')">Latest Prices</button>
      <button class="btn btn-secondary" onclick="preset('SELECT t.ticker, ls.latest_signal, ls.signal_confidence, ls.signal_strategy, ls.signal_ts FROM latest_snapshot ls JOIN tickers t ON t.ticker_id = ls.ticker_id WHERE ls.latest_signal IS NOT NULL ORDER BY ls.signal_ts DESC LIMIT 25')">Latest Signals</button>
      <button class="btn btn-secondary" onclick="preset('SELECT * FROM paper_trades ORDER BY created_at DESC LIMIT 20')">Recent Trades</button>
      <button class="btn btn-secondary" onclick="preset('SELECT * FROM portfolio_positions ORDER BY quantity DESC LIMIT 20')">Portfolio Positions</button>
      <button class="btn btn-secondary" onclick="preset('SELECT * FROM portfolio_valuation ORDER BY valuation_date DESC LIMIT 5')">Portfolio Valuation</button>
      <button class="btn btn-secondary" onclick="preset('SELECT command_id, command_type, status, operator_id, created_at FROM trask_command_log ORDER BY created_at DESC LIMIT 20')">Command Log</button>
      <button class="btn btn-secondary" onclick="preset('SELECT * FROM market_news ORDER BY published_at DESC LIMIT 15')">Market News</button>
      <button class="btn btn-secondary" onclick="preset('SELECT * FROM engine_worker_heartbeats ORDER BY worker_name')">Engine Heartbeats</button>
    </div>
  </div>
</div>

<script>
let TOKEN = '';
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

async function apiFetch(path) {
  const resp = await fetch(BASE + path, {
    headers: { 'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/json' }
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status}: ${body}`);
  }
  return resp.json();
}

async function loadDashboard() {
  if (!TOKEN) return;
  try {
    const data = await apiFetch('/api/v1/admin/dashboard-data');
    setAuthStatus('Connected', 'green');
    document.getElementById('timestamp').textContent = 'Last updated: ' + new Date(data.timestamp).toLocaleString();
    renderApiStatus(data.api);
    renderDbStatus(data.database);
    renderEngineWorkers(data.engine_workers);
    renderTableCounts(data.tables);
    renderServiceClients(data.service_clients);
    renderAuditEvents(data.recent_events);
  } catch (e) {
    setAuthStatus('Auth failed: ' + e.message, 'red');
  }
}

function renderApiStatus(api) {
  document.getElementById('api-status').innerHTML = `
    <div class="kv"><span class="label">Status</span><span class="value green"><span class="status-dot green"></span>${api.status}</span></div>
    <div class="kv"><span class="label">Name</span><span class="value">${api.name}</span></div>
    <div class="kv"><span class="label">Version</span><span class="value">${api.version}</span></div>
    <div class="kv"><span class="label">Environment</span><span class="value">${api.environment}</span></div>
    <div class="kv"><span class="label">Listening</span><span class="value">${api.host}:${api.port}</span></div>
  `;
}

function renderDbStatus(db) {
  const color = db.connected ? 'green' : 'red';
  const label = db.connected ? 'Connected' : 'Disconnected';
  document.getElementById('db-status').innerHTML = `
    <div class="kv"><span class="label">Connection</span><span class="value ${color}"><span class="status-dot ${color}"></span>${label}</span></div>
    <div class="kv"><span class="label">Version</span><span class="value" style="font-size:12px">${db.version}</span></div>
    <div class="kv"><span class="label">URL</span><span class="value" style="font-size:11px;word-break:break-all">${db.url_masked}</span></div>
  `;
}

function renderEngineWorkers(workers) {
  if (!workers || workers.length === 0) {
    document.getElementById('engine-status').innerHTML = '<div class="loading">No heartbeat data (engine_worker_heartbeats table may not exist)</div>';
    return;
  }
  let html = '<table><tr><th>Worker</th><th>Status</th><th>Last Beat</th><th>Ago</th></tr>';
  for (const w of workers) {
    const stale = w.seconds_ago !== null && w.seconds_ago > 120;
    const color = stale ? 'red' : (w.status === 'running' ? 'green' : 'yellow');
    const ago = w.seconds_ago !== null ? (w.seconds_ago < 60 ? w.seconds_ago + 's' : Math.round(w.seconds_ago/60) + 'm') : '—';
    html += `<tr>
      <td>${w.worker_name}</td>
      <td><span class="badge badge-${color}">${w.status}</span></td>
      <td style="font-size:11px">${w.last_heartbeat || '—'}</td>
      <td>${ago}</td>
    </tr>`;
  }
  html += '</table>';
  document.getElementById('engine-status').innerHTML = html;
}

function renderTableCounts(tables) {
  if (!tables || tables.length === 0) {
    document.getElementById('table-counts').innerHTML = '<div class="loading">No data</div>';
    return;
  }
  let html = '<table><tr><th>Table</th><th style="text-align:right">Rows</th></tr>';
  for (const t of tables) {
    const val = t.row_count < 0 ? '<span style="color:var(--red)">N/A</span>' : t.row_count.toLocaleString();
    html += `<tr><td>${t.table}</td><td style="text-align:right">${val}</td></tr>`;
  }
  html += '</table>';
  document.getElementById('table-counts').innerHTML = html;
}

function renderServiceClients(clients) {
  if (!clients || clients.length === 0) {
    document.getElementById('service-clients').innerHTML = '<div class="loading">No service clients found</div>';
    return;
  }
  let html = '<table><tr><th>Client ID</th><th>Name</th><th>Active</th><th>Scopes</th></tr>';
  for (const c of clients) {
    const active = c.is_active ? '<span class="badge badge-green">yes</span>' : '<span class="badge badge-red">no</span>';
    html += `<tr><td>${c.client_id}</td><td>${c.display_name || '—'}</td><td>${active}</td><td>${c.scope_count}</td></tr>`;
  }
  html += '</table>';
  document.getElementById('service-clients').innerHTML = html;
}

function renderAuditEvents(events) {
  if (!events || events.length === 0) {
    document.getElementById('audit-events').innerHTML = '<div class="loading">No recent events</div>';
    return;
  }
  let html = '<table><tr><th>Type</th><th>Category</th><th>Severity</th><th>Time</th></tr>';
  for (const e of events) {
    const sev = e.severity || 'info';
    const sevColor = sev === 'error' ? 'red' : (sev === 'warning' ? 'yellow' : 'green');
    html += `<tr>
      <td>${e.event_type || '—'}</td>
      <td>${e.event_category || '—'}</td>
      <td><span class="badge badge-${sevColor}">${sev}</span></td>
      <td style="font-size:11px">${e.created_at || '—'}</td>
    </tr>`;
  }
  html += '</table>';
  document.getElementById('audit-events').innerHTML = html;
}

function preset(sql) {
  document.getElementById('query-input').value = sql;
  runQuery();
}

async function runQuery() {
  if (!TOKEN) { setAuthStatus('Authenticate first', 'red'); return; }
  const q = document.getElementById('query-input').value.trim();
  if (!q) return;
  const limit = document.getElementById('query-limit').value;
  const statusEl = document.getElementById('query-status');
  statusEl.textContent = 'Executing...';
  try {
    const t0 = performance.now();
    const data = await apiFetch('/api/v1/admin/query?limit=' + limit + '&q=' + encodeURIComponent(q));
    const ms = Math.round(performance.now() - t0);
    statusEl.textContent = `${data.row_count} rows in ${ms}ms`;
    renderQueryResults(data.rows);
  } catch (e) {
    statusEl.textContent = '';
    document.getElementById('query-results').innerHTML = '<div class="error-msg">' + escapeHtml(e.message) + '</div>';
  }
}

function renderQueryResults(rows) {
  const wrap = document.getElementById('query-results');
  if (!rows || rows.length === 0) {
    wrap.innerHTML = '<div class="loading">No results</div>';
    return;
  }
  const cols = Object.keys(rows[0]);
  let html = '<div class="result-table-wrap"><table><tr>';
  for (const c of cols) html += '<th>' + escapeHtml(c) + '</th>';
  html += '</tr>';
  for (const row of rows) {
    html += '<tr>';
    for (const c of cols) {
      const val = row[c] !== null ? String(row[c]) : '<span style="color:var(--text-muted)">null</span>';
      html += '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (row[c] !== null ? escapeHtml(val) : val) + '</td>';
    }
    html += '</tr>';
  }
  html += '</table></div>';
  wrap.innerHTML = html;
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
</script>
</body>
</html>
"""
