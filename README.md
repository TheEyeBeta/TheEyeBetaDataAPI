# TheEyeBetaDataAPI

Secure multi-client data access layer between private PostgreSQL and external/internal consumers.
Runtime data is served from the canonical `theeyebeta` schema only; the legacy `public`
schema is deprecated for this API. This service is read-only. Editing/order/job systems
live outside this repo.

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
- Scope examples:
  - `market:read`
  - `analytics:read`
  - `admin:read`
  - `admin:*`

## API Reference

See **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** for the full endpoint reference including parameters, request/response schemas, required scopes, and curl examples.

### Capability route groups (summary)

| Group | Scope | Endpoints |
|---|---|---|
| Health | — | `GET /health` |
| Auth | — | `POST /api/v1/auth/service-token` |
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
| Admin | `admin:read` | `GET /api/v1/admin/audit-events\|dashboard-data\|named-query\|etl-jobs\|engine-status\|worker-heartbeats\|price-ticks/{ticker}` |

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

Logs are available via journald: `sudo journalctl -u theeyebeta-dataapi -f`

**3. Install the GitHub Actions self-hosted runner (auto-deploys on push to `main`):**

Go to: **GitHub → repo Settings → Actions → Runners → New self-hosted runner → Linux**

Run the commands GitHub provides, then:

```bash
cd actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
```

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

```bash
# Restart
sudo systemctl restart theeyebeta-dataapi

# Stop
sudo systemctl stop theeyebeta-dataapi

# Start
sudo systemctl start theeyebeta-dataapi

# Status
sudo systemctl status theeyebeta-dataapi

# Logs
sudo journalctl -u theeyebeta-dataapi -f
```

## Quick verification

```bash
curl -s http://127.0.0.1:7000/health
```

Service token flow:

```bash
TOKEN=$(curl -s -X POST "http://127.0.0.1:7000/api/v1/auth/service-token" \
  -u "vi-app:<SERVICE_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["advisor:read","market:read","signals:read"]}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

curl -s "http://127.0.0.1:7000/api/v1/advisor/context?ticker=AAPL" \
  -H "Authorization: Bearer ${TOKEN}"
```

Start all native services + tunnel (no Docker):

```bash
bash scripts/start_all_native.sh
```

Remote smoke test (via Cloudflare Tunnel):

```bash
API_BASE_URL="https://dataapi.theeyebeta.store" \
SERVICE_CLIENT_ID="vi-app" \
SERVICE_CLIENT_SECRET="<SERVICE_SECRET>" \
bash scripts/verify_remote_access.sh
```

## Cloudflare Tunnel

See **[docs/TUNNEL_RUNBOOK.md](docs/TUNNEL_RUNBOOK.md)** for the full TheEyeBeta2025 tunnel guide.

| Public hostname | Local origin | Service |
|---|---|---|
| `dataapi.theeyebeta.store` | `http://127.0.0.1:7000` | TheEyeBetaDataAPI |
| `api.theeyebeta.store` | `http://127.0.0.1:8000` | TheEyeBetaLocal Main API |
| `admin.theeyebeta.store` | `http://127.0.0.1:7200` | TheEyeBetaProd admin |

Canonical config: [`deploy/cloudflared-config.yml`](deploy/cloudflared-config.yml)

```bash
# Sync DNS + remote ingress (no sudo)
bash scripts/sync_tunnel.sh

# Permanent systemd fix (sudo once — required if dataapi returns 502)
sudo bash scripts/fix_tunnel.sh
```

## Optional production hardening toggles

- OIDC/JWKS user JWT validation:
  - `USER_JWT_JWKS_URL`, `USER_JWT_ISSUER`, `USER_JWT_AUDIENCE`, `USER_JWT_ALGORITHMS`
- Redis rate limiting backend:
  - `REDIS_URL`, `RATE_LIMIT_REDIS_PREFIX`
- mTLS service principal flow:
  - `SERVICE_MTLS_ENABLED=true`
  - `SERVICE_MTLS_SUBJECTS_JSON`
  - `TRUST_PROXY_HEADERS=true`

## Rotate secrets

```bash
source .venv/bin/activate
python scripts/rotate_secrets.py
```

Rotates `JWT_SECRET`, `USER_JWT_SECRET`, and all `SERVICE_CLIENTS_JSON` client secrets.

## DB-backed API key schema

See `docs/API_KEY_SCHEMA_RUNBOOK.md` for PostgreSQL schema and provisioning SQL.

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
