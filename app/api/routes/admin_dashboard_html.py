"""Inline HTML for GET /api/v1/admin/dashboard (ops viewer/controller)."""

from __future__ import annotations

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TheEyeBeta DataAPI — Ops</title>
<style>
  :root {
    --bg: #090B0F;
    --bg-elevated: #0D1015;
    --surface: #141820;
    --surface-hover: #1a2030;
    --border: #29303C;
    --border-light: #3a4454;
    --text: #D4DAE3;
    --text-secondary: #8E97A3;
    --text-muted: #6B7380;
    --primary: #E5A83A;
    --primary-fg: #090B10;
    --primary-glow: rgba(229,168,58,0.18);
    --accent: #31C47A;
    --accent-bg: rgba(49,196,122,0.12);
    --accent-border: rgba(49,196,122,0.28);
    --red: #E54D4A;
    --red-bg: rgba(229,77,74,0.12);
    --red-border: rgba(229,77,74,0.28);
    --yellow: #E5A83A;
    --yellow-bg: rgba(229,168,58,0.12);
    --yellow-border: rgba(229,168,58,0.28);
    --radius: 2px;
    --shadow: 0 1px 2px rgba(0,0,0,0.35);
    --transition: 140ms ease;
    --font: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
    --mono: "IBM Plex Mono", "SF Mono", Consolas, monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--text);
    font-family: var(--font); font-size: 14px; line-height: 1.5;
    min-height: 100vh;
  }
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .header {
    background: var(--bg-elevated); border-bottom: 1px solid var(--border);
    padding: 14px 20px; display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 50;
  }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .logo {
    width: 28px; height: 28px; background: var(--primary); color: var(--primary-fg);
    display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px;
    border-radius: var(--radius);
  }
  .header h1 { font-size: 16px; font-weight: 650; letter-spacing: -0.2px; }
  .header h1 .brand { color: var(--primary); }
  .meta { color: var(--text-muted); font-size: 12px; display: flex; align-items: center; gap: 8px; }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }

  .auth-bar {
    background: var(--bg); border-bottom: 1px solid var(--border);
    padding: 10px 20px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  }
  .auth-bar input[type="password"], .auth-bar input[type="text"], .field input, .field select, .field textarea {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 9px 12px; border-radius: var(--radius); font-size: 13px; font-family: inherit;
  }
  .auth-bar .cred { width: 200px; min-width: 140px; }
  .auth-bar .cred-wide { flex: 1; min-width: 180px; }
  .auth-bar input:focus, .field input:focus, .field select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary-glow); }
  .auth-advanced { width: 100%; display: none; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 4px; }
  .auth-advanced.open { display: flex; }
  .auth-hint { font-size: 11px; color: var(--text-muted); width: 100%; }

  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 8px 14px; border-radius: var(--radius); cursor: pointer; font-size: 13px;
    font-weight: 600; border: none; transition: background var(--transition), border-color var(--transition);
    white-space: nowrap; font-family: inherit;
  }
  .btn-primary { background: var(--primary); color: var(--primary-fg); }
  .btn-primary:hover { filter: brightness(1.05); }
  .btn-secondary { background: var(--surface); border: 1px solid var(--border); color: var(--text-secondary); }
  .btn-secondary:hover { border-color: var(--border-light); color: var(--text); }
  .btn-danger { background: var(--red-bg); border: 1px solid var(--red-border); color: var(--red); }
  .btn-danger:hover { background: rgba(229,77,74,0.2); }
  .btn-ghost { background: transparent; color: var(--text-secondary); }
  .btn-ghost:hover { color: var(--text); background: var(--surface); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }

  .tabs {
    display: flex; gap: 0; border-bottom: 1px solid var(--border);
    padding: 0 20px; background: var(--bg-elevated); overflow-x: auto;
  }
  .tab {
    background: transparent; border: none; color: var(--text-muted);
    padding: 12px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
    border-bottom: 2px solid transparent; font-family: inherit; white-space: nowrap;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--primary); border-bottom-color: var(--primary); }

  .container { max-width: 1400px; margin: 0 auto; padding: 18px 20px 40px; }
  .panel { display: none; }
  .panel.active { display: block; }

  .stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }
  .stat-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 14px 16px;
  }
  .stat-label { font-size: 11px; font-weight: 650; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-muted); }
  .stat-value { font-size: 24px; font-weight: 700; margin-top: 4px; letter-spacing: -0.4px; }
  .stat-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

  .section-label {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.9px;
    color: var(--text-muted); margin: 18px 0 10px;
  }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px; margin-bottom: 14px; }
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden;
  }
  .card.full { grid-column: 1 / -1; }
  .card-header {
    padding: 11px 14px; border-bottom: 1px solid var(--border); font-size: 12px; font-weight: 650;
    text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-secondary);
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
  }
  .card-body { padding: 12px 14px; }
  .tag {
    font-size: 10px; padding: 2px 7px; border-radius: var(--radius);
    background: var(--primary-glow); color: var(--primary); font-weight: 650; text-transform: none; letter-spacing: 0;
  }

  .kv { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
  .kv:last-child { border-bottom: none; }
  .kv .label { color: var(--text-muted); }
  .kv .value { font-weight: 600; text-align: right; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left; color: var(--text-muted); font-weight: 650; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.4px; padding: 8px 10px;
    border-bottom: 1px solid var(--border); background: var(--bg-elevated);
  }
  td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.03); vertical-align: middle; }
  tr:hover td { background: rgba(255,255,255,0.015); }
  .mono { font-family: var(--mono); font-size: 12px; }
  .muted { color: var(--text-muted); }

  .badge {
    display: inline-flex; align-items: center; padding: 2px 8px; border-radius: var(--radius);
    font-size: 11px; font-weight: 650;
  }
  .badge-green { background: var(--accent-bg); color: var(--accent); border: 1px solid var(--accent-border); }
  .badge-red { background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }
  .badge-yellow { background: var(--yellow-bg); color: var(--yellow); border: 1px solid var(--yellow-border); }
  .badge-primary { background: var(--primary-glow); color: var(--primary); border: 1px solid rgba(229,168,58,0.35); }
  .badge-muted { background: rgba(142,151,163,0.12); color: var(--text-secondary); border: 1px solid var(--border); }

  .flow {
    display: flex; align-items: stretch; gap: 8px; flex-wrap: wrap; margin-bottom: 14px;
  }
  .flow-node {
    flex: 1; min-width: 140px; background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 12px;
  }
  .flow-node h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-muted); margin-bottom: 6px; }
  .flow-node .flow-main { font-size: 15px; font-weight: 700; }
  .flow-arrow {
    align-self: center; color: var(--primary); font-weight: 700; font-size: 18px; padding: 0 2px;
  }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
  .status-dot.green { background: var(--accent); }
  .status-dot.red { background: var(--red); }
  .status-dot.yellow { background: var(--yellow); }

  .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
  .toolbar input[type="search"] { flex: 1; min-width: 180px; background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: var(--radius); }
  .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 10px; }
  .field label { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 650; }
  .field input, .field select { width: 100%; }
  .hint { font-size: 12px; color: var(--text-muted); margin-top: 6px; }
  .error-msg { color: var(--red); padding: 10px 12px; background: var(--red-bg); border: 1px solid var(--red-border); border-radius: var(--radius); margin-top: 10px; font-size: 13px; }
  .ok-msg { color: var(--accent); padding: 10px 12px; background: var(--accent-bg); border: 1px solid var(--accent-border); border-radius: var(--radius); margin-top: 10px; font-size: 13px; }
  .loading { color: var(--text-muted); padding: 20px; text-align: center; }
  .write-only { display: none; }
  .can-write .write-only { display: block; }
  .table-wrap { max-height: 480px; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius); }
  .result-table-wrap { max-height: 420px; overflow: auto; margin-top: 12px; border: 1px solid var(--border); border-radius: var(--radius); }
  .query-controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 10px; }
  .query-controls select { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 8px 10px; border-radius: var(--radius); }
  .block-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .block-row input { width: 140px; }

  @media (max-width: 800px) {
    .stat-row { grid-template-columns: 1fr 1fr; }
    .flow-arrow { display: none; }
    .container { padding: 12px; }
  }
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="logo">E</div>
    <h1><span class="brand">TheEyeBeta</span> DataAPI Ops</h1>
  </div>
  <div class="meta">
    <span class="live-dot" id="live-dot" style="display:none"></span>
    <span id="timestamp">Not connected</span>
  </div>
