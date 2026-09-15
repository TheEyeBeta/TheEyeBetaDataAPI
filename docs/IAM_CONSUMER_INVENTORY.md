# IAM Consumer Inventory (Phase 0+)

**Status:** living inventory — updated after IAM hardening deploy (2026-09-15).  
**Scope:** every consumer of DataAPI auth surfaces, with **production priority** for the
two products that must keep working: **Lens (AI Financial Advisor)** and
**TheEyeBetaAdmin Frontend** (hosted / Tauri terminal).

Evidence sources are cited as paths. Items labeled **Guess** are not confirmed from
live production DB rows or sibling-repo configs.

---

## Production consumers that matter

These are the only product surfaces operators must protect when changing auth:

| Product | How it reaches DataAPI | Live IAM principal | Auth model |
|---|---|---|---|
| **Lens / AI Financial Advisor** | Advisor backend → DataAPI `/api/v1/*` | `ai-advisor-production` | Service client Basic → `/api/v1/auth/service-token` → Bearer (60 min). End-user Supabase/JWT stays on the Advisor backend — **not** sent to DataAPI. |
| **TheEyeBetaAdmin Frontend** | Browser → `https://dataapiprod.theeyebeta.store/admin/*` → DataAPI admin gateway → Prod admin-service `:7200`; admin-service then calls DataAPI `/api/v1/*` for market/terminal data | UI: Prod admin session (cookies/Bearer via gateway). Data hop: `theeyebeta-prod-admin` (and related `admin-terminal-production`) | Gateway forwards Prod auth headers. DataAPI JWT is issued only for the **server-side** admin-service → DataAPI call. |

**Post-deploy smoke (2026-09-15, Mac host):**

| Check | Result |
|---|---|
| `ai-advisor-production` token + quotes / symbols / advisor context | **200**, `expires=60`, no refresh |
| `theeyebeta-prod-admin` + `admin-terminal-production` token + quotes / symbols | **200**, `expires=60`, no refresh |
| `ADMIN_GATEWAY_ENABLED` | **true** → `http://127.0.0.1:7200` |
| Unauthenticated `GET /admin/auth/me`, `/admin/terminal-data/modules` | **401** (gateway up, auth required) |
| `short_lived_tokens_enabled` for both product clients | **false** (long-lived service tokens) |

**Not a production product consumer:** `vi-app` / “VI analytics”. That name remains in
`.env.example`, unit tests, and ops smoke scripts as a **template / legacy IAM row**
only. There is no VI app in active use — do not treat it as a release gate.

---

## Auth surfaces this API exposes

| Surface | Mechanism | Issued by | Default lifetime (config) | Evidence |
|---|---|---|---|---|
| Service access JWT | Client credentials → `POST /api/v1/auth/service-token` → Bearer JWT (`token_use=service`) | DataAPI (`JWT_SECRET`, HS256) | `SERVICE_TOKEN_EXPIRES_MINUTES` **60** | `app/api/routes/auth.py`, `app/auth/tokens.py`, `app/core/config.py` |
| Lens delegated JWT | Client credentials + user subject token → `POST /api/v1/auth/delegated-token` → Bearer JWT (`token_use=delegated`) | DataAPI (`JWT_SECRET`) | `DELEGATED_TOKEN_EXPIRES_MINUTES` **5** | `app/api/routes/auth.py`, `app/auth/tokens.py` — **unused in prod IAM** (no `lens:delegate` grant) |
| User JWT (inbound) | Bearer JWT (`token_use` absent or `user`) | External IdP / app using `USER_JWT_SECRET` or OIDC JWKS | Issuer-controlled | Capability exists; **no live product caller found** |
| User API key | Opaque Bearer `teb_uk_<16hex>_<secret>` | Operators via SQL/CLI | Optional `expires_at` | **0** live keys (2026-09-15) |
| Service client secret | HTTP Basic for token endpoints | Provision scripts / DB | Optional `expires_at` | `deploy/iam_api_key_schema.sql` |
| Service mTLS headers | Trusted proxy headers | Edge/proxy | N/A | Default **disabled** on prod host |
| `/admin/*` gateway | Allowlisted reverse proxy to Prod admin-service `:7200` | **Prod admin auth** (cookie / Bearer / CSRF / idempotency forwarded) | Prod-controlled | `app/api/routes/admin_gateway.py` (**do not change for IAM hardening**) |

