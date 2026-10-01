# TheEyeBeta2025 — Cloudflare Tunnel Runbook

This documents how public traffic reaches the **native** (no Docker) services on this server.

## Architecture

```
Internet
   │
   ▼
Cloudflare Edge (TLS)
   │
   ▼
cloudflared tunnel "my-api"  (systemd: cloudflared.service) — SHARED
   │
   ├── dataapiprod.theeyebeta.store → 127.0.0.1:7000  TheEyeBetaDataAPI (canonical)
   ├── dataapi.theeyebeta.store     → 127.0.0.1:7000  TheEyeBetaDataAPI (legacy alias)
   ├── admin.theeyebeta.store       → 127.0.0.1:8080  TheEyeBetaAdminFrontend static terminal host (target; DEBT-01)
   └── api.theeyebeta.store         → 127.0.0.1:8000  TheEyeBetaLocal main API
```

The single routing table, with owners and verification status, is
[`OWNERSHIP.md`](OWNERSHIP.md) section 2; `tests/test_tunnel_routing.py` keeps it,
`README.md` and [`deploy/cloudflared-config.yml`](../deploy/cloudflared-config.yml)
in agreement.

- The terminal (browser and Tauri) sends every API call to
  `dataapiprod.theeyebeta.store`; `/admin/*` there goes through DataAPI's
  allowlisted gateway to admin-service on loopback `:7200`.
- `admin.theeyebeta.store → :8080` (AdminFrontend `server.mjs`, page only) is
  the decided target (DEBT-01, 2026-10-01). admin-service on `:7200` is never a
  tunnel origin: routing a hostname to it would bypass the DataAPI gateway.
- The tree above is the **target**, not a statement of what is live. TheEyeBetaProd
  still declares `admin → :7200` (C7), and `:8080` has no proven production
  unit yet. **Do not apply the config until
  `curl -sf http://127.0.0.1:8080/healthz` returns `{"ok":true,...}` on the host.**

**Do not use Docker** for these app ports. Old containers (`theeyebeta-dataapi`, `theeyebeta-api-dev`, nginx on `:80`) are obsolete and will break the tunnel if left running.

## Change policy (shared tunnel)

The tunnel carries hostnames owned by three repositories. Pushing ingress
replaces the routing for **all** of them, so:

- `scripts/start_all_native.sh` and `scripts/watchdog_all.sh` never change
  tunnel configuration. When `https://dataapiprod.theeyebeta.store/health`
  fails, the watchdog writes an `ALERT` line to `.runtime-logs/watchdog.log`
  and nothing else.
- `scripts/fix_tunnel.sh` and `scripts/sync_tunnel.sh` print the ingress they
  would apply and exit 2 unless `TUNNEL_CHANGE_APPROVED=yes` is set. With
  approval they still exit 3, changing nothing, while
  `http://127.0.0.1:8080/healthz` (`ADMIN_TERMINAL_HEALTH_URL`) is not healthy.
- Before approving: confirm the live routing (Cloudflare dashboard or
  `cloudflared tunnel info my-api`), get agreement from the owner of every
  hostname whose origin would change (Prod must update its C7 declaration for
  the admin hostname), and confirm the `:8080` terminal host runs under a
  production unit.

Source of truth for DataAPI's hostnames: [`deploy/cloudflared-config.yml`](../deploy/cloudflared-config.yml).
Installed copy (requires sudo): `/etc/cloudflared/config.yml`.

## Start services (native)

From `TheEyeBetaDataAPI`:

```bash
bash scripts/start_all_native.sh   # Data API :7000 + watchdog (no tunnel changes)
THEEYE_LOCAL_REPO=/path/to/TheEyeBetaLocal bash scripts/start_all_native.sh  # also Local :8000/:8090
```

The production DataAPI process is the user unit `theeyebeta-dataapi`
(`systemctl --user restart theeyebeta-dataapi`); see `PRODUCTION_RUNBOOK.md`.

## Applying a tunnel change (approved operator action)

Preview first (no changes, exits 2):

```bash
bash scripts/sync_tunnel.sh
```