</div>

<div class="auth-bar" id="auth-bar">
  <input type="text" class="cred" id="client-id-input" placeholder="Client ID (e.g. admin-tool-production)" autocomplete="username">
  <input type="password" class="cred-wide" id="client-secret-input" placeholder="Client secret" autocomplete="current-password">
  <button class="btn btn-primary" id="btn-signin" onclick="signIn()">Sign in</button>
  <button class="btn btn-ghost" id="btn-signout" onclick="signOut()" style="display:none">Sign out</button>
  <span id="auth-status" class="muted"></span>
  <div style="margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
    <label class="muted" style="display:flex;align-items:center;gap:6px;font-size:12px;">
      <input type="checkbox" id="remember-session" checked> Keep signed in (this browser tab)
    </label>
    <button class="btn btn-ghost" type="button" onclick="toggleAdvancedAuth()">Advanced</button>
    <label class="muted" style="display:flex;align-items:center;gap:6px;font-size:12px;">
      <input type="checkbox" id="auto-refresh-toggle" onchange="toggleAutoRefresh()"> Auto 30s
    </label>
    <button class="btn btn-ghost" onclick="refreshAll()">Refresh</button>
  </div>
  <div class="auth-hint">Official login: service client credentials → <code>/api/v1/auth/service-token</code>. Save the secret once in your password manager; no SSH minting each visit.</div>
  <div class="auth-advanced" id="auth-advanced">
    <input type="password" class="cred-wide" id="token-input" placeholder="Or paste bearer token" autocomplete="off">
    <button class="btn btn-secondary" onclick="authenticateWithToken()">Use token</button>
  </div>
</div>

<nav class="tabs" id="tabs">
  <button class="tab active" data-tab="overview" onclick="showTab('overview')">Overview</button>
  <button class="tab" data-tab="connections" onclick="showTab('connections')">Connections</button>
  <button class="tab" data-tab="telemetry" onclick="showTab('telemetry')">Telemetry</button>
  <button class="tab" data-tab="tables" onclick="showTab('tables')">Tables</button>
  <button class="tab" data-tab="accounts" onclick="showTab('accounts')">Accounts</button>
  <button class="tab" data-tab="query" onclick="showTab('query')">Query</button>
</nav>

