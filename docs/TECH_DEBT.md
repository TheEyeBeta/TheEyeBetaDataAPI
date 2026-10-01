# Technical Debt Log

Known weaknesses, what was done in this repository, and what is left. Last
reviewed 2026-10-01 (production baseline, `docs/DATAAPI_BASELINE_2026-10-01.md`;
DEBT-01 and DEBT-02 decisions recorded the same day).

Columns used for every item:

- **Severity**: P0 (blocks a production claim), P1 (real risk to a product
  gate), P2 (operational risk), P3 (hygiene).
- **Repo fix**: what this repository already does about it.
- **Remaining**: the next concrete action and who owns it.
- **Host-verify**: whether only a read-only check on the production host can
  prove the state.
- **Cross-repo**: which other repository has to change, if any.

## Open

| ID | Item | Sev | Repo fix done | Remaining | Host-verify | Cross-repo |
|---|---|---|---|---|---|---|
| DEBT-01 | `admin.theeyebeta.store` origin — **decision RESOLVED (architectural), host activation PENDING** | P1 (activation) | Operator decision 2026-10-01: `admin.theeyebeta.store → 127.0.0.1:8080` (AdminFrontend static terminal host); admin-service `:7200` is reachable only via the DataAPI gateway and is never a tunnel origin. `deploy/cloudflared-config.yml` holds the target with a DO NOT APPLY note; `sync_tunnel.sh`/`fix_tunnel.sh` need `TUNNEL_CHANGE_APPROVED=yes` **and** exit 3 while `http://127.0.0.1:8080/healthz` fails; watchdog/start scripts never touch the tunnel; `tests/test_tunnel_routing.py` | (1) AdminFrontend audit: production unit for `server.mjs` on `:8080` (bind loopback; it defaults to `0.0.0.0`) and a passing `/healthz` on the host; (2) Prod updates C7 (`infra/cloudflared/apply-p-net-01.sh`, still `:7200`); (3) operator applies with approval. Cloudflare is not changed from this repo | Yes: live ingress, `:8080` health | AdminFrontend (`:8080` unit), TheEyeBetaProd (C7) |
| DEBT-02 | Repository visibility — **decision RESOLVED: PRIVATE** (proprietary infrastructure), GitHub change PENDING | P0 until the setting is changed (operator action; not a code blocker) | Decision recorded (operator, 2026-10-01). gitleaks over full history: no real secrets (11 placeholder hits, allowlisted narrowly); secret scan gates CI | Operator changes the GitHub repository visibility to private (deliberately not done from an agent session). Until then the tunnel UUID, host user path, client IDs and ops detail stay public | No | No |
| DEBT-04 | 10 `theeyebeta` tables + `latest_snapshots.eps` exist only on the host; no Prod migration creates them | P1 | Listed in `contracts/prod/host_only_tables.txt`; shapes DataAPI needs are declared in `host_only_assumed.sql` and contract-tested (proves DataAPI SQL vs its own assumption only) | Prod adds migrations for them (or DataAPI stops reading them); until then compare `\d` on the host with `host_only_assumed.sql` | Yes | TheEyeBetaProd |
| DEBT-05 | Live DB role for DataAPI unconfirmed; Prod contract C3 (market-data grants) open | P1 | `db_security.sql` creates `api_service` (no superuser/createrole/bypassrls), membership in Prod's `api_readonly`, explicit SELECT allowlist; fails if `api_readonly` is missing; privilege boundaries tested on Postgres 16 | Operator: check `DATABASE_URL` user and `\du`/`\dp` on the host, then apply `db_security.sql`. Prod: own C3 grants | Yes | TheEyeBetaProd (C3) |
| DEBT-06 | Lens calls 4 routes it has no scope for | P1 | Pinned in `tests/contract` (`LENS_SCOPE_GAP` → 403): analytics snapshot, ticker fundamentals, financials, technical indicators need `analytics:read`, which `ai-advisor-production` does not hold per the 2026-09-15 inventory | Decide: grant `analytics:read` to `ai-advisor-production` (IAM row change, operator) or remove those calls from Lens. No scope was changed here | Yes: live scopes | AI-Financial-Advisor |
| DEBT-07 | `JWT_REQUIRE_ISS_AUD` on the host | P2 | Code default is `true`; all four consumers verified to send DataAPI-minted tokens (which carry `iss`/`aud`); suite runs enforced; compatibility tests | Remove any `JWT_REQUIRE_ISS_AUD=false` from the host `.env` at next deploy; run Lens + Admin smoke | Yes | No |
| DEBT-13 | DataAPI alert rules are not loaded anywhere | P2 | Rules validated by `promtool` and `tests/test_prometheus_rules.py` (metrics exported, handlers exist); `/metrics` restricted to direct local scrapes | Prod's `infra/prometheus/prometheus.yml` has no `dataapi` scrape job and does not load `dataapi_auth.yml`: add both in Prod, fire one test alert | Yes | TheEyeBetaProd |
| DEBT-16 | `theeyebeta.latest_snapshots` table is created outside Alembic (Prod worker) | P2 | Contract snapshot models it from Prod's own test DDL. Prod migration 0079's docstring says the host table has 72 columns; the worker model writes 40 | Prod moves the table into a migration so its shape is versioned | Yes | TheEyeBetaProd |
| DEBT-03 | Single production host, no staging tier | P2 | Deploy now: tested SHA only, DB-aware health, automatic rollback, post-deploy Admin E2E | Document backup + tested restore (incl. `iam`), separate staging `.env`/DB | Yes | No |
| DEBT-17 | Deploy job host assumptions | P2 | `deploy.sh` fails closed if the `--user` unit is not visible | Confirm on the runner host: `XDG_RUNTIME_DIR=/run/user/1000` matches the service user, `ADMIN_GATEWAY_ENABLED=true` (else the post-deploy Admin E2E fails by design) | Yes | No |
| DEBT-08 | `trades:write` / `internal:jobs` seeded but no route checks them | P3 | None (scopes are not removed without consumer proof) | Confirm TheEyeBetaLocal (`trade-engine`, requests `[]`) does not depend on them, then revoke | Yes | TheEyeBetaLocal |
| DEBT-12 | Host-specific paths | P3 | Local coupling now opt-in via `THEEYE_LOCAL_REPO` (fails fast on a bad path) | `scripts/provision_integrations.sh` hard-codes `/home/the-eye-beta/...`; tunnel credentials path in `deploy/cloudflared-config.yml` | No | No |
| DEBT-09 | Oversized modules | P3 | Contract tests now cover the SQL, so a split has a safety net | Split `sql_market_data.py` (~1,570 lines) by domain; serve the dashboard HTML from a template | No | No |
| DEBT-10 | Deferred dependency majors | P3 | `pip-audit` clean (runtime + dev) and gating | SQLAlchemy 2.1, openai 3.x, redis 8.x one at a time; Starlette test client warns `httpx` → `httpx2` | No | No |
| DEBT-14 | Bus factor of one | P3 | Runbooks, ownership matrix (`docs/OWNERSHIP.md`), CI gates encode the contracts | Quarterly fresh-machine setup from the README | No | No |
| DEBT-18 | 1 MB image (`the_eye_80s.png`) in git history | P3 | Not in the tree | None unless repo size matters; history is not rewritten | No | No |

