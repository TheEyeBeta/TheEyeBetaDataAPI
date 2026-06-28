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
cloudflared tunnel "my-api"  (systemd: cloudflared.service)
   │
   ├── api.theeyebeta.store     → 127.0.0.1:8000  TheEyeBetaLocal Main API
   ├── dataapi.theeyebeta.store     → 127.0.0.1:7000  TheEyeBetaDataAPI
   ├── dataapiprod.theeyebeta.store → 127.0.0.1:7000  TheEyeBetaDataAPI (prod alias)
   └── admin.theeyebeta.store       → 127.0.0.1:7200  TheEyeBetaProd admin service
```

| Public URL | Local service | Repo |
|---|---|---|
| `https://dataapi.theeyebeta.store` | `127.0.0.1:7000` | TheEyeBetaDataAPI |
| `https://dataapiprod.theeyebeta.store` | `127.0.0.1:7000` | TheEyeBetaDataAPI (prod alias) |
| `https://api.theeyebeta.store` | `127.0.0.1:8000` | TheEyeBetaLocal |
| `https://admin.theeyebeta.store` | `127.0.0.1:7200` | TheEyeBetaProd |

**Do not use Docker** for these app ports. Old containers (`theeyebeta-dataapi`, `theeyebeta-api-dev`, nginx on `:80`) are obsolete and will break the tunnel if left running.

## Canonical config

Source of truth: [`deploy/cloudflared-config.yml`](../deploy/cloudflared-config.yml)

Installed copy (requires sudo): `/etc/cloudflared/config.yml`

## Start everything (native)

From `TheEyeBetaDataAPI`:

```bash
bash scripts/start_all_native.sh   # Data API :7000 + TheEyeBetaLocal :8000/:8090
bash scripts/sync_tunnel.sh        # DNS + remote ingress + tunnel verify
```

Or use the watchdog (keeps services + tunnel fallback alive):

```bash
tmux new-session -d -s theeyebeta-watchdog "bash scripts/watchdog_all.sh"
```

## One-time permanent tunnel fix

If `dataapi.theeyebeta.store` returns **502/530** but `curl http://127.0.0.1:7000/health` works, the system tunnel config is stale (often still pointing `dataapi` at Docker nginx on port **80**).

```bash
cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
sudo bash scripts/fix_tunnel.sh
```

This will:

1. Copy `deploy/cloudflared-config.yml` → `/etc/cloudflared/config.yml`
2. Link DNS hostnames to tunnel `my-api`
3. Push ingress rules to Cloudflare
4. Restart `cloudflared.service`
5. Remove the temporary `cloudflared-native` tmux fallback

## Non-sudo tunnel sync (fallback)

When you cannot run sudo yet:

```bash
bash scripts/sync_tunnel.sh
```

This syncs DNS + remote Cloudflare ingress and starts a **fallback** `cloudflared-native` tmux session with the correct config until `fix_tunnel.sh` is run.

## Verify

**Local:**

```bash
curl -s http://127.0.0.1:7000/health   # Data API
curl -s http://127.0.0.1:8000/health   # Main API
curl -s http://127.0.0.1:8090/health   # Trask
```

**Through tunnel:**

```bash
curl -s https://dataapi.theeyebeta.store/health
curl -s https://dataapiprod.theeyebeta.store/health
curl -s https://api.theeyebeta.store/health
```

**Authenticated data (Data API via tunnel):**

```bash
API_BASE_URL="https://dataapi.theeyebeta.store" \
SERVICE_CLIENT_ID="vi-app" \
SERVICE_CLIENT_SECRET="<secret>" \
bash scripts/verify_remote_access.sh
```

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| Error **1033** / HTTP **530** | DNS not linked to tunnel, or no healthy `cloudflared` connector | `bash scripts/sync_tunnel.sh` |
| HTTP **502** on `dataapi.*` only | Stale ingress routes `dataapi` → `:80` (dead Docker nginx) | `sudo bash scripts/fix_tunnel.sh` |
| Local `:7000` OK, tunnel fails | Two connectors: systemd (bad config) + fallback (good config) fighting | `sudo bash scripts/fix_tunnel.sh` |
| Intermittent 502/200 | Same as above — traffic hits wrong connector | `sudo bash scripts/fix_tunnel.sh` |

## tmux sessions

| Session | Purpose |
|---|---|
| `theeyebeta-dataapi` | Data API gunicorn on `:7000` |
| `theeyebeta-watchdog` | Restarts services + tunnel fallback |
| `cloudflared-native` | Temporary tunnel connector (remove after `fix_tunnel.sh`) |

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
TRUSTED_HOSTS=api.theeyebeta.store,dataapi.theeyebeta.store,127.0.0.1,localhost
```

Bootstrap with proxy support:

```bash
python scripts/bootstrap_local_env.py \
  --database-url "postgresql+psycopg://..." \
  --trust-proxy-headers
```

## Related scripts

| Script | When to use |
|---|---|
| `scripts/start_all_native.sh` | Start all native services |
| `scripts/sync_tunnel.sh` | Sync DNS + remote ingress (no sudo) |
| `scripts/fix_tunnel.sh` | Permanent systemd tunnel fix (sudo) |
| `scripts/watchdog_all.sh` | Keep services + tunnel alive |
| `scripts/verify_remote_access.sh` | Smoke test through public URL |