<div class="container" id="app">
  <section class="panel active" id="panel-overview">
    <div class="stat-row">
      <div class="stat-card"><div class="stat-label">API</div><div class="stat-value" id="stat-api">--</div><div class="stat-sub" id="stat-api-sub">Waiting</div></div>
      <div class="stat-card"><div class="stat-label">Database</div><div class="stat-value" id="stat-db">--</div><div class="stat-sub" id="stat-db-sub">Waiting</div></div>
      <div class="stat-card"><div class="stat-label">Tickers</div><div class="stat-value" id="stat-tickers">--</div><div class="stat-sub" id="stat-tickers-sub">&nbsp;</div></div>
      <div class="stat-card"><div class="stat-label">Workers</div><div class="stat-value" id="stat-workers">--</div><div class="stat-sub" id="stat-workers-sub">&nbsp;</div></div>
    </div>
    <div class="section-label">Product gates</div>
    <div class="grid" id="product-gates"><div class="card"><div class="card-body loading">Authenticate to view</div></div></div>
    <div class="section-label">System</div>
    <div class="grid">
      <div class="card"><div class="card-header">Data API</div><div class="card-body" id="api-status"><div class="loading">Authenticate to view</div></div></div>
      <div class="card"><div class="card-header">Database</div><div class="card-body" id="db-status"><div class="loading">Authenticate to view</div></div></div>
    </div>
  </section>

  <section class="panel" id="panel-connections">
    <div class="section-label">Service clients</div>
    <div class="card full">
      <div class="card-header">Connections <span class="tag" id="client-count-tag">0</span></div>
      <div class="card-body table-wrap" id="service-clients"><div class="loading">Authenticate to view</div></div>
    </div>
  </section>

  <section class="panel" id="panel-telemetry">
    <div class="section-label">Data flow</div>
    <div class="flow" id="data-flow">
      <div class="flow-node"><h3>Sources / ETL</h3><div class="flow-main" id="flow-etl">--</div><div class="muted" id="flow-etl-sub">jobs</div></div>
      <span class="flow-arrow">&rarr;</span>
      <div class="flow-node"><h3>Tables</h3><div class="flow-main" id="flow-tables">--</div><div class="muted" id="flow-tables-sub">row counts</div></div>
      <span class="flow-arrow">&rarr;</span>
      <div class="flow-node"><h3>DataAPI</h3><div class="flow-main" id="flow-api">--</div><div class="muted" id="flow-api-sub">service</div></div>
      <span class="flow-arrow">&rarr;</span>
      <div class="flow-node"><h3>Products</h3><div class="flow-main" id="flow-products">--</div><div class="muted" id="flow-products-sub">Lens + Admin</div></div>
    </div>
    <div class="grid">
      <div class="card"><div class="card-header">ETL jobs</div><div class="card-body table-wrap" id="etl-jobs"><div class="loading">Authenticate to view</div></div></div>
      <div class="card"><div class="card-header">Engine workers <span class="tag" id="worker-count-tag">0</span></div><div class="card-body table-wrap" id="engine-workers"><div class="loading">Authenticate to view</div></div></div>
      <div class="card"><div class="card-header">Engine status</div><div class="card-body table-wrap" id="engine-kv"><div class="loading">Authenticate to view</div></div></div>
      <div class="card"><div class="card-header">Recent events</div><div class="card-body table-wrap" id="audit-events"><div class="loading">Authenticate to view</div></div></div>
    </div>
  </section>

  <section class="panel" id="panel-tables">
    <div class="toolbar">
      <input type="search" id="table-filter" placeholder="Filter tables…" oninput="renderTables()">
    </div>
    <div class="card full">
      <div class="card-header">Table row counts <span class="tag" id="table-count-tag">0</span></div>
      <div class="card-body table-wrap" id="table-counts"><div class="loading">Authenticate to view</div></div>
    </div>
  </section>

  <section class="panel" id="panel-accounts">
    <div class="section-label">End-user accounts (iam.users)</div>
    <div class="card full write-only" style="margin-bottom:12px;">
      <div class="card-header">Add user</div>
      <div class="card-body">
        <div class="form-grid">
          <div class="field"><label>Email</label><input id="acct-email" type="text" placeholder="user@example.com"></div>
          <div class="field"><label>Display name</label><input id="acct-name" type="text" placeholder="Optional"></div>
          <div class="field"><label>Organization</label><input id="acct-org" type="text" placeholder="Optional"></div>
          <div class="field"><label>Plan</label>
            <select id="acct-plan"><option value="free">free</option><option value="starter">starter</option><option value="pro">pro</option><option value="enterprise">enterprise</option></select>
          </div>
        </div>
        <button class="btn btn-primary" onclick="createAccount()">Create account</button>
        <div id="acct-create-msg"></div>
      </div>
    </div>
    <div class="card full">
      <div class="card-header">Accounts <span class="tag" id="acct-count-tag">0</span></div>
      <div class="card-body">
        <p class="hint" style="margin-bottom:10px;">Block soft-deactivates the user (<code>is_active=false</code>) and revokes API keys. Requires <code>admin:write</code> + approval code. Unblock is out of band today.</p>
        <div class="table-wrap" id="accounts-table"><div class="loading">Authenticate to view</div></div>
        <div id="acct-block-msg"></div>
      </div>
    </div>
  </section>

  <section class="panel" id="panel-query">
    <div class="section-label">Named query console</div>
    <div class="card full">
      <div class="card-header">Curated read queries <span class="tag">read-only</span></div>
      <div class="card-body">
        <div class="query-controls">
          <select id="query-name">
            <option value="">Select query…</option>
            <option value="table_stats">table_stats</option>
            <option value="heartbeats">heartbeats</option>
            <option value="all_tickers">all_tickers</option>
            <option value="latest_prices">latest_prices</option>
            <option value="latest_signals">latest_signals</option>
            <option value="market_news">market_news</option>
            <option value="command_log">command_log</option>
            <option value="orders">orders</option>
            <option value="portfolio">portfolio</option>
          </select>
          <input id="query-limit" type="number" value="100" min="1" max="1000" style="width:90px;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:8px 10px;border-radius:var(--radius);">
          <button class="btn btn-primary" onclick="runQuery()">Run</button>
          <span id="query-status" class="muted"></span>
        </div>
        <div id="query-results"></div>
      </div>
    </div>
  </section>
