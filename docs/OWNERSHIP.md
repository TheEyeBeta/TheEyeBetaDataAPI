# Ownership and Cross-Repo Contracts

One owner per asset across the five repositories, as verified on 2026-10-01
against:

| Repository | Revision inspected |
|---|---|
| TheEyeBetaDataAPI (this repo) | branch `claude/zen-rubin-6dhimj` |
| TheEyeBetaProd | `47d042f8c8b36308b07a88ad4d00050015772739` (`contracts/prod/PROD_SHA`) |
| TheEyeBetaAdminFrontend | `b75fd2aef4097c2d633eb388a7426b38a14e73cd` |
| AI-Financial-Advisor (Lens) | `d97ee7cfa31a121b571e8c1b1ceff79152945d27` |
| TheEyeBetaLocal | `b601f312e1622427a2cd04aca16fc11eba6804f5` |

Prod's counterpart is `TheEyeBetaProd/docs/architecture/ownership-and-contracts.md`;
the two must agree. "host-verify" means only a read-only check on the
production host can prove the live state; no repository does.

## 1. Ownership matrix

| Asset | Owner | Evidence |
|---|---|---|
| `theeyebeta` schema and all its migrations | **TheEyeBetaProd** (Alembic, `db/migrations`) | Prod ownership doc |
| `theeyebeta.dataapi_*` policy tables (C2) | **TheEyeBetaProd** (migration 0092); written only by admin-service | Prod 0092 |
| DB role `api_readonly` (policy reader, C1) | **TheEyeBetaProd** (0092). DataAPI never alters or drops it | `deploy/db_security.sql` |
| Market-data grants to the DataAPI role (C3) | **Open** in Prod; applied today by `deploy/db_security.sql` as an interim allowlist | DEBT-05 |
| `theeyebeta.latest_snapshots` table shape | **TheEyeBetaProd** `workers/latest_snapshot_worker.py` (created outside Alembic) | contract snapshot header |
| 10 host-only `theeyebeta` tables + `latest_snapshots.eps` | **Unowned in code** (exist only on the host) | `contracts/prod/host_only_*`, DEBT-04 |
| Production data pipelines and workers | **TheEyeBetaProd** | |
| admin-service (`:7200`): admin identity, MFA, RBAC, audit | **TheEyeBetaProd** (ADR 0017) | |
| Terminal **source** | **TheEyeBetaAdminFrontend** | AdminFrontend ADR 0001 |
| Terminal **bundle served at `/admin/terminal/`** | **TheEyeBetaProd** admin-service (`static/terminal`, CI-checked against AdminFrontend) | Prod C8 |
| `iam` schema (service clients, secrets, user API keys, refresh tokens, auth audit) | **TheEyeBetaDataAPI** (`deploy/iam_*.sql`) | |
| DB login role `api_service` | **TheEyeBetaDataAPI** (`deploy/db_security.sql`) | |
| Public HTTP API `/api/v1/*`, service tokens, delegated tokens | **TheEyeBetaDataAPI** | |
| `/admin/*` gateway on `dataapiprod` (allowlist, header policy) | **TheEyeBetaDataAPI** (`app/api/routes/admin_gateway.py`); the routes behind it are Prod's | `contracts/prod/admin_route_families.json` |
| Lens / advisory app and its DataAPI client | **AI-Financial-Advisor** | `backend/websearch_service/app/services/dataapi_client.py` |
| Local trading API `:8000`, Trask `:8090` | **TheEyeBetaLocal** | |
| Cloudflare tunnel (`my-api`) | **Operator**; each hostname's origin is declared by the repo that owns the service (section 2) | |
| Host, systemd, credentials, backups | **Operator** | |
| Prometheus server, rules loading, Grafana | **TheEyeBetaProd** (`infra/prometheus`) | Prod ownership doc |
| DataAPI alert rules (`deploy/prometheus/rules/dataapi_auth.yml`) | **TheEyeBetaDataAPI** authors them; Prod's Prometheus must load them | DEBT-13 |

