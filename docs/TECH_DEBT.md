# Technical Debt Log

What is known to be weak or unfinished, why it matters, and the plan. Ordered
by risk. Last reviewed 2026-09-28 (repo audit and cleanup).

Legend: **Risk** = what goes wrong if left alone. **Plan** = the concrete next step.

## Open

### 1. Tunnel config contradicts the documented routing for `admin.theeyebeta.store` — *Critical, decision needed*
- `AGENTS.md`, `README.md` and `docs/TUNNEL_RUNBOOK.md` say the hostname routes
  to the hosted terminal on `127.0.0.1:8080` and must not be repointed to
  `7200`. The committed `deploy/cloudflared-config.yml` (and the
  `scripts/fix_tunnel.sh` summary) still route it to admin-service on `:7200`.
- **Risk:** `sync_tunnel.sh` pushes the committed file to Cloudflare as remote
  ingress, and `watchdog_all.sh` runs it automatically when the tunnel looks
  unhealthy. The next run could expose admin-service directly on the public
  hostname, or undo whatever the live tunnel does today.
- **Plan:** check what the live tunnel serves (`cloudflared tunnel info`, the
  Cloudflare dashboard), then make the file and the docs agree in one commit.
  This was deliberately *not* changed in the cleanup, because the live state
  can't be seen from the repo.

### 2. Single production host, no staging tier — *Major*
- API, PostgreSQL, admin-service, CI runner, tunnel and monitoring share one
  machine. There is a staging IAM database on it (`TheEyeBetaDataAPI`) but no
  separate staging API. Pushes to `main` deploy straight to production.
- **Risk:** one hardware or OS failure takes every product down. There is no
  documented recovery time or recovery point.
- **Plan:** (a) record the backup job, retention and a tested restore in
  `OPS_HARDENING.md`, including the `iam` schema; (b) give staging its own
  `.env` (`--environment staging`) and database; (c) when revenue justifies
  it, move PostgreSQL to a managed instance.

### 3. Bus factor of one — *Major*
- One person has written and operates everything.
- **Mitigations now in place:** 5-minute quickstart, runbooks, `CODEOWNERS`,
  CI lint/audit/integration jobs, and Postgres integration tests that encode
  the IAM contract.
- **Plan:** keep `AGENTS.md` and the runbooks current as part of every change
  (the `readme-sync` skill), and do a "fresh machine" setup from the README
  once a quarter.

### 4. Market-data SQL is only tested against mocks — *Major*
- The `theeyebeta` schema is owned by TheEyeBetaProd; this repo has no copy of
  its DDL. `sql_market_data.py`, `sql_macro.py` and `sql_fixed_income.py` sit
  at 20–35% line coverage. The policy SQL (`theeyebeta.dataapi_*`) is unit-tested
  for its decisions, not against real tables.
- **Risk:** a column rename in a Prod migration ships green here and fails at
  runtime (`503 DATABASE_UNAVAILABLE`) for Lens.
- **Plan:** publish a schema-only snapshot of `theeyebeta` from Prod (e.g.
  `pg_dump --schema-only`) as a CI artifact, and add a contract job that runs
  every repository query against it with `EXPLAIN`.

### 5. Production database role not confirmed against the new grants — *Major*
- `deploy/db_security.sql` now defines a verified least-privilege `api_service`
  role. The previous file's `api_readonly` role (public schema only) could not
  run this API, and the repo doesn't record which role production connects as.
  `api_service` may already exist on the host with grants applied by hand.
- **Risk:** if production connects as an owner or superuser, a compromised API
  process has full database control.
- **Plan:** compare live grants (`\dp iam.*`, `\dp theeyebeta.*`) with
  `db_security.sql`, apply it (idempotent), point `DATABASE_URL` at
  `api_service`, smoke Lens and Admin, then drop `api_readonly` if it exists.

### 6. `JWT_REQUIRE_ISS_AUD` still `false` — *Minor, now unblocked*
- Every open question in `IAM_CONSUMER_INVENTORY.md` §7 is closed, and service
  tokens already carry `iss`/`aud`.