</div>

<script>
const PRODUCT_CLIENTS = {
  'ai-advisor-production': { product: 'Lens', kind: 'primary' },
  'theeyebeta-prod-admin': { product: 'Admin Frontend', kind: 'primary' },
  'admin-terminal-production': { product: 'Admin Frontend', kind: 'related' },
  'admin-tool-production': { product: 'Admin Frontend', kind: 'related' },
  'admin-tool': { product: 'Admin Frontend', kind: 'related' },
};

const SESSION_KEY = 'dataapi_ops_session';
const CLIENT_ID_KEY = 'dataapi_ops_client_id';

let TOKEN = '';
let TOKEN_EXPIRES_AT = 0;
let CLIENT_ID = localStorage.getItem(CLIENT_ID_KEY) || 'admin-tool-production';
let CLIENT_SECRET = '';
let CAN_WRITE = false;
let autoRefreshTimer = null;
let tokenRenewTimer = null;
let cache = { dashboard: null, etl: null, engine: null, accounts: null, tables: [] };

document.getElementById('client-id-input').value = CLIENT_ID;
restoreSession();

function toggleAdvancedAuth() {
  document.getElementById('auth-advanced').classList.toggle('open');
}

function setAuthStatus(msg, color) {
  const el = document.getElementById('auth-status');
  el.textContent = msg;
  el.style.color = color === 'green' ? 'var(--accent)' : (color === 'red' ? 'var(--red)' : 'var(--text-muted)');
}

function setSignedInUi(signedIn) {
  document.getElementById('btn-signout').style.display = signedIn ? '' : 'none';
  document.getElementById('btn-signin').style.display = signedIn ? 'none' : '';
  document.getElementById('client-secret-input').disabled = signedIn;
  document.getElementById('client-id-input').disabled = signedIn;
}

function restoreSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return;
    const s = JSON.parse(raw);
    if (s.access_token && s.expires_at && Date.now() < s.expires_at - 5000) {
      TOKEN = s.access_token;
      TOKEN_EXPIRES_AT = s.expires_at;
      CLIENT_ID = s.client_id || CLIENT_ID;
      CLIENT_SECRET = s.client_secret || '';
      document.getElementById('client-id-input').value = CLIENT_ID;
      if (CLIENT_SECRET) document.getElementById('client-secret-input').value = CLIENT_SECRET;
      setSignedInUi(true);
      scheduleTokenRenewal();
    }
  } catch (_) {}
}

function persistSession() {
  if (!document.getElementById('remember-session').checked) {
    sessionStorage.removeItem(SESSION_KEY);
    return;
  }
  sessionStorage.setItem(SESSION_KEY, JSON.stringify({
    access_token: TOKEN,
    expires_at: TOKEN_EXPIRES_AT,
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
  }));
  localStorage.setItem(CLIENT_ID_KEY, CLIENT_ID);
}

function clearSession() {
  TOKEN = '';
  TOKEN_EXPIRES_AT = 0;
  CLIENT_SECRET = '';
  sessionStorage.removeItem(SESSION_KEY);
  if (tokenRenewTimer) { clearTimeout(tokenRenewTimer); tokenRenewTimer = null; }
  setSignedInUi(false);
  document.getElementById('live-dot').style.display = 'none';
  document.getElementById('client-secret-input').value = '';
}

function scheduleTokenRenewal() {
  if (tokenRenewTimer) { clearTimeout(tokenRenewTimer); tokenRenewTimer = null; }
  if (!CLIENT_SECRET || !TOKEN_EXPIRES_AT) return;
  const ms = Math.max(15000, TOKEN_EXPIRES_AT - Date.now() - 90000);
  tokenRenewTimer = setTimeout(() => { renewToken().catch(() => {}); }, ms);
}

async function renewToken() {
  if (!CLIENT_ID || !CLIENT_SECRET) return;
  await issueServiceToken(CLIENT_ID, CLIENT_SECRET, false);
  await refreshAll();
}

async function issueServiceToken(clientId, clientSecret, showStatus) {
  const basic = btoa(unescape(encodeURIComponent(clientId + ':' + clientSecret)));
  const resp = await fetch('/api/v1/auth/service-token', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + basic,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ requested_scopes: ['admin:read', 'admin:write'] }),
  });
  const body = await resp.text();
  let data = null;
  try { data = JSON.parse(body); } catch (_) {}
  if (!resp.ok) {
    const msg = data?.error?.message || data?.detail || body || ('HTTP ' + resp.status);
    throw new Error(msg);
  }
  TOKEN = data.access_token;
  const expiresIn = Number(data.expires_in || 3600);
  TOKEN_EXPIRES_AT = Date.now() + expiresIn * 1000;
  CLIENT_ID = clientId;
  CLIENT_SECRET = clientSecret;
  persistSession();
  setSignedInUi(true);
  scheduleTokenRenewal();
  if (showStatus !== false) {
    setAuthStatus('Signed in as ' + clientId + ' (token ~' + Math.round(expiresIn / 60) + 'm)', 'green');
  }
}

