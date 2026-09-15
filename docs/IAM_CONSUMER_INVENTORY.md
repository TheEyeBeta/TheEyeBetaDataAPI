# IAM Consumer Inventory (Phase 0)

**Status:** inventory only — no runtime behavior changes.  
**Date:** 2026-09-14  
**Scope:** every consumer of DataAPI auth surfaces, inferred from this repository’s code, env templates, provision scripts, and runbooks.

Evidence sources are cited as paths. Items labeled **Guess** or **Unknown** are not confirmed from live production DB rows or sibling-repo configs in this pass.

---

## Auth surfaces this API exposes

| Surface | Mechanism | Issued by | Default lifetime (config) | Evidence |
|---|---|---|---|---|
| Service access JWT | Client credentials → `POST /api/v1/auth/service-token` → Bearer JWT (`token_use=service`) | DataAPI (`JWT_SECRET`, HS256) | `SERVICE_TOKEN_EXPIRES_MINUTES` **60** | `app/api/routes/auth.py`, `app/auth/tokens.py`, `app/core/config.py` |
| Lens delegated JWT | Client credentials + user subject token → `POST /api/v1/auth/delegated-token` → Bearer JWT (`token_use=delegated`) | DataAPI (`JWT_SECRET`) | `DELEGATED_TOKEN_EXPIRES_MINUTES` **5** | `app/api/routes/auth.py`, `app/auth/tokens.py` |
| User JWT (inbound) | Bearer JWT (`token_use` absent or `user`) | External IdP / app using `USER_JWT_SECRET` or OIDC JWKS | **Unknown** (issuer-controlled) | `app/auth/tokens.py::decode_user_token` |
| User API key | Opaque Bearer `teb_uk_<16hex>_<secret>` (no token exchange) | Operators via SQL/CLI (`iam.issue_user_api_key` / `provision_user_api_key.py`) | Optional `expires_at`; **null = no expiry** today | `app/auth/user_api_keys.py`, `deploy/iam_user_api_key_schema.sql` |
| Service client secret | HTTP Basic for token endpoints (hashed in `iam.service_client_secrets` or env JSON) | Provision scripts / DB functions | Optional `expires_at`; **null = no expiry** | `deploy/iam_api_key_schema.sql`, `app/auth/service_clients.py` |
| Service mTLS headers | Trusted proxy headers → service principal (no Bearer) | Edge/proxy + `SERVICE_MTLS_*` | N/A (sessionless per request) | `app/auth/dependencies.py`; default **disabled** |
| `/admin/*` gateway | Allowlisted reverse proxy to Prod admin-service `:7200` | **Prod admin auth** (cookie / Bearer / CSRF / idempotency headers forwarded) | Prod-controlled | `app/api/routes/admin_gateway.py` (**out of scope for hardening code changes**) |

Signing vs validation secrets (important for later phases):

- **Service + delegated JWTs** are signed/verified with `JWT_SECRET` (`settings.jwt_secret`).
- **Inbound user JWTs** are verified with `USER_JWT_SECRET` (symmetric) or `USER_JWT_JWKS_URL` (asymmetric). DataAPI does **not** mint ordinary user JWTs in-repo.

---

## 1. Service-client token consumers (server-to-server)

These obtain a short-lived service JWT via Basic auth against `/api/v1/auth/service-token`, then call `/api/v1/*` with `Authorization: Bearer …`.

### 1.1 `vi-app` (canonical smoke / env-template name)

| Field | Value |
|---|---|
| **Auth mechanism** | Service client credentials → service JWT |
| **Driver** | Server-to-server |
| **Approx token lifetime** | 60 minutes (default `SERVICE_TOKEN_EXPIRES_MINUTES`) |
| **Typical scopes (template)** | `market:read`, `symbols:read`, `analytics:read`, `advisor:read`, `signals:read` |
| **Evidence** | `.env.example` `SERVICE_CLIENTS_JSON`; `README.md` / `scripts/verify_remote_access.sh` / `OTHEREND_TEST.md` use `vi-app` |
| **Notes** | Name used heavily in docs and tests. **Guess:** production may also use DB-backed IDs such as `vi-backend-prod` / `ai-advisor-production` (see below) rather than literal `vi-app`. |

### 1.2 VI / analytics backend (`vi-backend` app type)