## 2. Canonical routing table

| Public entry | Origin | Serves | Owner | Status |
|---|---|---|---|---|
| `dataapiprod.theeyebeta.store` | `127.0.0.1:7000` | DataAPI (canonical) | DataAPI | code |
| `dataapi.theeyebeta.store` | `127.0.0.1:7000` | DataAPI (legacy alias) | DataAPI | code |
| `dataapiprod.theeyebeta.store/admin/*` | DataAPI gateway → `http://127.0.0.1:7200/admin/*` (loopback) | Prod admin-service, allowlisted | DataAPI (gateway) / Prod (routes) | code, contract-tested |
| `admin.theeyebeta.store` | `127.0.0.1:7200` | Prod admin-service: terminal bundle **and its whole `/admin/*` API** | Prod (declared) | **OPEN, DEBT-01**; host-verify |
| `api.theeyebeta.store` | `127.0.0.1:8000` | TheEyeBetaLocal main API | Local | host-verify |
| (no hostname) | `0.0.0.0:8080` | AdminFrontend `server.mjs` static terminal host | AdminFrontend | no systemd unit in any repo; host-verify |

How the products use it (verified in their code):

- **Lens**: server-to-server only, `https://dataapiprod.theeyebeta.store/api/v1/*`.
- **AdminFrontend** (web and Tauri): every API call goes to
  `https://dataapiprod.theeyebeta.store` (`src/lib/runtime.ts`); the page itself
  is loaded from `https://admin.theeyebeta.store/admin/terminal/`.
- **admin-service → DataAPI** (data for the terminal):
  `ADMIN_DATAAPI_URL=https://dataapiprod.theeyebeta.store`, client
  `theeyebeta-prod-admin`.

### DEBT-01: `admin.theeyebeta.store` routing (open, P0 decision)

- Prod declares `admin.theeyebeta.store → :7200`. That publishes admin-service's
  entire API, including the routes DataAPI's gateway deliberately refuses
  (`POST /admin/users`, `GET /admin/health`, `GET /admin/dataapi/{path}`).
- Prod ADR 0017 makes DataAPI the single remote administrative origin.
  AdminFrontend's design says API traffic "targets DataAPI, not a public Prod
  `:7200`" and ships an `:8080` static host for the page.
- DataAPI's earlier docs said the hostname routes to `:8080`; its config file
  said `:7200`. Nothing in any repo shows which one is live.

Resolution belongs to the operator and TheEyeBetaProd. Either point
`admin.theeyebeta.store` at a page-only origin (the `:8080` host once it has a
unit, or a Cloudflare path rule that only admits `/admin/terminal/`), or accept
direct public admin-service exposure in writing. Until then this repo mirrors
Prod's declared `:7200` and refuses to push tunnel config without explicit
approval (`TUNNEL_CHANGE_APPROVED=yes`).

## 3. Tunnel change policy

- `scripts/watchdog_all.sh` and `scripts/start_all_native.sh` never change tunnel
  configuration. A failing tunnel probe is logged as an ALERT for a person.
- `scripts/sync_tunnel.sh` (Cloudflare remote ingress) and
  `scripts/fix_tunnel.sh` (`/etc/cloudflared/config.yml`) replace the **whole**
  ingress of the shared tunnel. Without `TUNNEL_CHANGE_APPROVED=yes` they print the
  plan and exit 2.
- `tests/test_tunnel_routing.py` keeps `deploy/cloudflared-config.yml`, this
  table and the scripts in agreement.

## 4. Coupling to TheEyeBetaLocal

DataAPI's scripts start or restart TheEyeBetaLocal only when `THEEYE_LOCAL_REPO`
points at its checkout; a wrong path fails fast. There is no implicit
`../TheEyeBetaLocal` default.
