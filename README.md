# TheEyeBetaDataAPI

Secure multi-client data access layer between private PostgreSQL and external/internal consumers.
Runtime data is served from the canonical `theeyebeta` schema only; the legacy `public`
schema is deprecated for this API. This service is read-only. Editing/order/job systems
live outside this repo.

**Production consumers that must keep working:**

1. **Lens / AI Financial Advisor** — backend service client `ai-advisor-production` → `/api/v1/*`
2. **TheEyeBetaAdmin Frontend** (hosted + Tauri) — browser → `/admin/*` gateway → Prod admin-service; admin-service uses `theeyebeta-prod-admin` for DataAPI `/api/v1/*` data

See [`docs/IAM_CONSUMER_INVENTORY.md`](docs/IAM_CONSUMER_INVENTORY.md). The `vi-app` name in examples is a **template / legacy IAM row**, not an active product.

**Ops viewer:** open `GET /api/v1/admin/dashboard` and **Sign in** with an admin service
client ID + secret (e.g. `admin-tool-production`). The page calls
`POST /api/v1/auth/service-token` and renews the JWT while the tab stays open.
Mint the client secret once on the Mac (`iam.issue_service_api_key`) and keep it in a
password manager — do not SSH-mint a token every visit. See
[`docs/OPS_DASHBOARD_LOGIN.md`](docs/OPS_DASHBOARD_LOGIN.md).

## Architecture model

- Private DB is reachable only by this API service.
- API contracts are domain-oriented and versioned under `/api/v1`.
- Layering is enforced:
  - routes/controllers
  - auth dependencies (principal + scopes)
  - services/use-cases
  - repositories (SQL only)
  - domain models/errors
- Structured API errors are returned for auth, validation, and DB failures.

## Auth model

- User auth:
  - bearer JWT
  - either symmetric secret validation (`USER_JWT_SECRET`) or OIDC/JWKS (`USER_JWT_JWKS_URL`)
- Service auth:
  - client credentials -> scoped bearer token via `POST /api/v1/auth/service-token`
  - credentials are validated from PostgreSQL `iam` tables when `SERVICE_CLIENT_AUTH_MODE=database`
  - optional fallback modes: `environment` or `hybrid`
  - optional direct mTLS principal flow (no bearer) via trusted proxy headers:
    - `X-Service-Client-Id`
    - `X-Client-Cert-Subject`
- JWT decode hardening (Phase 1):
  - every `jwt.decode` uses an explicit algorithm allowlist (current signing alg only)
  - `exp` and `iat` are always required
  - `iss`/`aud` enforcement is gated by `JWT_REQUIRE_ISS_AUD` (default `false` grace period; see `docs/IAM_CONSUMER_INVENTORY.md`)
- Refresh tokens (Phase 3, opt-in per client):
  - set `iam.service_clients.short_lived_tokens_enabled = true` (after applying `deploy/iam_refresh_tokens.sql`)
  - opted-in clients get shorter access TTL (`SHORT_LIVED_ACCESS_TOKEN_MINUTES`) plus `refresh_token` on `/service-token`
  - `POST /api/v1/auth/refresh` rotates refresh tokens (reuse of an old refresh token is rejected)
  - all other clients keep the existing long-lived `/service-token` response shape
- Scope examples:
  - `market:read`
  - `analytics:read`
  - `admin:read`
  - `admin:write` (separate from `admin:read` — create/deactivate end-user accounts)
  - `admin:*`
- OpenAPI UI (`/docs`, `/redoc`, `/openapi.json`) is disabled when `ENVIRONMENT=production`.

## API Reference

See **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** for the full endpoint reference including parameters, request/response schemas, required scopes, and curl examples.

### Capability route groups (summary)