| Field | Value |
|---|---|
| **Auth mechanism** | DB-backed service client → service JWT |
| **Driver** | Server-to-server |
| **Approx token lifetime** | 60 minutes |
| **Default scopes (schema)** | `advisor:read`, `market:read`, `symbols:read`, `analytics:read` |
| **Evidence** | `deploy/iam_api_key_schema.sql` client type + defaults; `docs/API_KEY_SCHEMA_RUNBOOK.md` example `vi-backend-prod` |
| **Notes** | Intended consumer family for “VI desktop/laptop analytics”. Exact live `client_id` values: **Unknown** without querying `iam.service_clients`. |

### 1.3 AI Financial Advisor / mobile backend (`mobile-backend` app type)

| Field | Value |
|---|---|
| **Auth mechanism** | DB-backed service client → service JWT |
| **Driver** | Server-to-server |
| **Approx token lifetime** | 60 minutes |
| **Default scopes (schema)** | `advisor:read`, `market:read`, `symbols:read` (+ script often adds `signals:read`) |
| **Evidence** | `scripts/provision_integrations.sh` provisions `ai-advisor-${ENVIRONMENT}`; IAM defaults in `deploy/iam_api_key_schema.sql` |
| **Notes** | Maps to “AI-Financial-Advisor backend” in provision script comments. **Guess:** this is the primary advisor-app backend consumer. |

### 1.4 Trade engine (`trade-engine` / `trade-engine-${ENVIRONMENT}`)

| Field | Value |
|---|---|
| **Auth mechanism** | Service client credentials → service JWT; optional mTLS header path if enabled |
| **Driver** | Server-to-server (automated engine / jobs) |
| **Approx token lifetime** | 60 minutes (JWT); client secret may have optional `expires_at` |
| **Default scopes (schema)** | `trades:write`, `portfolio:read`, `internal:jobs` (+ provision script may add `market:read`) |
| **Evidence** | `.env.example`, `deploy/iam_api_key_schema.sql`, `scripts/provision_integrations.sh`, `tests/test_mtls_auth.py`, `OTHEREND_TEST.md` |
| **Notes** | README states this DataAPI is **read-only**; `trades:write` / `/api/v1/trades/orders` appear in older laptop docs (`OTHEREND_TEST.md`) but **no trades route exists in this tree**. Treat trade-write flows as **legacy/doc drift** unless a sibling service still calls removed endpoints. Portfolio **read** remains a live DataAPI surface. |

### 1.5 Admin tool (`admin-tool` / `admin-tool-${ENVIRONMENT}`)

| Field | Value |
|---|---|
| **Auth mechanism** | Service client credentials → service JWT against **DataAPI-native** `/api/v1/admin/*` (not `/admin/*`) |
| **Driver** | Server-to-server and/or operator scripts |
| **Approx token lifetime** | 60 minutes |
| **Default scopes (schema)** | `admin:read`, `admin:write`, `internal:jobs` (env template historically used `admin:*`) |
| **Evidence** | `.env.example`, `deploy/iam_api_key_schema.sql`, `scripts/provision_integrations.sh`, `tests/test_admin_accounts_route.py` |
| **Notes** | Used for DataAPI admin reads and account create/deactivate (`admin:write` + approval code). Distinct from hosted-terminal Prod admin auth. |

### 1.6 TypeScript consumer plugin (`@theeyebeta/dataapi-plugin`)

| Field | Value |
|---|---|
| **Auth mechanism** | Service client id/secret → `/api/v1/auth/service-token` (client helper) |
| **Driver** | Server-to-server (embedded in other Node backends) |
| **Approx token lifetime** | Same as service JWT (60 min default) |
| **Evidence** | `packages/theeyebeta-dataapi-plugin/src/index.ts`, package README |
| **Notes** | Packaging for integrators; not itself a production principal. |

### 1.7 Operator / CI smoke scripts

| Consumer | Mechanism | Driver | Lifetime | Evidence |
|---|---|---|---|---|
| `scripts/verify_remote_access.sh` | Service token (default scopes advisor+market) | Human / ops | 60 min | script |
| `OTHEREND_TEST.md` laptop checklist | `vi-app` / `trade-engine` / `admin-tool` tokens | Human | 60 min | doc |
| `scripts/rotate_secrets.py` | Rotates env secrets (not a runtime caller) | Human | N/A | README |
| GitHub Actions CI | Dummy env JWT/API secrets for pytest only | CI | N/A | `.github/workflows/ci.yml` |

---

## 2. User JWT consumers

Inbound user JWTs are validated by DataAPI; issuance lives outside this repo.

