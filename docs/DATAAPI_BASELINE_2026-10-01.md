# DataAPI Production Baseline — 2026-10-01

Repository-side baseline of TheEyeBetaDataAPI against TheEyeBetaProd. This
records what was verified in code and CI, and what only the production host can
prove. Nothing here was merged, deployed, rotated or applied to a live system.

**Update (same day): operator decisions recorded.**

- **DEBT-01, resolved architecturally.** The decision is
  `admin.theeyebeta.store → 127.0.0.1:8080`, the TheEyeBetaAdminFrontend static
  terminal host. `dataapiprod.theeyebeta.store/admin/*` goes through the DataAPI
  gateway to Prod admin-service on `127.0.0.1:7200`, which is never a tunnel
  origin.
  - `deploy/cloudflared-config.yml` now holds this target. It is **not
    applied**, and the tunnel scripts refuse to apply it until
    `http://127.0.0.1:8080/healthz` is healthy.
  - Host activation waits for the AdminFrontend audit, which must give `:8080`
    a production unit, and for Prod updating its C7 declaration.
- **DEBT-02, resolved: PRIVATE.** The repository is proprietary infrastructure.
  The GitHub visibility change is an operator action and was deliberately not
  made from this session.
- Host verification remains deferred (section 16).

## 1. Revisions

| | SHA |
|---|---|
| Base (`main`) | `fe7023bffaaf06e7bcd7054fba27605fbfeedfd1` |
| Start of this baseline (branch tip when started) | `7849d0e` (10 commits ahead of base) |
| Code baseline (last code/doc commit before this report) | `1c9ace4afe56ac56e1b5ce8113a36f2e09672946` |
| Final branch tip | the commit that adds this file; see PR TheEyeBeta/TheEyeBetaDataAPI#23 |
| Branch | `claude/zen-rubin-6dhimj` |
| TheEyeBetaProd | `47d042f8c8b36308b07a88ad4d00050015772739` (`contracts/prod/PROD_SHA`), Alembic head `0102_news_dedupe_uniq` |
| TheEyeBetaAdminFrontend | `b75fd2aef4097c2d633eb388a7426b38a14e73cd` |
| AI-Financial-Advisor (Lens) | `d97ee7cfa31a121b571e8c1b1ceff79152945d27` |
| TheEyeBetaLocal | `b601f312e1622427a2cd04aca16fc11eba6804f5` |

## 2. Size of change

- Commits `fe7023b..1c9ace4`: 23 (13 in this baseline, `7849d0e..1c9ace4`).
- `7849d0e..1c9ace4`: 108 files, +6,495 / −1,209 (includes one mechanical
  `ruff format` commit, `a3f4f7f`, listed in `.git-blame-ignore-revs`).

| Commit | Scope |
|---|---|
| `2927f7d` | DB role aligned with Prod `api_readonly`; Prod schema snapshot in tests |
| `135dec5` | Admin gateway pinned to Prod routes; path re-targeting closed |
| `8798490` | `prod-contract` CI job |
| `08274c4` | Tunnel ownership, approval gate, routing table |
| `b60975a` | Refresh family revocation, client binding; `iss`/`aud` enforced |
| `ee35d42` | Error leakage |
| `096eee0` | `deploy.sh` fail-closed, tested SHA, DB health, rollback |
| `47cf135` | `/metrics` restricted |
| `b880af5` | mypy-clean `app/`; test isolation for per-IP rate limits |
| `0028210` | Admin E2E smoke, docs/OpenAPI drift, Prometheus rule tests |
| `a3f4f7f` | `ruff format` (mechanical) |
| `1ef20d3` | CI gates |
| `1c9ace4` | Tech-debt restructure |

## 3. Security changes