| Group | Scope | Endpoints |
|---|---|---|
| Health | — | `GET /health` |
| Auth | — | `POST /api/v1/auth/service-token`, `POST /api/v1/auth/refresh` (opt-in), `POST /api/v1/auth/delegated-token` |
| Market Data | `market:read` | `GET /api/v1/market-data/quotes` |
| Symbols | `symbols:read` | `GET /api/v1/symbols/search`, `GET /api/v1/symbols/resolve` |
| Tickers | `market:read` / `analytics:read` | `GET /api/v1/tickers/{ticker}`, price-history, corporate-actions, fundamentals |
| Financials | `analytics:read` | `GET /api/v1/financials/{ticker}/income\|balance\|cashflow\|quality` |
| Indicators | `analytics:read` | `GET /api/v1/indicators/{ticker}/technical\|risk\|valuation\|returns` |
| Analytics | `analytics:read` | `GET /api/v1/analytics/snapshots/{ticker}` |
| Signals | `signals:read` | `GET /api/v1/signals/latest` |
| News | `market:read` | `GET /api/v1/news/market`, `/news/ticker/{ticker}` |
| Reference | `market:read` | `GET /api/v1/reference/countries\|currencies\|exchanges\|sectors\|industries\|calendar` |
| Advisor | `advisor:read` | `GET /api/v1/advisor/context`, `POST /api/v1/advisor/chat` |
| Portfolio | `portfolio:read` | `GET /api/v1/portfolio/state` (ownership-aware) |
| Generic Data | read scope / `admin:read` | `GET /api/v1/data/tables`, columns, rows |
| Admin | `admin:read` | `GET /api/v1/admin/dashboard` (ops HTML), `dashboard-data`, `accounts`, `audit-events`, `named-query`, `etl-jobs`, `engine-status`, `worker-heartbeats`, `price-ticks/{ticker}` |
| Admin accounts | `admin:read` / `admin:write` | `GET /api/v1/admin/accounts` (list); `POST` create; `DELETE /api/v1/admin/accounts/{user_uuid}` soft-block (approval-code gated, 1 req/min) |

## Production setup (Linux server — one time)

The app runs natively on the machine — no Docker required.

**1. Generate your `.env`:**

```bash
cd /path/to/TheEyeBetaDataAPI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap_local_env.py \
  --database-url "postgresql+psycopg://postgres:REPLACE_ME@localhost:5432/TheEyeBeta2025Live"
```

If running behind Cloudflare Tunnel, add `--trust-proxy-headers`.

`.env` holds every runtime secret (`JWT_SECRET`, `DATABASE_URL`, `SERVICE_CLIENTS_JSON`,
`ADMIN_ACCOUNT_APPROVAL_CODE`, ...) in one file. `bootstrap_local_env.py` and
`rotate_secrets.py` both write it (and any `.env.bak.*` backup) with mode `600`
(owner read/write only) automatically. If you ever hand-edit or copy `.env` by
some other means, re-run `chmod 600 .env` — a `--user` systemd unit like
`theeyebeta-dataapi` always runs as you, so 600 never breaks it. `.env.bak.*`
is git-ignored; never `git add -f` one.

**2. Install as a background service (starts on boot, restarts on crash):**

```bash
sudo bash scripts/install_service.sh
```

This installs a **`--user`** systemd unit (`~/.config/systemd/user/theeyebeta-dataapi.service`),
not a system one — `sudo` is only used to enable linger for your user so the
service survives reboots without an active login session. Every command that
manages it afterward drops the `sudo` (see Service management below); plain
`sudo systemctl ... theeyebeta-dataapi` will report "Unit could not be found."

Logs are available via journald: `journalctl --user -u theeyebeta-dataapi -f`

**3. Install the GitHub Actions self-hosted runner (auto-deploys on push to `main`):**

GitHub Actions runners are registered per-repo (this account has no org-level runner
pool), and this machine also hosts a separate runner for `TheEyeBetaProd`. **Use a
dedicated directory for this repo's runner — never reuse another repo's runner
directory.** Reusing one re-registers it against this repo and breaks the other
repo's deploys.

