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
| Public terminal **page host** (`admin.theeyebeta.store/admin/terminal/`) | **TheEyeBetaAdminFrontend** `server.mjs` on `:8080` (target, DEBT-01). Prod admin-service also embeds a copy of the bundle (`static/terminal`, Prod C8), which is not publicly routed under the target | AdminFrontend `server.mjs`, Prod C8 |
| `iam` schema (service clients, secrets, user API keys, refresh tokens, auth audit) | **TheEyeBetaDataAPI** (`deploy/iam_*.sql`) | |
| DB login role `api_service` | **TheEyeBetaDataAPI** (`deploy/db_security.sql`) | |
| Public HTTP API `/api/v1/*`, service tokens, delegated tokens | **TheEyeBetaDataAPI** | |
| `/admin/*` gateway on `dataapiprod` (allowlist, header policy) | **TheEyeBetaDataAPI** (`app/api/routes/admin_gateway.py`); the routes behind it are Prod's | `contracts/prod/admin_route_families.json` |
| Lens / advisory app and its DataAPI client | **AI-Financial-Advisor** | `backend/websearch_service/app/services/dataapi_client.py` |
| Local trading API `:8000`, Trask `:8090` | **TheEyeBetaLocal** | |
| Cloudflare tunnel (`my-api`) | **Operator**; each hostname's origin is declared by the repo that owns the service (section 2) | |
| Repository visibility of TheEyeBetaDataAPI | **Operator**: decided **PRIVATE** (proprietary infrastructure, DEBT-02); the GitHub setting is changed by the operator | |
| Host, systemd, credentials, backups | **Operator** | |
| Prometheus server, rules loading, Grafana | **TheEyeBetaProd** (`infra/prometheus`) | Prod ownership doc |
| DataAPI alert rules (`deploy/prometheus/rules/dataapi_auth.yml`) | **TheEyeBetaDataAPI** authors them; Prod's Prometheus must load them | DEBT-13 |

## 2. Canonical routing table

This is the **target architecture** (DEBT-01, decided 2026-10-01). "Live"
says whether the host has been verified to match it; nothing here is a claim
about the live tunnel.

| Public entry | Origin | Serves | Owner | Live |
|---|---|---|---|---|
| `dataapiprod.theeyebeta.store` | `127.0.0.1:7000` | DataAPI (canonical) | DataAPI | host-verify |
| `dataapi.theeyebeta.store` | `127.0.0.1:7000` | DataAPI (legacy alias) | DataAPI | host-verify |
| `dataapiprod.theeyebeta.store/admin/*` | DataAPI gateway → `http://127.0.0.1:7200/admin/*` (loopback) | Prod admin-service, allowlisted | DataAPI (gateway) / Prod (routes) | code, contract-tested |
| `admin.theeyebeta.store` | `127.0.0.1:8080` | AdminFrontend `server.mjs` static terminal host (page only; `/healthz`) | AdminFrontend | **pending activation**: no production unit for `:8080` proven yet |
| `api.theeyebeta.store` | `127.0.0.1:8000` | TheEyeBetaLocal main API | Local | host-verify |
| (no hostname) | `127.0.0.1:7200` | Prod admin-service | Prod | never a tunnel origin; reached only through the DataAPI gateway |

How the products use it (verified in their code):

- **Lens**: server-to-server only, `https://dataapiprod.theeyebeta.store/api/v1/*`.
- **AdminFrontend** (web and Tauri): every API call goes to
  `https://dataapiprod.theeyebeta.store` (`src/lib/runtime.ts`; `server.mjs`
  CSP `connect-src` allows only that origin). The page is served from
  `https://admin.theeyebeta.store/admin/terminal/` by `server.mjs`, which
  redirects every other `/admin/*` path to the page and proxies no API.
- **admin-service → DataAPI** (data for the terminal):
  `ADMIN_DATAAPI_URL=https://dataapiprod.theeyebeta.store`, client
  `theeyebeta-prod-admin`.

### DEBT-01: `admin.theeyebeta.store` routing

**Decision (operator, 2026-10-01): `admin.theeyebeta.store → 127.0.0.1:8080`.**
Architecturally resolved; host activation pending.

Why (verified across repos):

- Prod defines `:7200` as the admin-service backend.
- AdminFrontend `server.mjs` defines `:8080` as the static terminal host.
- AdminFrontend API traffic targets `https://dataapiprod.theeyebeta.store`.
- DataAPI owns the remote admin allowlist (gateway).
- Routing `admin.theeyebeta.store` to `:7200` would bypass that gateway and
  publish admin-service routes the gateway deliberately denies
  (`POST /admin/users`, `GET /admin/health`, `GET /admin/dataapi/{path}`).

Activation, in order (none of it is done from this repo):

1. The AdminFrontend audit gives `server.mjs` a production unit on `:8080`
   (binding loopback is advisable: it defaults to `0.0.0.0`), and
   `curl -sf http://127.0.0.1:8080/healthz` returns `{"ok":true,...}` on the host.
2. TheEyeBetaProd updates its C7 declaration (`infra/cloudflared/apply-p-net-01.sh`),
   which still says `:7200`.
3. The operator applies the tunnel config with
   `sudo TUNNEL_CHANGE_APPROVED=yes bash scripts/fix_tunnel.sh`. The script
   also refuses (exit 3) while the `:8080` health check fails.

## 3. Tunnel change policy

- `scripts/watchdog_all.sh` and `scripts/start_all_native.sh` never change tunnel
  configuration. A failing tunnel probe is logged as an ALERT for a person.
- `scripts/sync_tunnel.sh` (Cloudflare remote ingress) and
  `scripts/fix_tunnel.sh` (`/etc/cloudflared/config.yml`) replace the **whole**
  ingress of the shared tunnel. Without `TUNNEL_CHANGE_APPROVED=yes` they print the
  plan and exit 2. With approval, they still exit 3 without changing anything
  while `http://127.0.0.1:8080/healthz` is not healthy (DEBT-01 activation guard).
- `tests/test_tunnel_routing.py` keeps `deploy/cloudflared-config.yml`, this
  table and the scripts in agreement.

## 4. Coupling to TheEyeBetaLocal

DataAPI's scripts start or restart TheEyeBetaLocal only when `THEEYE_LOCAL_REPO`
points at its checkout; a wrong path fails fast. There is no implicit
`../TheEyeBetaLocal` default.