Signing vs validation:

- **Service + delegated JWTs** use `JWT_SECRET` / `JWT_SIGNING_SECRET_*`.
- **Inbound user JWTs** use `USER_JWT_SECRET` or `USER_JWT_JWKS_URL`. DataAPI does **not** mint ordinary user JWTs.

---

## 1. Service-client token consumers (server-to-server)

### 1.1 Lens — `ai-advisor-production` (**primary**)

| Field | Value |
|---|---|
| **Product** | AI Financial Advisor / Lens backend (`AI-Financial-Advisor/.../dataapi_client.py`) |
| **Auth mechanism** | `SERVICE_CLIENT_ID` / `DATAAPI_CLIENT_ID` + secret → `/api/v1/auth/service-token` |
| **Driver** | Server-to-server |
| **Approx token lifetime** | 60 minutes (`short_lived_tokens_enabled=false`) |
| **Live scopes** | `advisor:read`, `market:read`, `signals:read`, `symbols:read` |
| **Evidence** | Sibling `dataapi_client.py`; `scripts/provision_integrations.sh` (`ai-advisor-${ENVIRONMENT}`); live IAM row |

### 1.2 TheEyeBetaAdmin Frontend data bridge — `theeyebeta-prod-admin` (**primary**)

| Field | Value |
|---|---|
| **Product** | Hosted/Tauri terminal (`TheEyeBetaAdminFrontend`) via Prod `admin_service` |
| **Auth mechanism** | Admin-service uses `ADMIN_DATAAPI_CLIENT_ID=theeyebeta-prod-admin` → `/service-token` for `/api/v1/*` data; browser talks only to `/admin/*` on DataAPI origin |
| **Driver** | Server-to-server (admin-service) + human UI (gateway) |
| **Approx token lifetime** | 60 minutes |
| **Related clients** | `admin-terminal-production`, `admin-tool-production`, `admin-tool` (same family; broad admin scopes) |
| **Evidence** | `TheEyeProd/services/admin_service/api/dataapi.py`, `settings.py` (`ADMIN_DATAAPI_*`); Frontend `PRODUCTION_API_ORIGIN=https://dataapiprod.theeyebeta.store` |

### 1.3 Other IAM rows (not release gates)

| client_id | Role |
|---|---|
| `trade-engine` / `trade-engine-production` | Optional Local/engine integrations; hold `trades:write` but DataAPI has **no trade routes** |
| `owner-master-oneoff` | Operator one-off; broad scopes |
| `vi-app` | **Legacy / template only** — present in IAM and docs/examples; **not** an active product |

### 1.4 TypeScript plugin / ops scripts

| Consumer | Notes |
|---|---|
| `@theeyebeta/dataapi-plugin` | Integrator helper; service-token only |
| `scripts/verify_remote_access.sh` | Ops smoke; example client id often `vi-app` — prefer `ai-advisor-production` or `theeyebeta-prod-admin` for prod checks |
| CI | Dummy secrets for pytest only |

---

## 2. User JWT consumers

| Consumer | Status |
|---|---|
| Inbound user JWT to DataAPI `/api/v1/*` | **None found** in Lens, Admin Frontend, or Prod admin-service |
| Lens subject → `/delegated-token` | **Unused** — no `lens:delegate` scope in prod IAM |
| Lens end-user JWT | Validated by **Advisor backend** (Supabase), not DataAPI |

Live journal sample (7d): `auth_type=service` and `auth_type=none` only — no `user` / `api_key` / `delegated`.

---

## 3. User API key holders