| Change | Before | After | Test |
|---|---|---|---|
| Refresh reuse | 401, family stayed valid | Family revoked (`replaced_by` chain) | `tests/test_refresh_tokens.py`, `tests/integration/test_iam_postgres.py` |
| Refresh authentication | Token alone was enough | Issuing client's HTTP Basic required; client/subject mismatch revokes family | same |
| JWT `iss`/`aud` | Optional (default `false`) | Required by default | `tests/test_jwt_hardening.py` |
| Admin gateway methods | PUT/PATCH/DELETE allowed on 16 families Prod does not implement | Exactly Prod's methods minus `POST /admin/users`, `GET /admin/health`, `GET /admin/dataapi/{path}` | `tests/test_admin_gateway_contract.py` |
| Gateway path handling | Encoded `?`/`#`/traversal could re-target upstream | `%`, `\`, control chars, empty/`.`/`..` segments refused; path percent-encoded | `tests/test_admin_gateway_proxy.py` |
| Named-query DB error | Returned driver text (SQL + params) | Generic message, logged server-side | `tests/test_error_handling.py` |
| 422 body | Echoed submitted `input` (could be a secret) | `type`/`loc`/`msg` only | same |
| `/metrics` | Reachable via the public tunnel | Direct scrapes from `METRICS_ALLOWED_NETWORKS` only | `tests/test_metrics_access.py` |
| Tunnel config | Watchdog pushed config automatically | Alert-only; scripts need `TUNNEL_CHANGE_APPROVED=yes` | `tests/test_tunnel_routing.py` |
| Deploy | Silent tmux fallback; deployed `origin/main`; health ignored DB; no rollback | Fail-closed; tested SHA; `database:true`; rollback | `tests/test_deploy_script.py` |
| Secret scanning | None | gitleaks over full history in CI | `secrets` job |

## 4. DB role model

- `api_readonly` (NOLOGIN) is owned by TheEyeBetaProd (migration 0092). It
  grants SELECT on the 8 `theeyebeta.dataapi_*` policy tables. DataAPI never
  alters or drops it.
- `api_service` (LOGIN) is owned by DataAPI (`deploy/db_security.sql`). Its
  attributes: NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION,
  NOBYPASSRLS. Its access:
  - membership in `api_readonly`;
  - USAGE on `theeyebeta`, plus an explicit SELECT allowlist (absent tables
    are skipped);
  - column-scoped INSERT/UPDATE on `iam` tables, and no DELETE.
- The script raises if `api_readonly` is missing.
- Proven on Postgres 16 (`tests/integration`, as `api_service`): no writes or
  DDL on `theeyebeta`; no writes to policy tables; an unlisted table is
  invisible; `SET ROLE postgres`, `ALTER ROLE … SUPERUSER` and `CREATE ROLE`
  are denied; it is not an owner or superuser; policy tables are readable only
  through `api_readonly`.
- Not proven: which role production actually connects as (DEBT-05).

## 5. Prod schema contract

- Source: the snapshot is produced by `scripts/prod_contract_snapshot.sh`,
  which applies Prod's real migrations to `head` at `PROD_SHA` with
  TimescaleDB, then `pg_dump`s only the objects DataAPI reads.
- What the snapshot contains (`contracts/prod/theeyebeta_schema.sql`): it is
  deterministic and loads on plain Postgres 16. Prod's `api_readonly` grants
  are in `api_readonly_grants.sql`.
- `latest_snapshots` is a table maintained by a Prod worker, outside Alembic.
  It is modelled from Prod's own test DDL (DEBT-16).
- Result: the `prod-contract` job passes 70 tests as `api_service`. They cover:
  - every Lens route Lens is scoped for;
  - every other data route, using the bridge client's scopes;
  - 9 admin named queries;
  - 10 host-only routes, against declared assumptions only;
  - the Admin E2E smoke script, including the bridge data hop.
- Defect found and fixed: the generic rows API filtered by a
  `public_ticker_map.symbol` column that Prod does not have.
- Host-only objects not created by any Prod migration (DEBT-04):
  - `fund_balance_q`, `fund_cashflow_q`, `fund_income_q`;
  - `ind_risk_daily`, `ind_valuation_daily`;
  - `price_ticks`, `provider_sync_runs`, `returns_snapshot_daily`;
  - `ticker_news`, `trask_audit_events_archive`;
  - `latest_snapshots.eps`.

## 6. IAM consumers verified (in each consumer's code)

| Consumer | Client | Token use | Refresh | `iss`/`aud` compatible |
|---|---|---|---|---|
| Lens `dataapi_client.py` | `ai-advisor-production` | `/service-token`, `requested_scopes: []`, reads `expires_minutes` | No | Yes (opaque token) |
| Lens `routes/admin.py` | `DATAAPI_ADMIN_CLIENT_ID` (falls back to the main client) | `/service-token` | No | Yes |
| Prod admin-service `api/dataapi.py` | `theeyebeta-prod-admin` (7 scopes) | `/service-token` | No | Yes |
| TheEyeBetaLocal `dataapi_client.py` | `DATAAPI_CLIENT_ID` (`trade-engine`) | `/service-token`, `[]` | No | Yes |

No scope or client was removed. Lens calls 4 routes that need `analytics:read`,
which its recorded IAM row lacks. Those calls return 403, and the behaviour is
pinned in tests (DEBT-06).

## 7. Admin gateway

- Prod admin-service's HTTP routes form 34 path families
  (`contracts/prod/admin_route_families.json`, generated by importing Prod's
  app at `PROD_SHA`).
- The DataAPI manifest allows exactly those families and methods except the
  three deliberate denials listed in section 3, and
  `tests/test_admin_gateway_contract.py` fails on any difference. Prod's
  WebSocket `/admin/events/stream` is not proxied, and the old `events` entry
  was removed. AdminFrontend uses none of the denied routes.
- The gateway fails closed in four cases: disabled → 503; unlisted family or
  method → 404; mutations need `X-Idempotency-Key`; oversized bodies → 413.
- Routing `admin.theeyebeta.store → :7200`, as Prod still declares, would
  publish admin-service in full, including the denied routes. The DEBT-01
  decision avoids this: the admin hostname serves the static page from `:8080`,
  and admin-service is reachable only through the gateway.

## 8. Lens contract

Every Lens-scoped call returns 200 on Prod's schema with the fields Lens reads:
quotes, symbol search, context, advisor context, market news, price history,
corporate actions and reference data. Token responses carry `access_token` and
`expires_minutes`, with no `refresh_token`. The scope-gap calls return 403
(DEBT-06).

## 9. Admin contract

- The terminal sends all API calls to `dataapiprod.theeyebeta.store`
  (AdminFrontend `src/lib/runtime.ts`). Admin-service's data hop uses the
  bridge token against `/api/v1/*`, and those routes pass on Prod's schema.
- Post-deploy E2E: `scripts/e2e_admin_smoke.py` needs no secrets. It checks:
  - DB health;
  - that the gateway reaches admin-service, which returns 401;
  - that denied routes stay closed;
  - that encoded traversal is refused.

  With bridge credentials it also runs the data hop. It is tested in the unit
  suite (mocked admin-service) and the contract suite (Prod schema), and it runs
  in the `deploy` job.

## 10. Cloudflare ownership and routing

Canonical table: `docs/OWNERSHIP.md` section 2.

| Hostname | Origin | Status |
|---|---|---|
| `dataapiprod`/`dataapi` | `:7000` | Code |
| `admin` | `:8080` (AdminFrontend static terminal host) | **DEBT-01 resolved architecturally**; activation pending the AdminFrontend `:8080` unit; live value unverified |
| `api` | `:8000` | Owned by Local; host-verify |
| (none) | `:7200` admin-service | Never a tunnel origin; reached only through the DataAPI gateway |

- AdminFrontend's `:8080` `server.mjs` has no service unit in any repo yet.
  Its `/healthz` is the activation check.
- Prod's C7 still declares `admin → :7200` and must be updated to match before
  activation.
- No Cloudflare or host configuration was changed.
- Tunnel changes are operator-only. `sync_tunnel.sh` and `fix_tunnel.sh` need
  `TUNNEL_CHANGE_APPROVED=yes`, and even then exit 3 while `:8080` is
  unhealthy. The watchdog and start scripts never touch the tunnel.

## 11. Monitoring

- `deploy/prometheus/rules/dataapi_auth.yml` defines 3 rules. They pass
  `promtool` 3.5.0 and `tests/test_prometheus_rules.py`: metrics are exported,
  status codes are ungrouped, and handlers exist.
- Prod's `infra/prometheus/prometheus.yml` has no DataAPI scrape job and does
  not load these rules (DEBT-13). The alerts are **not live** anywhere this
  review can see.

## 12. CI results (PR TheEyeBeta/TheEyeBetaDataAPI#23)

Run 36895991062 on `1c9ace4` (event `pull_request`):

| Job | Gate | Result |
|---|---|---|
| `test` | Unit + docs/OpenAPI drift + tunnel/deploy/CI-gate/Prometheus tests | success |
| `integration` | IAM SQL, grants, privilege boundaries, refresh families (Postgres 16) | success |
| `prod-contract` | HTTP API on Prod schema as `api_service` | success |
| `lint` | `ruff check`, `ruff format --check`, `bash -n`, `promtool` | success |
| `typecheck` | `mypy app/` | success |
| `audit` | `pip-audit -r requirements-dev.txt` | success |
| `secrets` | gitleaks, full history + tree | success |
| `deploy` | Needs all of the above; `main` push only | skipped (PR) — correct |

The commit adding this report changes documentation only; its run is on the PR.

## 13. Local test results (Python 3.12, Postgres 16 scratch server)

| Suite | Result |
|---|---|
| `pytest` with `TEST_POSTGRES_URL` | 390 passed, 70 skipped |
| `pytest tests/contract` with `PROD_CONTRACT=1` | 70 passed |
| `ruff check .` / `ruff format --check .` | clean / 160 files formatted |
| `mypy` | no issues in 85 files |
| `pip-audit -r requirements-dev.txt` | no known vulnerabilities |
| gitleaks 8.30.0 (history: 79 commits scanned; tree) | no leaks |
| `promtool check rules` / `check config --syntax-only` | 3 rules OK / OK |

The 70 skipped tests in the first row are exactly the `tests/contract` suite,
which skips without `PROD_CONTRACT=1`; it runs in the second row and in its own
CI job. Without `TEST_POSTGRES_URL`, the 41 `tests/integration` tests also
skip; they run in the `integration` job.

## 14. Dependency audit

`pip-audit` is clean for runtime and dev pins, and it now gates CI. Deferred
majors (SQLAlchemy 2.1, openai 3.x, redis 8.x) are tracked as DEBT-10.

## 15. Skipped checks

- **Live host checks.** Not run: no access, and not permitted. This covers
  grants, `.env`, tunnel ingress, unit state and Prometheus.
- **Regenerating the Prod snapshot in CI.** Not run, because it needs
  TimescaleDB and a Prod checkout. Regenerate it locally with
  `scripts/prod_contract_snapshot.sh`; tests catch drift against the committed
  snapshot only.
- **shellcheck.** Not added; CI runs `bash -n` only.
- **Type checking of `tests/` and `scripts/`.** Not done; only `app/` is
  checked.

## 16. Host verification required (read-only)

| # | Check |
|---|---|
| 1 | Live ingress for all four hostnames; before activating DEBT-01: a `:8080` production unit and `curl -sf http://127.0.0.1:8080/healthz` |
| 2 | `DATABASE_URL` login role; `\du api_service`; `\dp theeyebeta.*`, `\dp iam.*` vs `db_security.sql` (DEBT-05) |
| 3 | `\d` of the 10 host-only tables and `latest_snapshots` vs `contracts/prod/host_only_assumed.sql` (DEBT-04, DEBT-16) |
| 4 | Live scopes of `ai-advisor-production` and `theeyebeta-prod-admin` (DEBT-06) |
| 5 | Host `.env`: `JWT_REQUIRE_ISS_AUD` not pinned `false`; `ADMIN_GATEWAY_ENABLED=true`; `METRICS_ALLOWED_NETWORKS` covers the local scraper (DEBT-07, DEBT-17) |
| 6 | Runner: `XDG_RUNTIME_DIR=/run/user/1000` matches the unit's user; `systemctl --user show theeyebeta-dataapi` resolves (DEBT-17) |
| 7 | Prometheus: whether anything scrapes `:7000/metrics` and loads `dataapi_auth.yml` (DEBT-13) |

## 17. Remaining P2/P3

DEBT-03, 07, 08, 09, 10, 12, 13, 14, 16, 17, 18 — see `docs/TECH_DEBT.md`.

## 18. Decisions

| Item | Status |
|---|---|
| DEBT-02 repository visibility | **Resolved: PRIVATE.** GitHub setting is pending, and is an operator action |
| DEBT-01 admin hostname origin | **Resolved: `:8080`** (architecture). Activation pending the AdminFrontend audit and Prod C7 |
| LICENSE / ownership | Open: confirm that "TheEyeBeta" is the right legal entity for the copyright notice |
| DEBT-06 Lens `analytics:read` | Open: grant the scope to Lens, or remove the calls in Lens |

## 19. Verdict

**READY FOR ADMIN AUDIT.** The repository-side baseline is complete.

- The two P0 decisions are made and recorded.
- What remains depends on others or needs host evidence:
  - the AdminFrontend `:8080` unit and activation;
  - Prod C7;
  - the GitHub visibility setting;
  - the host checks in section 16.