| Consumer | Auth mechanism | Driver | Approx lifetime | Evidence / status |
|---|---|---|---|---|
| **Configured user IdP / app** | Bearer user JWT (`USER_JWT_SECRET` HS256 **or** `USER_JWT_JWKS_URL` RS256 family) | Human sessions (via that IdP) | **Unknown** — issuer TTL | `app/auth/tokens.py`, `docs/API_REFERENCE.md`, `.env.example` |
| **Lens subject token (pre-delegation)** | User JWT presented as `subject_token` to `/api/v1/auth/delegated-token` | Human (Lens) via Lens backend | **Unknown** (Lens/IdP) | `app/api/routes/auth.py::issue_delegated_token` |
| **Lens delegated access (post-exchange)** | DataAPI-issued delegated JWT (data-only scopes) | Server-to-server on behalf of user | **5 minutes** | `app/auth/tokens.py::create_delegated_access_token`, `SCOPE_LENS_DELEGATE` |

**Default delegated scope intersection:** only scopes that appear in both the Lens service client’s grants and `LENS_DELEGATED_READ_SCOPES` (`market:read`, `symbols:read`, `analytics:read`, `signals:read`) — never admin/portfolio/advisor. Evidence: `app/auth/scopes.py`, `app/api/routes/auth.py`.

**Who holds `lens:delegate` in production:** **Unknown** without querying `iam.service_client_scopes`. Policy seeding is described in `docs/PRODUCTION_RUNBOOK.md` (Lens tenant / `LENS_ACCESS` via admin-service).

**Phase 1 implication:** service + delegated issuance already set `iss`/`aud`. Symmetric user-JWT decode currently expects `issuer=settings.jwt_issuer` and `audience=settings.jwt_audience` when not using JWKS overrides. Confirm whether any live user tokens omit these claims before flipping `JWT_REQUIRE_ISS_AUD` (flag introduced in Phase 1, default false).

---

## 3. User API key holders

| Field | Value |
|---|---|
| **Auth mechanism** | Opaque personal key `teb_uk_*` as Bearer (no refresh, no `/service-token`) |
| **Driver** | Human tools / bots / scripts holding a provisioned key |
| **Approx lifetime** | Per-key `expires_at`; **unset = never expires** today |
| **Provisioning** | Operator-only (`scripts/provision_user_api_key.py`, SQL `iam.provision_user_api_key`) — no self-service HTTP endpoint |
| **Evidence** | `app/auth/user_api_keys.py`, `deploy/iam_user_api_key_schema.sql`, `docs/API_KEY_SCHEMA_RUNBOOK.md` §H |
| **Named holders in this repo** | **None** — only example emails in docs (`trader@example.com`) |
| **Live inventory** | **Unknown** — query `iam.user_api_keys` / `iam.users` on the host DB |

Service secrets use a related prefix family (`teb_sk_*` mentioned in tests/docs) but those are **client credentials**, not end-user Bearer keys.

---

## 4. `/admin/*` consumers (context only — Prod auth, not DataAPI JWT)

These hit DataAPI’s gateway path `/admin/*`, which forwards to Prod admin-service on loopback `:7200`. They do **not** authenticate with DataAPI service/user JWTs for that hop; DataAPI forwards `Authorization`, cookies, CSRF, confirm, dry-run, and idempotency headers.

| Consumer | Path into DataAPI | Auth authority | Driver | Evidence |
|---|---|---|---|---|
| Hosted web terminal | Browser → `https://admin.theeyebeta.store` → terminal `:8080` → often proxies admin ops; terminal also configured to call DataAPI origin for data | Prod admin login / roles (`MASTER_ADMIN`, `OPERATOR`, …) for `/admin/*`; DataAPI Bearer for `/api/v1/*` when calling data | Human | `agent.md`, `AGENTS.md`, `docs/API_REFERENCE.md` intro, `deploy/cloudflared-config.yml` |
| Tauri desktop (“TheEye”) | Loads hosted terminal SPA; CORS allows `tauri://localhost` / `tauri.localhost` | Same as hosted terminal | Human | `agent.md`, `.env.example` `CORS_ORIGINS` |
| Direct callers of `/admin/*` on DataAPI origin | Cloudflare → DataAPI `:7000` `/admin/...` | Prod admin-service session/token | Human / tools | `app/api/routes/admin_gateway.py` |

**Do not confuse with** DataAPI-native `/api/v1/admin/*` (audit, accounts, named queries) which **does** require DataAPI scopes (`admin:read` / `admin:write`).

---

## 5. Optional / disabled paths