| Field | Value |
|---|---|
| Live `iam.user_api_keys` | **0** rows (2026-09-15) |
| Sibling apps using `teb_uk_*` | **None found** |

---

## 4. `/admin/*` consumers (TheEyeBetaAdmin Frontend)

Browser → Cloudflare → DataAPI `:7000` `/admin/*` → loopback admin-service `:7200`.

| Consumer | Path | Auth authority |
|---|---|---|
| Hosted terminal (`admin.theeyebeta.store` → Node `:8080` / DataAPI origin) | `/admin/auth/*`, `/admin/terminal-data/*`, … | Prod admin-service session |
| Tauri desktop | Same SPA origins (`tauri://localhost`, …) | Same |

DataAPI **forwards** `Authorization`, cookies, CSRF, confirm, dry-run, idempotency — it does **not** re-validate those as DataAPI JWTs. Do not confuse with DataAPI-native `/api/v1/admin/*` (requires `admin:read` / `admin:write`).

---

## 5. Optional / disabled paths

| Path | Prod status |
|---|---|
| Service mTLS | `SERVICE_MTLS_ENABLED` unset → **false** |
| Policy enforcement | `POLICY_ENFORCEMENT_ENABLED=true` on host |
| Env-JSON service clients | `SERVICE_CLIENT_AUTH_MODE=database` (JSON keys may still exist for local/legacy) |

---

## 6. Lifetime summary (rotation planning)

| Credential | Max relevant TTL | Note |
|---|---|---|
| Service JWT (Lens + Admin bridge) | **60 min** | Wait ≥ this before clearing `JWT_SIGNING_SECRET_PREVIOUS` |
| Delegated JWT | **5 min** | Unused in prod today |
| User JWT | N/A (no inbound callers) | Keep `USER_JWT_*` configured but separate from service rotation |
| User API key | N/A (none live) | |
| Service client secret | Unbounded unless `expires_at` set | Rotate via provision scripts, not JWT runbook |

---

## 7. Open questions — status

1. **Live clients:** **CLOSED** — see tables above; product gates are Lens + Admin Frontend only.
2. **User JWT / iss+aud:** **CLOSED** — no inbound user-JWT product callers; service tokens already carry `iss`/`aud`/`iat`/`exp`. `JWT_REQUIRE_ISS_AUD=true` recommended when ready.
3. **Lens `lens:delegate`:** **CLOSED — unused** in prod IAM.
4. **User API keys:** **CLOSED** — zero rows.
5. **Trade write scopes:** **CLOSED** — scopes exist without routes; not a Lens/Admin blocker.
6. **mTLS:** **CLOSED** — disabled.

### Staging note

Host `ENVIRONMENT=production` → `TheEyeBeta2025Live`. Sibling DB `TheEyeBetaDataAPI` was used for staging IAM SQL / refresh soak. Confirm `api_service` grants on `refresh_tokens` / `auth_audit_log` if the API login is not the table owner.

---

## 8. Phase gating notes

- **Release gate for auth changes:** smoke **Lens** (`ai-advisor-production`) and **Admin bridge** (`theeyebeta-prod-admin` / gateway 401-without-cookie + healthy admin-service), not `vi-app`.
- Keep both product clients on `short_lived_tokens_enabled=false` until those apps explicitly support refresh.
- `/admin/*` gateway contract remains untouched.
- Do not flip `JWT_REQUIRE_ISS_AUD` without a post-flip Lens + Admin smoke.

---

## Revision

| Rev | Date | Change |
|---|---|---|
| 0 | 2026-09-14 | Initial inventory from repo evidence |
| 1–2 | 2026-09-14/15 | Host probes, claims, mTLS, Lens unused |
| 3 | 2026-09-15 | Consumer search: no inbound user-JWT callers |
| 4 | 2026-09-15 | **Canonical consumers = Lens + TheEyeBetaAdmin Frontend**; `vi-app` demoted to legacy/template; live smoke recorded |