async function signIn() {
  const clientId = document.getElementById('client-id-input').value.trim();
  const clientSecret = document.getElementById('client-secret-input').value;
  if (!clientId || !clientSecret) {
    setAuthStatus('Client ID and secret required', 'red');
    return;
  }
  setAuthStatus('Signing in…', '');
  try {
    await issueServiceToken(clientId, clientSecret, true);
    await refreshAll();
  } catch (e) {
    setAuthStatus('Sign in failed: ' + e.message, 'red');
    clearSession();
  }
}

function signOut() {
  clearSession();
  setAuthStatus('Signed out', '');
}

function authenticateWithToken() {
  TOKEN = document.getElementById('token-input').value.trim();
  if (!TOKEN) { setAuthStatus('Token required', 'red'); return; }
  CLIENT_SECRET = '';
  TOKEN_EXPIRES_AT = Date.now() + 55 * 60 * 1000;
  persistSession();
  setSignedInUi(true);
  refreshAll();
}

function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + name));
  if (name === 'accounts' && TOKEN) loadAccounts();
  if (name === 'telemetry' && TOKEN) loadTelemetryExtras();
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str == null ? '' : String(str);
  return d.innerHTML;
}

async function apiFetch(path, opts = {}) {
  const headers = Object.assign({ 'Authorization': 'Bearer ' + TOKEN }, opts.headers || {});
  if (opts.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const resp = await fetch(path, Object.assign({}, opts, { headers }));
  const body = await resp.text();
  if (!resp.ok) {
    let message = body, code = '';
    try {
      const parsed = JSON.parse(body);
      message = parsed.error?.message || parsed.detail || body;
      code = parsed.error?.code || '';
    } catch (_) {}
    const err = new Error(resp.status + ': ' + message);
    err.status = resp.status;
    err.code = code;
    throw err;
  }
  if (!body) return null;
  try { return JSON.parse(body); } catch (_) { return body; }
}

function toggleAutoRefresh() {
  if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
  if (document.getElementById('auto-refresh-toggle').checked) {
    autoRefreshTimer = setInterval(refreshAll, 30000);
  }
}

async function refreshAll() {
  if (!TOKEN) return;
  await loadDashboard();
  const tab = document.querySelector('.tab.active')?.dataset.tab;
  if (tab === 'telemetry') await loadTelemetryExtras();
  if (tab === 'accounts') await loadAccounts();
}

async function loadDashboard() {
  try {
    const data = await apiFetch('/api/v1/admin/dashboard-data');
    cache.dashboard = data;
    cache.tables = data.tables || [];
    setAuthStatus('Signed in · ' + (CLIENT_ID || 'token') + ' (admin:read+)', 'green');
    document.getElementById('live-dot').style.display = 'inline-block';
    setSignedInUi(true);
    document.getElementById('timestamp').textContent = new Date(data.timestamp).toLocaleString();
    renderOverview(data);
    renderConnections(data.service_clients || []);
    renderTables();
    renderAudit(data.recent_events || []);
    renderWorkers(data.engine_workers || []);
    updateFlowFromDashboard(data);
    probeWriteAccess();
    if (document.getElementById('auto-refresh-toggle').checked && !autoRefreshTimer) {
      autoRefreshTimer = setInterval(refreshAll, 30000);
    }
  } catch (e) {
    setAuthStatus('Auth failed: ' + e.message, 'red');
    document.getElementById('live-dot').style.display = 'none';
  }
}

async function probeWriteAccess() {
  // Soft probe: list is read; create with empty would 422 — instead try listing accounts
  // and enable write UI optimistically if token previously used write successfully.
  // We detect write by attempting a no-op-safe path: GET accounts works with read;
  // show write forms always after connect, but API will 403 if missing admin:write.
  document.getElementById('app').classList.add('can-write');
  CAN_WRITE = true;
}

function clientBadge(clientId) {
  const meta = PRODUCT_CLIENTS[clientId];
  if (!meta) return '<span class="badge badge-muted">other</span>';
  if (meta.kind === 'primary') return '<span class="badge badge-primary">' + escapeHtml(meta.product) + '</span>';
  return '<span class="badge badge-yellow">' + escapeHtml(meta.product) + '</span>';
}

function renderOverview(data) {
  const apiOk = data.api?.status === 'running';
  document.getElementById('stat-api').textContent = apiOk ? 'Online' : 'Down';
  document.getElementById('stat-api').style.color = apiOk ? 'var(--accent)' : 'var(--red)';
  document.getElementById('stat-api-sub').textContent = (data.api?.version || '') + ' · ' + (data.api?.environment || '');

  const dbOk = !!data.database?.connected;
  document.getElementById('stat-db').textContent = dbOk ? 'Connected' : 'Down';
  document.getElementById('stat-db').style.color = dbOk ? 'var(--accent)' : 'var(--red)';
  document.getElementById('stat-db-sub').textContent = dbOk ? String(data.database.version || '').split(' ').slice(0, 2).join(' ') : 'Unreachable';

  document.getElementById('stat-tickers').textContent = Number(data.active_tickers || 0).toLocaleString();
  document.getElementById('stat-tickers').style.color = 'var(--text)';
  document.getElementById('stat-tickers-sub').textContent = 'monitored';

  const workers = data.engine_workers || [];
  const healthy = workers.filter(w => w.status === 'running' && (w.seconds_ago == null || w.seconds_ago <= 120)).length;
  document.getElementById('stat-workers').textContent = healthy + '/' + workers.length;
  document.getElementById('stat-workers').style.color = healthy === workers.length && workers.length ? 'var(--accent)' : (healthy ? 'var(--yellow)' : 'var(--red)');
  document.getElementById('stat-workers-sub').textContent = workers.length ? (healthy === workers.length ? 'all healthy' : (workers.length - healthy) + ' degraded') : 'none';

  document.getElementById('api-status').innerHTML =
    '<div class="kv"><span class="label">Status</span><span class="value">' + escapeHtml(data.api.status) + '</span></div>' +
    '<div class="kv"><span class="label">Name</span><span class="value">' + escapeHtml(data.api.name) + '</span></div>' +
    '<div class="kv"><span class="label">Version</span><span class="value">' + escapeHtml(data.api.version) + '</span></div>' +
    '<div class="kv"><span class="label">Environment</span><span class="value">' + escapeHtml(data.api.environment) + '</span></div>' +
    '<div class="kv"><span class="label">Bind</span><span class="value">' + escapeHtml(data.api.host) + ':' + data.api.port + '</span></div>';

  document.getElementById('db-status').innerHTML =
    '<div class="kv"><span class="label">Connection</span><span class="value">' + (dbOk ? 'Connected' : 'Disconnected') + '</span></div>' +
    '<div class="kv"><span class="label">Version</span><span class="value" style="font-size:12px">' + escapeHtml(data.database.version) + '</span></div>' +
    '<div class="kv"><span class="label">URL</span><span class="value mono" style="font-size:11px;word-break:break-all">' + escapeHtml(data.database.url_masked) + '</span></div>';

  const clients = data.service_clients || [];
  const gates = [
    { id: 'ai-advisor-production', label: 'Lens / AI Financial Advisor' },
    { id: 'theeyebeta-prod-admin', label: 'TheEyeBetaAdmin Frontend (data bridge)' },
  ];
  let html = '';
  for (const g of gates) {
    const c = clients.find(x => x.client_id === g.id);
    const ok = c && c.is_active;
    html += '<div class="card"><div class="card-header">' + escapeHtml(g.label) + '</div><div class="card-body">';
    html += '<div class="kv"><span class="label">Client</span><span class="value mono">' + escapeHtml(g.id) + '</span></div>';
    html += '<div class="kv"><span class="label">Status</span><span class="value"><span class="status-dot ' + (ok ? 'green' : 'red') + '"></span>' + (ok ? 'active in IAM' : (c ? 'inactive' : 'missing')) + '</span></div>';
    if (c) html += '<div class="kv"><span class="label">Scopes</span><span class="value">' + c.scope_count + '</span></div>';
    html += '</div></div>';
  }
  document.getElementById('product-gates').innerHTML = html;
}

function renderConnections(clients) {
  document.getElementById('client-count-tag').textContent = String(clients.length);
  if (!clients.length) {
    document.getElementById('service-clients').innerHTML = '<div class="loading">No service clients</div>';
    return;
  }
  const sorted = clients.slice().sort((a, b) => {
    const ap = PRODUCT_CLIENTS[a.client_id] ? 0 : 1;
    const bp = PRODUCT_CLIENTS[b.client_id] ? 0 : 1;
    if (ap !== bp) return ap - bp;
    return a.client_id.localeCompare(b.client_id);
  });
  let html = '<table><thead><tr><th>Product</th><th>Client ID</th><th>Name</th><th>Active</th><th>Scopes</th></tr></thead><tbody>';
  for (const c of sorted) {
    html += '<tr>';
    html += '<td>' + clientBadge(c.client_id) + '</td>';
    html += '<td class="mono">' + escapeHtml(c.client_id) + '</td>';
    html += '<td>' + escapeHtml(c.display_name || '—') + '</td>';
    html += '<td>' + (c.is_active ? '<span class="badge badge-green">active</span>' : '<span class="badge badge-red">inactive</span>') + '</td>';
    html += '<td>' + c.scope_count + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  document.getElementById('service-clients').innerHTML = html;
}

function renderTables() {
  const filter = (document.getElementById('table-filter')?.value || '').toLowerCase();
  let tables = cache.tables || [];
  if (filter) tables = tables.filter(t => String(t.table).toLowerCase().includes(filter));
  document.getElementById('table-count-tag').textContent = String(tables.length);
  if (!tables.length) {
    document.getElementById('table-counts').innerHTML = '<div class="loading">No tables</div>';
    return;
  }
  const sorted = tables.slice().sort((a, b) => (b.row_count || 0) - (a.row_count || 0));
  let html = '<table><thead><tr><th>Table</th><th style="text-align:right">Rows</th></tr></thead><tbody>';
  for (const t of sorted) {
    const val = t.row_count < 0 ? '<span style="color:var(--red)">N/A</span>' : Number(t.row_count).toLocaleString();
    html += '<tr><td class="mono">' + escapeHtml(t.table) + '</td><td style="text-align:right;font-variant-numeric:tabular-nums">' + val + '</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('table-counts').innerHTML = html;
}

function renderWorkers(workers) {
  document.getElementById('worker-count-tag').textContent = String(workers.length);
  if (!workers.length) {
    document.getElementById('engine-workers').innerHTML = '<div class="loading">No heartbeat data</div>';
    return;
  }
  let html = '<table><thead><tr><th>Worker</th><th>Status</th><th>Last beat</th><th>Ago</th></tr></thead><tbody>';
  for (const w of workers) {
    const stale = w.seconds_ago != null && w.seconds_ago > 120;
    const color = stale ? 'red' : (w.status === 'running' ? 'green' : 'yellow');
    const ago = w.seconds_ago == null ? '—' : (w.seconds_ago < 60 ? w.seconds_ago + 's' : Math.round(w.seconds_ago / 60) + 'm');
    html += '<tr><td>' + escapeHtml(w.worker_name) + '</td><td><span class="badge badge-' + color + '">' + escapeHtml(w.status) + '</span></td><td class="mono" style="font-size:11px">' + escapeHtml(w.last_heartbeat || '—') + '</td><td>' + ago + '</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('engine-workers').innerHTML = html;
}

function renderAudit(events) {
  if (!events.length) {
    document.getElementById('audit-events').innerHTML = '<div class="loading">No recent events</div>';
    return;
  }
  let html = '<table><thead><tr><th>Type</th><th>Category</th><th>Severity</th><th>Time</th></tr></thead><tbody>';
  for (const e of events) {
    const sev = e.severity || 'info';
    const sevColor = sev === 'error' ? 'red' : (sev === 'warning' ? 'yellow' : 'green');
    html += '<tr><td>' + escapeHtml(e.event_type || '—') + '</td><td>' + escapeHtml(e.event_category || '—') + '</td><td><span class="badge badge-' + sevColor + '">' + escapeHtml(sev) + '</span></td><td class="mono" style="font-size:11px">' + escapeHtml(e.created_at || '—') + '</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('audit-events').innerHTML = html;
}

function updateFlowFromDashboard(data) {
  const tables = data.tables || [];
  const totalRows = tables.reduce((s, t) => s + (t.row_count > 0 ? t.row_count : 0), 0);
  document.getElementById('flow-tables').textContent = tables.length + ' tables';
  document.getElementById('flow-tables-sub').textContent = totalRows.toLocaleString() + ' rows (approx)';
  document.getElementById('flow-api').innerHTML = '<span class="status-dot ' + (data.api?.status === 'running' ? 'green' : 'red') + '"></span>' + (data.api?.status || '—');
  document.getElementById('flow-api-sub').textContent = data.api?.environment || '';
  const clients = data.service_clients || [];
  const lens = clients.find(c => c.client_id === 'ai-advisor-production' && c.is_active);
  const admin = clients.find(c => c.client_id === 'theeyebeta-prod-admin' && c.is_active);
  const ok = (lens ? 1 : 0) + (admin ? 1 : 0);
  document.getElementById('flow-products').textContent = ok + '/2 gates';
  document.getElementById('flow-products-sub').textContent = (lens ? 'Lens ' : '') + (admin ? 'Admin' : '') || 'missing';
}

async function loadTelemetryExtras() {
  if (!TOKEN) return;
  try {
    const [etl, engine] = await Promise.all([
      apiFetch('/api/v1/admin/etl-jobs'),
      apiFetch('/api/v1/admin/engine-status'),
    ]);
    cache.etl = etl;
    cache.engine = engine;
    renderEtl(etl?.jobs || []);
    renderEngineKv(engine?.entries || []);
    const jobs = etl?.jobs || [];
    const okJobs = jobs.filter(j => !j.last_error && (j.status || '').toLowerCase() !== 'error').length;
    document.getElementById('flow-etl').textContent = okJobs + '/' + jobs.length + ' ok';
    document.getElementById('flow-etl-sub').textContent = jobs.length ? 'ETL registered' : 'no ETL rows';
  } catch (e) {
    document.getElementById('etl-jobs').innerHTML = '<div class="error-msg">' + escapeHtml(e.message) + '</div>';
  }
}

function renderEtl(jobs) {
  if (!jobs.length) {
    document.getElementById('etl-jobs').innerHTML = '<div class="loading">No ETL jobs</div>';
    return;
  }
  let html = '<table><thead><tr><th>Job</th><th>Status</th><th>Last run</th><th>Last OK date</th><th>Error</th></tr></thead><tbody>';
  for (const j of jobs) {
    const bad = !!j.last_error || (j.status || '').toLowerCase() === 'error';
    html += '<tr><td class="mono">' + escapeHtml(j.job_name) + '</td><td><span class="badge badge-' + (bad ? 'red' : 'green') + '">' + escapeHtml(j.status || '—') + '</span></td><td class="mono" style="font-size:11px">' + escapeHtml(j.last_run_at || '—') + '</td><td>' + escapeHtml(j.last_successful_date || '—') + '</td><td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--red)">' + escapeHtml(j.last_error || '') + '</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('etl-jobs').innerHTML = html;
}

function renderEngineKv(entries) {
  if (!entries.length) {
    document.getElementById('engine-kv').innerHTML = '<div class="loading">No engine status</div>';
    return;
  }
  let html = '<table><thead><tr><th>Key</th><th>Value</th><th>Updated</th></tr></thead><tbody>';
  for (const e of entries) {
    html += '<tr><td class="mono">' + escapeHtml(e.key) + '</td><td>' + escapeHtml(e.value) + '</td><td class="mono" style="font-size:11px">' + escapeHtml(e.updated_at || '—') + '</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('engine-kv').innerHTML = html;
}

async function loadAccounts() {
  if (!TOKEN) return;
  try {
    const data = await apiFetch('/api/v1/admin/accounts?include_inactive=true&limit=200');
    cache.accounts = data;
    renderAccounts(data.accounts || []);
  } catch (e) {
    document.getElementById('accounts-table').innerHTML = '<div class="error-msg">' + escapeHtml(e.message) + '</div>';
  }
}

function renderAccounts(accounts) {
  document.getElementById('acct-count-tag').textContent = String(accounts.length);
  if (!accounts.length) {
    document.getElementById('accounts-table').innerHTML = '<div class="loading">No accounts</div>';
    return;
  }
  let html = '<table><thead><tr><th>Email</th><th>Name</th><th>Org</th><th>Plan</th><th>Active</th><th>Created</th><th></th></tr></thead><tbody>';
  for (const a of accounts) {
    html += '<tr>';
    html += '<td>' + escapeHtml(a.email) + '</td>';
    html += '<td>' + escapeHtml(a.display_name || '—') + '</td>';
    html += '<td>' + escapeHtml(a.organization || '—') + '</td>';
    html += '<td>' + escapeHtml(a.plan || '—') + '</td>';
    html += '<td>' + (a.is_active ? '<span class="badge badge-green">active</span>' : '<span class="badge badge-red">blocked</span>') + '</td>';
    html += '<td class="mono" style="font-size:11px">' + escapeHtml(a.created_at || '—') + '</td>';
    html += '<td>';
    if (a.is_active) {
      html += '<div class="block-row write-only">';
      html += '<input type="password" id="approval-' + escapeHtml(a.user_uuid) + '" placeholder="Approval code" autocomplete="off">';
      html += '<button class="btn btn-danger" onclick="blockAccount(\'' + escapeHtml(a.user_uuid) + '\')">Block</button>';
      html += '</div>';
    } else {
      html += '<span class="muted">—</span>';
    }
    html += '</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('accounts-table').innerHTML = html;
}

async function createAccount() {
  const msg = document.getElementById('acct-create-msg');
  msg.innerHTML = '';
  try {
    const body = {
      email: document.getElementById('acct-email').value.trim(),
      display_name: document.getElementById('acct-name').value.trim() || null,
      organization: document.getElementById('acct-org').value.trim() || null,
      plan: document.getElementById('acct-plan').value,
    };
    const created = await apiFetch('/api/v1/admin/accounts', { method: 'POST', body: JSON.stringify(body) });
    msg.innerHTML = '<div class="ok-msg">Created ' + escapeHtml(created.email) + ' (' + escapeHtml(created.user_uuid) + ')</div>';
    document.getElementById('acct-email').value = '';
    document.getElementById('acct-name').value = '';
    document.getElementById('acct-org').value = '';
    await loadAccounts();
  } catch (e) {
    msg.innerHTML = '<div class="error-msg">' + escapeHtml(e.message) + '</div>';
  }
}

async function blockAccount(userUuid) {
  const msg = document.getElementById('acct-block-msg');
  msg.innerHTML = '';
  const codeEl = document.getElementById('approval-' + userUuid);
  const approval = codeEl ? codeEl.value : '';
  if (!approval) {
    msg.innerHTML = '<div class="error-msg">Approval code required to block</div>';
    return;
  }
  if (!confirm('Block this account? Soft-delete only — keys will be revoked.')) return;
  try {
    await apiFetch('/api/v1/admin/accounts/' + encodeURIComponent(userUuid), {
      method: 'DELETE',
      body: JSON.stringify({ approval_code: approval, reason: 'blocked via ops dashboard' }),
    });
    msg.innerHTML = '<div class="ok-msg">Account blocked (soft-deactivated)</div>';
    await loadAccounts();
  } catch (e) {
    msg.innerHTML = '<div class="error-msg">' + escapeHtml(e.message) + '</div>';
  }
}

async function runQuery() {
  if (!TOKEN) { setAuthStatus('Authenticate first', 'red'); return; }
  const queryName = document.getElementById('query-name').value;
  if (!queryName) return;
  const limit = document.getElementById('query-limit').value;
  const statusEl = document.getElementById('query-status');
  statusEl.textContent = 'Running…';
  try {
    const t0 = performance.now();
    const data = await apiFetch('/api/v1/admin/named-query?query_name=' + encodeURIComponent(queryName) + '&limit=' + limit);
    statusEl.textContent = data.row_count + ' rows in ' + Math.round(performance.now() - t0) + 'ms';
    renderQueryResults(data.rows || []);
  } catch (e) {
    statusEl.textContent = '';
    document.getElementById('query-results').innerHTML = '<div class="error-msg">' + escapeHtml(e.message) + '</div>';
  }
}

function renderQueryResults(rows) {
  const wrap = document.getElementById('query-results');
  if (!rows.length) { wrap.innerHTML = '<div class="loading">No results</div>'; return; }
  const cols = Object.keys(rows[0]);
  let html = '<div class="result-table-wrap"><table><thead><tr>';
  for (const c of cols) html += '<th>' + escapeHtml(c) + '</th>';
  html += '</tr></thead><tbody>';
  for (const row of rows) {
    html += '<tr>';
    for (const c of cols) {
      const raw = row[c];
      html += '<td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (raw == null ? '<span class="muted">null</span>' : escapeHtml(String(raw))) + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  wrap.innerHTML = html;
}

document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    if (document.querySelector('.tab.active')?.dataset.tab === 'query') { e.preventDefault(); runQuery(); }
  }
});

if (TOKEN) refreshAll();
</script>
</body>
</html>
"""