| Path | Default | Consumer if enabled | Evidence |
|---|---|---|---|
| Service mTLS headers | `SERVICE_MTLS_ENABLED=false` | Trade engine or other service behind trusted proxy | `app/core/config.py`, `tests/test_mtls_auth.py` |
| Policy enforcement | `POLICY_ENFORCEMENT_ENABLED` (example `.env` may show true) | Any principal after scope check | `app/auth/dependencies.py`, `app/policy/` |
| Admin gateway | `ADMIN_GATEWAY_ENABLED` | Terminal / Tauri / admin tools | `.env.example`, gateway router |
| Env-JSON service clients | Prod prefers `SERVICE_CLIENT_AUTH_MODE=database`; `environment`/`hybrid` still supported | Local/dev and legacy | `docs/API_KEY_SCHEMA_RUNBOOK.md` §8 |

---

## 6. Lifetime summary (for rotation / grace-period planning)

| Credential | Max relevant TTL today | Grace note for Phase 1–2 |
|---|---|---|
| Service JWT | **60 min** default (config 5–1440) | After secret rotation, wait ≥ max configured service TTL before discarding previous signing secret |
| Delegated JWT | **5 min** default (config 1–15) | Short; covered by same `JWT_SECRET` as service tokens |
| User JWT | **Unknown** | Must confirm IdP TTLs before requiring new claims or rotating `USER_JWT_SECRET` aggressively |
| User API key | Unbounded if `expires_at` null | Phase 5 grandfathering applies |
| Service client secret | Unbounded if `expires_at` null | Separate from JWT signing secret |

---

## 7. Open questions (resolve before flipping Phase 1–2 defaults)

1. **Live `iam.service_clients` rows:** **Partially closed (2026-09-14 host probe).**
   Production DB `TheEyeBeta2025Live` active clients:
   `admin-terminal-production`, `admin-tool`, `admin-tool-production`,
   `ai-advisor-production`, `owner-master-oneoff`, `theeyebeta-prod-admin`,
   `trade-engine`, `trade-engine-production`, `vi-app`.
   Literal `vi-app` **does** exist alongside `ai-advisor-production`.
2. **User JWT issuer:** which product mints tokens validated by `USER_JWT_SECRET` / JWKS, and whether all live tokens already carry `iss`/`aud`/`iat`/`exp`. **Still open — keep `JWT_REQUIRE_ISS_AUD=false`.**
3. **Lens production client:** which service client holds `lens:delegate`, and what subject-token TTL Lens uses. **Still open.**
4. **User API key holders:** active `teb_uk_*` keys with `expires_at IS NULL`.
   **Host probe 2026-09-14:** `user_api_keys_never_expire=0` (no never-expire actives at probe time). Re-check before backfill.
5. **Trade write consumers:** whether anything still expects `/api/v1/trades/*` (absent here) vs portfolio-read only. **Still open** (trade-engine clients exist in IAM).
6. **mTLS in prod:** is `SERVICE_MTLS_ENABLED` ever true on the live host? **Still open.**

### Staging / environment note (operator)

There is **no separate DataAPI staging database** on `the-eye-beta-server` today —
`ENVIRONMENT=production` and `DATABASE_URL` → `TheEyeBeta2025Live`. Additive IAM
SQL must not be applied to prod until a staging target exists **or** an explicit
maintenance window is approved for the single live DB. Host checkout at probe
time was `859e804` and did **not** yet contain `deploy/iam_refresh_tokens.sql` /
`deploy/iam_auth_audit.sql` (those files live in the unmerged laptop workspace).

Suggested host checks (operator, not committed secrets):

```sql
SELECT client_id, app_type, environment, is_active
FROM iam.service_clients
ORDER BY client_id;

SELECT c.client_id, array_agg(s.scope ORDER BY s.scope) AS scopes
FROM iam.service_clients c
JOIN iam.service_client_scopes s ON s.client_uuid = c.client_uuid
GROUP BY c.client_id;

SELECT count(*) AS keys, count(*) FILTER (WHERE expires_at IS NULL) AS never_expire
FROM iam.user_api_keys
WHERE is_active AND revoked_at IS NULL;
```

---

## 8. Phase gating notes

- **No client code changes** are implied by this inventory.
- Phase 1 should keep `JWT_REQUIRE_ISS_AUD` **default false** until questions 2–3 above are answered or the longest observed user/service TTL has elapsed after issuance starts always emitting claims (service/delegated already emit `iss`/`aud`).
- Phase 2 rotation of **`JWT_SECRET`** affects service + delegated tokens; rotation of **`USER_JWT_SECRET`** affects inbound user JWT validation only — treat as separate runbook steps.
- `/admin/*` gateway remains untouched for all later phases per project constraints.

---

## Revision

| Rev | Date | Change |
|---|---|---|
| 0 | 2026-09-14 | Initial inventory from repo evidence (Phase 0) |