## Resolved

| Item | Resolution (2026-10-01 unless noted) |
|---|---|
| Market-data SQL tested only against mocks (old #4) | `prod-contract` CI job runs every data route as `api_service` against TheEyeBetaProd's schema at `contracts/prod/PROD_SHA` |
| Refresh reuse did not revoke the family (old #8) | Reuse revokes all descendants; refresh needs the issuing client's credentials; client/subject mismatch revokes; concurrency tested on Postgres |
| `JWT_REQUIRE_ISS_AUD=false` default (old #6) | Default `true`; host part tracked as DEBT-07 |
| Watchdog could overwrite the shared tunnel (part of old #1) | Alert-only; tunnel scripts approval-gated |
| Sibling-repo coupling `../TheEyeBetaLocal` (part of old #11) | `THEEYE_LOCAL_REPO` opt-in, fail fast |
| No formatter, no type checking, deploy gated only on `test` (old #12) | `ruff format --check`, `mypy app/`, gitleaks, promtool; deploy needs every job (`tests/test_ci_gates.py`) |
| `deploy.sh` silent tmux fallback, deployed `origin/main` not the tested SHA, health ignored DB, no rollback | Fixed; `tests/test_deploy_script.py` |
| Admin gateway exposed methods Prod does not implement; path re-targeting via encoded characters | Manifest equals Prod's routes minus deliberate denials (`contracts/prod/admin_route_families.json`); forbidden characters and dot segments refused |
| Named-query DB errors returned SQL text; 422 echoed submitted values | Generic messages; regression tests |
| `/metrics` reachable through the public tunnel | Direct scrapes from `METRICS_ALLOWED_NETWORKS` only |
| Undocumented `/api/v1/context`, `/api/v1/chat`; wrong cap-events sample | Docs fixed; `tests/test_docs_openapi_sync.py` |
| 28 dependency advisories, FastAPI/Starlette upgrade, 422 path leak, CORS/env separation, JWT key length, LICENSE, Dependabot (2026-09) | See git history of this file |