- **Plan:** set `JWT_REQUIRE_ISS_AUD=true`, then run the Lens and Admin smoke
  tests in `E2E_VERIFICATION.md`.

### 7. Unused legacy IAM grants — *Minor*
- `trades:write` and `internal:jobs` are still seeded by
  `deploy/iam_api_key_schema.sql` and `scripts/provision_integrations.sh` for
  `trade-engine`/`admin-tool`. No route checks them.
- **Plan:** confirm TheEyeBetaLocal no longer requests them, revoke them in
  `iam.service_client_scopes`, and drop them from the seed.

### 8. Refresh-token reuse rejects but does not revoke the family — *Minor*
- A replayed refresh token gets `401`, but the token that replaced it stays
  valid. Current practice is to revoke the whole chain on reuse.
- Low exposure today: refresh is opt-in and no product client has it enabled.
- **Plan:** follow `replaced_by` and revoke descendants on reuse before any
  client enables refresh.

### 9. Oversized modules — *Minor*
- `app/repositories/sql_market_data.py` (~1,570 lines) mixes a dozen domains.
  `app/api/routes/admin_dashboard_html.py` is a 930-line HTML string.
- **Plan:** split the repository by domain (quotes, fundamentals, indicators,
  reference, admin) behind the existing interfaces, and serve the dashboard
  from a static template. Do this after #4, so the split has a safety net.

### 10. Deferred dependency majors — *Minor*
- Held back on purpose: SQLAlchemy 2.1, openai 3.x, redis 8.x. Dependabot is
  configured to skip majors. Starlette's test client now warns that `httpx`
  support is deprecated in favor of `httpx2`.
- **Plan:** upgrade one at a time, using the same method as the Sept 2026
  FastAPI/Starlette upgrade: full suite, recorded-response diff, live
  gunicorn smoke.

### 11. Host-specific paths and sibling-repo coupling in scripts — *Minor*
- `scripts/provision_integrations.sh` hard-codes `/home/the-eye-beta/...`.
  `start_all_native.sh` and `watchdog_all.sh` drive `../TheEyeBetaLocal`. The
  tunnel config pins a credentials path.
- **Plan:** read paths from environment variables with the current values as
  defaults, and keep cross-repo orchestration out of this repo long term.

### 12. Tooling gaps — *Minor*
- No autoformatter (ruff `E501` is ignored to avoid a whole-repo reformat) and
  no static type checking.
- The `deploy` job waits only on `test`, not on `integration`/`lint`/`audit`.
- **Plan:** adopt `ruff format` in one isolated commit, add `mypy` on
  `app/auth` and `app/core` first, and make `deploy` depend on all checks.

## Resolved in the 2026-09 cleanup

| Item | Resolution |
|---|---|
| 28 known advisories (Starlette, PyJWT, python-dotenv) | Upgraded; `pip-audit` clean and enforced in CI |
| FastAPI upgrade would have broken every route (metrics middleware) | Upgraded `prometheus-fastapi-instrumentator` alongside it |
| New FastAPI would leak server file paths in 422 bodies | Handler returns `str(exc.errors())`, identical to the old format |
| Admin gateway duplicated `X-Request-ID` | Header keys normalized; regression test |
| Advisor chat returned 500 without OpenAI | Fallback returns a string; regression test |
| `db_security.sql` role could not run the API | Rewritten least-privilege `api_service`, verified on Postgres 16 |
| Local-dev bootstrap silently produced a production `.env` | `--environment` is required |
| Production CORS origins applied in every environment | Production only |
| JWT keys allowed down to 24 bytes | ≥ 32 bytes (RFC 7518) |
| Stale/contradictory docs (`agent.md`, `OTHEREND_TEST.md`, missing routes) | Removed or replaced; API reference complete |
| No lint, no license, no dependency automation | ruff, pip-audit, Dependabot, CODEOWNERS, LICENSE |
| Grafana `changeme` default password | Compose refuses to start without `GRAFANA_ADMIN_PASSWORD` |