```bash
mkdir -p ~/actions-runner-dataapi && cd ~/actions-runner-dataapi
```

Go to: **GitHub → TheEyeBetaDataAPI repo Settings → Actions → Runners → New self-hosted runner → Linux**,
and run the download + `./config.sh` commands GitHub provides from inside
`~/actions-runner-dataapi`. Then:

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

Verify registration succeeded before relying on it: `~/actions-runner-dataapi/.runner`
should exist and its `gitHubUrl` should point at `TheEyeBetaDataAPI`, and
`gh api repos/TheEyeBeta/TheEyeBetaDataAPI/actions/runners` should list it. Without
a registered runner, every push to `main` queues the `deploy` job forever and it
silently never runs — there's no error, just an indefinitely queued job in the
Actions tab.

After this, every push to `main` that passes CI will automatically pull the latest code, update dependencies, restart the service, and verify `/health`.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/bootstrap_local_env.py \
  --database-url "postgresql+psycopg://postgres:REPLACE_ME@localhost:5432/TheEyeBeta2025Live"
bash scripts/run_local.sh
```

Default bind: `127.0.0.1:7000`

## Service management

`theeyebeta-dataapi` runs as a **`--user`** systemd unit, not a system one —
no `sudo` for any of these (run as the same user the service was installed
for). `server.sh`/`./server.sh status` is a separate, unrelated nohup-based
path whose PID file doesn't track this service; it will report "Not running"
even when the API is up. Use the commands below instead.

```bash
# Restart
systemctl --user restart theeyebeta-dataapi

# Stop
systemctl --user stop theeyebeta-dataapi

# Start
systemctl --user start theeyebeta-dataapi

# Status
systemctl --user status theeyebeta-dataapi