Install `/etc/cloudflared/config.yml`, restart `cloudflared.service`, link DNS
and push remote ingress:

```bash
sudo TUNNEL_CHANGE_APPROVED=yes bash scripts/fix_tunnel.sh
```

Without sudo (DNS + remote ingress only; starts a temporary `cloudflared-native`
tmux connector if `/etc/cloudflared/config.yml` is stale):

```bash
TUNNEL_CHANGE_APPROVED=yes bash scripts/sync_tunnel.sh
```

## Verify

**Local:**

```bash
curl -s http://127.0.0.1:7000/health   # Data API
curl -s http://127.0.0.1:8000/health   # Main API
curl -s http://127.0.0.1:8090/health   # Trask
```

**Through tunnel:**

```bash
curl -s https://dataapiprod.theeyebeta.store/health
curl -s https://api.theeyebeta.store/health
```

**Authenticated data (Data API via tunnel)** — prefer a real product client:

```bash
API_BASE_URL="https://dataapiprod.theeyebeta.store" \
SERVICE_CLIENT_ID="ai-advisor-production" \
SERVICE_CLIENT_SECRET="<secret>" \
bash scripts/verify_remote_access.sh
```

Admin Frontend gateway (unauthenticated — expect 401 when up):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://dataapiprod.theeyebeta.store/admin/auth/me
```

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
All fixes below change the shared tunnel: follow "Change policy" first.

| Symptom | Cause | Fix (approved) |
|---|---|---|
| Error **1033** / HTTP **530** | DNS not linked to tunnel, or no healthy `cloudflared` connector | `TUNNEL_CHANGE_APPROVED=yes bash scripts/sync_tunnel.sh` |
| HTTP **502** on `dataapi.*` only | Stale ingress routes `dataapi` → `:80` (dead Docker nginx) | `sudo TUNNEL_CHANGE_APPROVED=yes bash scripts/fix_tunnel.sh` |
| Local `:7000` OK, tunnel fails | Two connectors: systemd (bad config) + fallback fighting | `sudo TUNNEL_CHANGE_APPROVED=yes bash scripts/fix_tunnel.sh` |
| Intermittent 502/200 | Same as above — traffic hits wrong connector | `sudo TUNNEL_CHANGE_APPROVED=yes bash scripts/fix_tunnel.sh` |

## tmux sessions

| Session | Purpose |
|---|---|
| `theeyebeta-dataapi` | Data API gunicorn on `:7000` |
| `theeyebeta-watchdog` | Restarts services; logs tunnel ALERTs only |
| `cloudflared-native` | Temporary connector started by an approved `sync_tunnel.sh` (removed by `fix_tunnel.sh`) |

```bash
tmux list-sessions
tmux attach -t theeyebeta-dataapi
```

## Logs

| Log | Path |
|---|---|
| Data API | `.runtime-logs/dataapi.log` |
| Tunnel sync | `.runtime-logs/sync-tunnel.log` |
| Watchdog | `.runtime-logs/watchdog.log` |
| cloudflared (systemd) | `sudo journalctl -u cloudflared -f` |

## .env requirements (Data API)

When exposed via tunnel, `.env` must include:

```env
API_HOST=127.0.0.1
API_PORT=7000
TRUST_PROXY_HEADERS=true
TRUSTED_HOSTS=dataapiprod.theeyebeta.store,dataapi.theeyebeta.store,127.0.0.1,localhost
```

Bootstrap with proxy support:

```bash
python scripts/bootstrap_local_env.py \
  --environment production \
  --database-url "postgresql+psycopg://api_service:..." \
  --trust-proxy-headers
```

## Related scripts

| Script | When to use |
|---|---|
| `scripts/start_all_native.sh` | Start native services (Local only with `THEEYE_LOCAL_REPO`) |
| `scripts/sync_tunnel.sh` | Preview; with approval: DNS + remote ingress (no sudo) |
| `scripts/fix_tunnel.sh` | Preview; with approval: install systemd tunnel config (sudo) |
| `scripts/watchdog_all.sh` | Restart services; alert-only for the tunnel |
| `scripts/verify_remote_access.sh` | Smoke test through public URL |
