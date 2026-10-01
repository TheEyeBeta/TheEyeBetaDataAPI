# TheEyeBetaDataAPI

**The secure data gateway for The Eye.** One authenticated, versioned HTTP API
(`/api/v1`) in front of a private PostgreSQL database, serving market data,
fundamentals, technical indicators, trading signals, macro and fixed-income
analytics to The Eye's products. Every caller gets a scoped, expiring token;
the database is never exposed.

| | |
|---|---|
| **Who uses it** | **Lens** (AI financial advisor, client `ai-advisor-production`) and the **TheEyeBetaAdmin Frontend** (web + Tauri terminal, via the `/admin/*` gateway). Details: [`docs/IAM_CONSUMER_INVENTORY.md`](docs/IAM_CONSUMER_INVENTORY.md) |
| **What it serves** | 60 documented operations (53 of them reads) across 21 route groups ([table below](#api-at-a-glance); full reference in [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)) |
| **Stack** | Python 3.12 · FastAPI · SQLAlchemy 2 + psycopg 3 · PostgreSQL · PyJWT · gunicorn/uvicorn · Prometheus/Grafana · Cloudflare Tunnel · GitHub Actions |
| **Status** | In active development; single production host. Known gaps: [`docs/TECH_DEBT.md`](docs/TECH_DEBT.md) |
| **Reviewer pack** | [Tech stack (1 page)](docs/TECH_STACK.md) · [Architecture](docs/ARCHITECTURE.md) · [Technical debt](docs/TECH_DEBT.md) |

## Architecture

```mermaid
flowchart LR
    subgraph consumers[Consumers]
        lens[Lens / AI Financial Advisor]
        admin[TheEyeBetaAdmin Frontend<br/>web + Tauri]
    end

    cf[Cloudflare Tunnel<br/>TLS at the edge]

    subgraph host[Production host]
        api[TheEyeBetaDataAPI<br/>FastAPI · gunicorn · :7000]
        as[admin-service<br/>TheEyeBetaProd · :7200]
        pg[(PostgreSQL<br/>theeyebeta · read-only<br/>iam · auth state)]
        mon[Prometheus + Grafana]
    end

    prod[TheEyeBetaProd pipelines]
    openai[OpenAI API<br/>optional]

    lens -- service token --> cf
    admin -- browser --> cf
    cf --> api
    api -- api_service role --> pg
    api -- "/admin/* allowlisted proxy" --> as
    api -. advisor chat .-> openai
    mon -- scrape /metrics --> api
    prod -- writes market data --> pg
```

Request path inside the API: **route → auth dependency (principal + scopes +
policy) → service → repository (SQL only) → domain models**. Errors are always
`{"error": {"code", "message", "request_id"}}`.

- **Data:** the `theeyebeta` schema is owned and written by TheEyeBetaProd; this
  API only reads it. The legacy `public` schema is not used.
- **Writes:** only to the `iam` schema — token bookkeeping, refresh tokens, the
  scope-denial audit log, and admin account create/deactivate (soft delete).
- **Database access:** the least-privilege `api_service` role
  ([`deploy/db_security.sql`](deploy/db_security.sql)), proven by the Postgres
  integration tests.

## Quickstart (about 5 minutes, no production access needed)

```bash
git clone https://github.com/TheEyeBeta/TheEyeBetaDataAPI && cd TheEyeBetaDataAPI
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 1. Unit tests: no database needed
pytest -q

# 2. Run the API against a local/dev database (never the live one)
python scripts/bootstrap_local_env.py \
  --environment development \
  --database-url "postgresql+psycopg://api_service:REPLACE_ME@127.0.0.1:5432/theeyebeta_dev"
bash scripts/run_local.sh            # http://127.0.0.1:7000, auto-reload
curl -s http://127.0.0.1:7000/health # {"status":"healthy","database":true,...}
```

`bootstrap_local_env.py` generates fresh secrets into `.env` (mode `600`) and
requires an explicit `--environment`. Replace `REPLACE_ME` with the real
password. In development, interactive docs are at `/docs`; they are disabled
in production.

**Integration tests** (IAM SQL + least-privilege role against a throwaway Postgres):

```bash
docker run -d --rm --name dataapi-pg -p 55432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/integration -q
docker stop dataapi-pg
```

## API at a glance

All routes need `Authorization: Bearer <token>` except health and the token
endpoints. Full parameters and response shapes: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).

| Group | Scope | Endpoints |
|---|---|---|
| Health | — | `GET /health` |
| Auth | — | `POST /api/v1/auth/service-token`, `POST /api/v1/auth/refresh` (opt-in), `POST /api/v1/auth/delegated-token` (`lens:delegate` clients) |
| Market data | `market:read` | `GET /api/v1/market-data/quotes` |
| Symbols | `symbols:read` | `GET /api/v1/symbols/search`, `/symbols/resolve` |
| Tickers | `market:read` / `analytics:read` | `GET /api/v1/tickers/{ticker}`, `/price-history`, `/corporate-actions`, `/fundamentals` |
| Financials | `analytics:read` | `GET /api/v1/financials/{ticker}/income\|balance\|cashflow\|quality` |
| Indicators | `analytics:read` | `GET /api/v1/indicators/{ticker}/technical\|risk\|valuation\|returns` |
| Analytics | `analytics:read` | `GET /api/v1/analytics/snapshots/{ticker}` |
| Signals | `signals:read` | `GET /api/v1/signals/latest` |
| News | `market:read` | `GET /api/v1/news/market`, `/news/ticker/{ticker}` |
| Reference | `market:read` | `GET /api/v1/reference/countries\|currencies\|exchanges\|sectors\|industries\|calendar` |
| Macro | `market:read` | `GET /api/v1/macro/series`, `/series/{code}`, `/latest`, `/regime` (also served at `/v1/macro/*`) |
| Fixed income | `market:read` | `GET /api/v1/fixed-income/regime`, `/history`, `/signals` |
| Universe | `market:read` | `GET /api/v1/universe/active`, `/cap-events` |
| Sectors | `market:read` | `GET /api/v1/sectors/daily` |
| Advisor | `advisor:read` | `GET /api/v1/advisor/context`, `POST /api/v1/advisor/chat` (aliases `/api/v1/context`, `/api/v1/chat`) |
| Portfolio | `portfolio:read` | `GET /api/v1/portfolio/state` (ownership-enforced) |
| Generic data | `admin:read` | `GET /api/v1/data/tables`, `/tables/{table}/columns`, `/tables/{table}/rows` |
| Admin | `admin:read` | `GET /api/v1/admin/dashboard` (ops HTML), `dashboard-data`, `audit-events`, `queries`, `named-query`, `etl-jobs`, `engine-status`, `worker-heartbeats`, `price-ticks/{ticker}`, `accounts` |
| Admin accounts | `admin:write` | `POST /api/v1/admin/accounts`; `DELETE /api/v1/admin/accounts/{user_uuid}` (soft delete, approval-code gated, 1 req/min) |
| Admin gateway | admin-service auth | `/admin/*` → admin-service, manifest-allowlisted, `X-Idempotency-Key` on mutations |

## Security model

- **Service auth:** client credentials (HTTP Basic) → short scoped JWT from
  `POST /api/v1/auth/service-token`. Credentials live hashed (bcrypt via
  pgcrypto) in `iam.*` when `SERVICE_CLIENT_AUTH_MODE=database`. A client only
  gets the scopes it requests, capped at its grants. Optional mTLS principal
  via trusted proxy headers.
- **User auth:** bearer JWT (symmetric `USER_JWT_SECRET` or OIDC/JWKS), personal
  API keys (`teb_uk_…`, expiring, revoked automatically when the account is
  deactivated), and Lens delegated tokens (tenant-bound, 1–15 min, read scopes only).
- **JWT hardening:** explicit algorithm allowlists, required `exp`/`iat`,
  ≥ 32-byte signing keys, zero-downtime rotation via `*_PREVIOUS` secrets,
  opt-in refresh tokens with rotate-on-use.
- **Policy kill switches:** tenant/application/subject/credential locks and
  revocations are checked on every request when `POLICY_ENFORCEMENT_ENABLED=true`
  (required in production); database errors fail closed.
- **Transport and abuse:** trusted-host allowlist, production CORS limited to
  the Admin Frontend origins, a per-IP rate limit on every request (Redis-backed
  when `REDIS_URL` is set) plus tighter per-subject limits on admin routes, security
  headers, 403 scope denials audited to `iam.auth_audit_log`.
- **Destructive actions:** account deactivation needs `admin:write` **and**
  `ADMIN_ACCOUNT_APPROVAL_CODE` (fail-closed if unset).
- **Secrets:** one `.env` (mode `600`, git-ignored, never committed; git
  history is clean). CI runs `pip-audit` on every push.

Scopes: `market:read`, `symbols:read`, `analytics:read`, `signals:read`,
`advisor:read`, `portfolio:read`, `admin:read`, `admin:write`, `admin:*`,
`lens:delegate`. See [`docs/API_REFERENCE.md#scopes`](docs/API_REFERENCE.md#scopes).

## Configuration

Every setting is an environment variable read by `app/core/config.py`; the
annotated template is [`.env.example`](.env.example). The ones you will touch:

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` / `staging` / `production` (production enables stricter validation, disables `/docs`) |
| `DATABASE_URL` | `postgresql+psycopg://api_service:…@host:5432/db` |
| `JWT_SECRET`, `USER_JWT_SECRET` | ≥ 32-byte signing keys (generated by the bootstrap script) |
| `SERVICE_CLIENT_AUTH_MODE` | `database` (production), `environment` or `hybrid` |
| `TRUSTED_HOSTS`, `CORS_ORIGINS`, `TRUST_PROXY_HEADERS` | Edge/proxy settings |
| `METRICS_ALLOWED_NETWORKS` | Who may scrape `/metrics` directly (default loopback); proxied requests always get 404 |
| `POLICY_ENFORCEMENT_ENABLED` | Must be `true` in production |
| `ADMIN_GATEWAY_ENABLED`, `ADMIN_SERVICE_URL` | `/admin/*` proxy (loopback URL only) |
| `ADMIN_ACCOUNT_APPROVAL_CODE` | Required to deactivate accounts; unset = always refused |
| `OPENAI_API_KEY` | Optional; advisor chat falls back to a data summary without it |

## Testing and CI

| Check | Command | CI job |
|---|---|---|
| Unit tests (no DB), incl. docs/OpenAPI drift, tunnel routing, deploy script, CI gate, Prometheus rule tests | `pytest -q` | `test` |
| Postgres integration (IAM SQL, grants, privilege boundaries, refresh families) | `TEST_POSTGRES_URL=… pytest tests/integration -q` | `integration` |
| HTTP API against TheEyeBetaProd's schema at `contracts/prod/PROD_SHA`, as `api_service` | `PROD_CONTRACT=1 TEST_POSTGRES_URL=… DATABASE_URL=…api_service…/dataapi_contract pytest tests/contract -q` (see `ci.yml`) | `prod-contract` |
| Lint, format, shell syntax, `promtool` rules/config | `ruff check .` · `ruff format --check .` | `lint` |
| Types (`app/`) | `mypy` | `typecheck` |
| Dependency advisories (runtime + dev) | `pip-audit -r requirements-dev.txt` | `audit` |
| Secret scan, full history | `gitleaks git --config .gitleaks.toml .` | `secrets` |

A push to `main` is deployed by the self-hosted `deploy` job only after **every**
job above passes (`tests/test_ci_gates.py` enforces this). `scripts/deploy.sh`
checks out the tested commit, installs, restarts the `--user` unit, requires
`/health` to report `"database": true`, and rolls back to the previous commit if
it does not. `scripts/e2e_admin_smoke.py` then checks the Admin path (no
secrets). Regenerate the Prod contract snapshot with
`scripts/prod_contract_snapshot.sh` when `PROD_SHA` moves. Dependabot opens
grouped minor/patch updates weekly.

## Operations

| Task | Where |
|---|---|
| First-time host setup, systemd service, self-hosted runner | [`docs/PRODUCTION_RUNBOOK.md`](docs/PRODUCTION_RUNBOOK.md) |
| Restart / logs | `systemctl --user restart theeyebeta-dataapi` · `journalctl --user -u theeyebeta-dataapi -f` (a `--user` unit: no `sudo`) |
| Health | `curl -s http://127.0.0.1:7000/health` |
| End-to-end verification | [`docs/E2E_VERIFICATION.md`](docs/E2E_VERIFICATION.md) |
| Cloudflare Tunnel | [`docs/TUNNEL_RUNBOOK.md`](docs/TUNNEL_RUNBOOK.md) |
| Rotate secrets (zero downtime) | `python scripts/rotate_secrets.py` → [`docs/SECRET_ROTATION_RUNBOOK.md`](docs/SECRET_ROTATION_RUNBOOK.md) |
| Provision a service client | `python scripts/provision_db_service_client.py --client-id … --display-name "…" --app-type … --least-privilege --scope market:read` |
| Personal API keys | [`docs/API_KEY_SCHEMA_RUNBOOK.md`](docs/API_KEY_SCHEMA_RUNBOOK.md) |
| Ops dashboard sign-in | [`docs/OPS_DASHBOARD_LOGIN.md`](docs/OPS_DASHBOARD_LOGIN.md) |
| Firewall, alerts, backups | [`docs/OPS_HARDENING.md`](docs/OPS_HARDENING.md) |

Public hostnames (config [`deploy/cloudflared-config.yml`](deploy/cloudflared-config.yml); full routing and ownership table in [`docs/OWNERSHIP.md`](docs/OWNERSHIP.md); tunnel changes need explicit operator approval — [`docs/TUNNEL_RUNBOOK.md`](docs/TUNNEL_RUNBOOK.md)):

| Hostname | Origin | Service |
|---|---|---|
| `dataapiprod.theeyebeta.store` | `127.0.0.1:7000` | This API (canonical) |
| `dataapi.theeyebeta.store` | `127.0.0.1:7000` | This API (legacy alias) |
| `api.theeyebeta.store` | `127.0.0.1:8000` | TheEyeBetaLocal main API |
| `admin.theeyebeta.store` | `127.0.0.1:8080` | TheEyeBetaAdminFrontend static terminal host (page only). Target decided in DEBT-01; **not yet activated** — the config must not be applied until `:8080` passes its health check, see [`docs/OWNERSHIP.md`](docs/OWNERSHIP.md) |

## Repository layout

```
app/        FastAPI app: api/routes → auth → services → repositories (SQL) → domain
tests/      pytest suite; tests/integration needs a scratch Postgres
scripts/    bootstrap, provisioning, secret rotation, deploy, tunnel helpers
deploy/     IAM SQL + least-privilege role, nginx, Prometheus/Grafana, tunnel config
docs/       API reference, runbooks, E2E verification, tech-debt log
packages/   TypeScript client (cd packages/theeyebeta-dataapi-plugin && npm ci && npm run build)
```

Contributor and agent conventions: [`AGENTS.md`](AGENTS.md). License: proprietary, see [`LICENSE`](LICENSE).