# Logs
journalctl --user -u theeyebeta-dataapi -f
```

## Quick verification

```bash
curl -s http://127.0.0.1:7000/health
```

Service token flow (use a real prod client for gates — Lens or Admin bridge):

```bash
# Lens / AI Financial Advisor
TOKEN=$(curl -s -X POST "http://127.0.0.1:7000/api/v1/auth/service-token" \
  -u "ai-advisor-production:<SERVICE_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["advisor:read","market:read","signals:read","symbols:read"]}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

curl -s "http://127.0.0.1:7000/api/v1/advisor/context?ticker=AAPL" \
  -H "Authorization: Bearer ${TOKEN}"
```

Admin Frontend gateway (unauthenticated probe — expect 401 when up):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7000/admin/auth/me
```

Start all native services + tunnel (no Docker):

```bash
bash scripts/start_all_native.sh
```

Remote smoke test (via Cloudflare Tunnel) — prefer prod clients over template `vi-app`:

```bash
API_BASE_URL="https://dataapiprod.theeyebeta.store" \
SERVICE_CLIENT_ID="ai-advisor-production" \
SERVICE_CLIENT_SECRET="<SERVICE_SECRET>" \
bash scripts/verify_remote_access.sh
```

## Cloudflare Tunnel

See **[docs/TUNNEL_RUNBOOK.md](docs/TUNNEL_RUNBOOK.md)** for the full TheEyeBeta2025 tunnel guide.

| Public hostname | Local origin | Service |
|---|---|---|
| `dataapiprod.theeyebeta.store` | `http://127.0.0.1:7000` | TheEyeBetaDataAPI (canonical production origin) |
| `dataapi.theeyebeta.store` | `http://127.0.0.1:7000` | TheEyeBetaDataAPI (legacy alias) |
| `api.theeyebeta.store` | `http://127.0.0.1:8000` | TheEyeBetaLocal Main API |
| `admin.theeyebeta.store` | `http://127.0.0.1:8080` | The Eye hosted terminal |

Canonical config: [`deploy/cloudflared-config.yml`](deploy/cloudflared-config.yml)

The web terminal and locally bundled Windows terminal both call
`https://dataapiprod.theeyebeta.store` directly. Production CORS is restricted
to the admin web origin and the Tauri application origins. Administrative
mutations require `X-Idempotency-Key`; the gateway forwards bearer, request ID,
confirmation, dry-run, CSRF, cookie, and idempotency headers to admin-service.

```bash
# Sync DNS + remote ingress (no sudo)
bash scripts/sync_tunnel.sh

# Permanent systemd fix (sudo once — required if dataapi returns 502)
sudo bash scripts/fix_tunnel.sh
```

## Optional production hardening toggles

- Require `iss`/`aud` on every JWT decode (after inventory confirms no legacy tokens):
  - `JWT_REQUIRE_ISS_AUD=true`
- OIDC/JWKS user JWT validation:
  - `USER_JWT_JWKS_URL`, `USER_JWT_ISSUER`, `USER_JWT_AUDIENCE`, `USER_JWT_ALGORITHMS`
- Redis rate limiting backend:
  - `REDIS_URL`, `RATE_LIMIT_REDIS_PREFIX`
- mTLS service principal flow:
  - `SERVICE_MTLS_ENABLED=true`
  - `SERVICE_MTLS_SUBJECTS_JSON`
  - `TRUST_PROXY_HEADERS=true`

Consumer inventory for rotation / claim-enforcement planning: [`docs/IAM_CONSUMER_INVENTORY.md`](docs/IAM_CONSUMER_INVENTORY.md).

Additive IAM SQL (apply on host Postgres before enabling the matching feature flags):

- `deploy/iam_refresh_tokens.sql` — refresh tokens + `short_lived_tokens_enabled`
- `deploy/iam_auth_audit.sql` — `iam.auth_audit_log` + `least_privilege_default` column

New DB-backed clients can be provisioned narrow with:

```bash
python scripts/provision_db_service_client.py \
  --client-id example-reader \
  --display-name "Example reader" \
  --app-type vi-backend \
  --least-privilege \
  --scope market:read
```


## Rotate secrets

```bash
source .venv/bin/activate
python scripts/rotate_secrets.py
```

Performs a **zero-downtime** JWT signing rotation: moves the live signing secret
into `JWT_SIGNING_SECRET_PREVIOUS` / `USER_JWT_SECRET_PREVIOUS`, writes new
`CURRENT` values (and keeps `JWT_SECRET` / `USER_JWT_SECRET` aliases aligned),
and rotates `SERVICE_CLIENTS_JSON` client secrets. Restart the service, wait one
full max token TTL, then clear `*_PREVIOUS`. Step-by-step:
[`docs/SECRET_ROTATION_RUNBOOK.md`](docs/SECRET_ROTATION_RUNBOOK.md).

## DB-backed API key schema

See `docs/API_KEY_SCHEMA_RUNBOOK.md` for PostgreSQL schema and provisioning SQL.

Use [OTHEREND_TEST.md](OTHEREND_TEST.md) for a complete laptop verification workflow with sample successful responses.

Cross-platform Python script (Windows/Unix):

```bash
API_BASE_URL=https://dataapiprod.theeyebeta.store \
VI_CLIENT_ID=vi-app VI_CLIENT_SECRET=<secret> \
TRADE_CLIENT_ID=trade-engine TRADE_CLIENT_SECRET=<secret> \
ADMIN_CLIENT_ID=admin-tool ADMIN_CLIENT_SECRET=<secret> \
python scripts/other_end_e2e_test.py
```

Provision a DB-backed service credential:

```bash
python scripts/provision_db_service_client.py \
  --client-id vi-backend-prod \
  --display-name "VI Backend Prod" \
  --app-type vi-backend \
  --allow-existing
```

## E2E verification

See `OTHEREND_TEST.md` for a complete verification workflow with sample responses.

## TypeScript frontend tester

```bash
cd packages/theeyebeta-dataapi-plugin
npm install
npm run build
```
