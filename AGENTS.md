# Agent notes — TheEyeBetaDataAPI

Operational knowledge that isn't obvious from reading the code. See `README.md`
for architecture, setup, and API reference.

**Read the `readme-sync` skill** (`.claude/skills/readme-sync/SKILL.md` or
`.agents/skills/readme-sync/SKILL.md` — identical content, tool-agnostic) before
finishing any task that adds/changes a route, scope, env var, script, or
service/deploy convention. `README.md` and `docs/API_REFERENCE.md` drift from
the code fast if updating them isn't a deliberate step of the change itself.

## Production consumers (release gates)

When changing auth, scopes, or deploy behavior, the products that must keep
working are:

1. **Lens / AI Financial Advisor** — IAM client `ai-advisor-production` (service token → `/api/v1/*`).
2. **TheEyeBetaAdmin Frontend** — browser `/admin/*` gateway → Prod admin-service; data via `theeyebeta-prod-admin`.

`vi-app` is a legacy/template client only — not a product release gate. Details:
`docs/IAM_CONSUMER_INVENTORY.md`.

## This is a separate system from TheEyeBetaProd

`TheEyeBetaDataAPI` (this repo) and `TheEyeBetaProd` (the trading system, at
`../TheEyeBetaProd`) are independent repos with independent credentials and
independent security models. Do not carry a convention or a secret value from
one into the other without re-deriving whether it actually applies:

- Prod's `TB_PROD_MIGRATION_CODEWORD` (`ARTEMIS` on this laptop) gates
  `tb db migrate --prod` in Prod's Alembic-based migration tooling. **This
  repo has no migrations and no such tooling** — nothing to gate with it.
- This repo's own destructive action (deactivating an `iam.users` account) is
  gated by a *different*, DataAPI-local secret: `ADMIN_ACCOUNT_APPROVAL_CODE`
  (see below). Never set it to the same value as Prod's codeword.
- Prod reaches its production Postgres over Tailscale from a laptop
  (`scripts/laptop_db.sh`). This repo's `DATABASE_URL` points at
  `127.0.0.1:5432` — the database is local to the same box the API runs on.
  There is no Tailscale-DB-access story here to replicate.

## Restarting the service

```
systemctl --user restart theeyebeta-dataapi
```

This is a **user-level** systemd unit (`~/.config/systemd/user/theeyebeta-dataapi.service`),
not a system one. `sudo systemctl restart theeyebeta-dataapi` (as written in
some older docs/scripts) fails with "Unit could not be found." Verify with
`curl -s http://127.0.0.1:7000/health` after restarting.

`server.sh`/`./server.sh status` is a separate nohup-based path whose PID file
does not track the gunicorn process systemd starts — it will report "Not
running" even when the API is up. Don't trust it for status checks.

## Hosted terminal ingress

`admin.theeyebeta.store` is the public entrypoint for The Eye hosted terminal,
not a direct public admin-service origin. The canonical tunnel config routes it
to loopback port `8080`; the Node terminal host proxies authenticated admin
operations through DataAPI's allowlisted gateway. Do not repoint this hostname
to port `7200` without an explicit rollback decision.

## Runtime secrets (`.env`)

`.env` holds every runtime secret in one file: `JWT_SECRET`, `DATABASE_URL`,
`SERVICE_CLIENTS_JSON`, `ADMIN_ACCOUNT_APPROVAL_CODE`, etc. It must stay mode
`600` (owner read/write only) — the service runs as a `--user` unit, always as
you, so this never breaks anything.

- `scripts/bootstrap_local_env.py` and `scripts/rotate_secrets.py` both
  `chmod 600` `.env` and any `.env.bak.*` backup automatically. If you ever
  hand-create or copy `.env` by some other means, `chmod 600 .env` yourself.
- `.env.bak.*` is git-ignored. Never `git add -f` one — a rotation or forced
  bootstrap run followed by a broad `git add -A`/`git add .` is exactly how a
  full secrets dump ends up in history.

## Admin account lifecycle (`admin:write` scope)

`POST /api/v1/admin/accounts` and `DELETE /api/v1/admin/accounts/{user_uuid}`
manage `iam.users` rows (soft-delete only — `is_active=false`, which triggers
automatic API-key revocation via `iam.revoke_user_keys_on_disable`; nothing is
hard-deleted). Both require the `admin:write` scope (distinct from the
pre-existing read-only `admin:read`).

Deletion additionally requires a valid `ADMIN_ACCOUNT_APPROVAL_CODE`,
checked fail-closed (`app/auth/account_approval.py`): if the env var is unset,
every delete attempt is refused with `403 APPROVAL_REQUIRED`, never silently
allowed. It's compared as UTF-8 bytes via `hmac.compare_digest` — set it in
`.env`, never commit a value.

Deletion is separately capped at **1 request/minute per subject**
(`app/core/subject_rate_limit.py::require_account_delete_rate_limit`), on top
of the general 20/min admin rate limit, since an already-authenticated
`admin:write` caller could otherwise brute-force a short approval code within
the shared limit.

## Tests

`pytest` from the repo root. Rate-limit buckets are process-global module
state (`app/core/subject_rate_limit.py`) keyed by `auth_subject`, which is
fixed per test service-client (e.g. `service:admin-tool`) — `tests/conftest.py`
has an autouse fixture (`_reset_rate_limit_buckets`) that clears them before
every test. If you add a new rate limiter via `_make_rate_limiter`, it's
covered by that reset automatically; no extra wiring needed.

## IAM hardening (in progress)

- Phase 0 inventory: `docs/IAM_CONSUMER_INVENTORY.md`
- Phase 1: JWT algorithm allowlists, `exp`/`iat` required, `JWT_REQUIRE_ISS_AUD`
  grace flag (default false), auth request `extra=forbid`, OpenAPI disabled in
  production. Do not flip `JWT_REQUIRE_ISS_AUD=true` until inventory open
  questions are closed.
- Phase 2: zero-downtime signing rotation via
  `JWT_SIGNING_SECRET_CURRENT`/`PREVIOUS` and `USER_JWT_SECRET_PREVIOUS`.
  Follow `docs/SECRET_ROTATION_RUNBOOK.md`; never clear `PREVIOUS` before one
  full max token TTL.
- Phase 3: refresh tokens are opt-in via
  `iam.service_clients.short_lived_tokens_enabled` (apply
  `deploy/iam_refresh_tokens.sql` first). Default clients unchanged.
- Phase 4: `iam.auth_audit_log` on 403 scope failures; provision with
  `--least-privilege` for **new** clients only (existing scopes untouched).
  Apply `deploy/iam_auth_audit.sql`.
- Phase 5: user API keys require `--expires-days`; backfill with
  `scripts/backfill_user_api_key_expiry.py`; report with
  `scripts/report_expiring_user_api_keys.py`. Expired keys return 401
  `API key expired`.
- Phase 6: see `docs/OPS_HARDENING.md` (firewall, alerts, rotation cadence,
  iam backup coverage). Alert rules:
  `deploy/prometheus/rules/dataapi_auth.yml`.

## Imported ops patterns from TheEyeProd

Source: `../TheEyeProd/AGENTS.md` and `../TheEyeProd/.agents/skills/doc-sync/SKILL.md`
(and Claude mirror). Only generic operational discipline was considered.
DataAPI's existing corrections always win on conflict.

### Imported (adapted)

| Pattern | Source | How it applies here |
|---|---|---|
| **Personal CI before every PR** | TheEyeProd `AGENTS.md` §8 "Personal CI" | Run focused `pytest` locally before relying on Actions. Skill: `.agents/skills/personal-ci/SKILL.md` (mirrored under `.claude/skills/`). |
| **Doc-sync after surface changes** | TheEyeProd `doc-sync` skill | Same intent as existing DataAPI `readme-sync` — keep `README.md` / `docs/API_REFERENCE.md` / `.env.example` current when routes, scopes, env, scripts, or CI change. Do **not** replace `readme-sync` with Prod's path table (`services/`, Alembic, `SERVICES_STATUS.md` do not exist here). |
| **Secrets never committed; mode 600** | TheEyeProd runtime credentials § | Reinforces DataAPI `.env` / `.env.bak.*` rules. Prod's per-unit `.env.<unit>` and sops+age are Prod-only; DataAPI keeps a single repo-root `.env`. |
| **Destructive actions need an approval gate** | TheEyeProd migration approval codeword pattern | Pattern only. DataAPI already gates account delete with `ADMIN_ACCOUNT_APPROVAL_CODE` (fail-closed). Never reuse Prod's `TB_PROD_MIGRATION_CODEWORD`. |
| **CI green ≠ deployed** | TheEyeProd deploy runbook | DataAPI: `test` job green is not enough; self-hosted `deploy` + `/health` must succeed (`scripts/deploy.sh`). |
| **Fail closed / inspect before "fixing" gates** | TheEyeProd prelive-gate notes | When deploy/health fails, inspect journald / runner env before changing gates or rolling back app code. |
| **Never print/copy prod secrets into chat or docs** | TheEyeProd credentials § | Same absolute rule for DataAPI `.env`. |
| **Confirm before mutating production** | TheEyeProd `AGENTS.md` §6 | Read-only checks need no confirmation. Restart, deploy, secret rotation, and live host mutation need explicit user approval first. |
| **Never skip hooks / never force-push** | TheEyeProd `AGENTS.md` §7 | Do not use `--no-verify`; fix the hook. Do not force-push shared branches unless the user explicitly asks. |
| **When in doubt, ask — don't invent live claims** | TheEyeProd `AGENTS.md` §9 + doc-sync | Do not guess ports, tunnel backends, or secret values. Only claim deployed/live with host evidence (`--user` unit + `/health`). |
| **Closing checklist: say what applied** | TheEyeProd `AGENTS.md` §12 | Before done/PR, state whether `readme-sync` / `personal-ci` applied or were N/A — silence is not N/A. |
| **Triage environment before blaming the diff; flakes are bugs** | TheEyeProd `AGENTS.md` §8 / §13.1 | Prefer runner/host/CI-env explanations when failures look environmental. A test that only passes on re-run without a code change must be fixed, not re-run until green. |

### Explicitly excluded (and why)

| Pattern | Why excluded |
|---|---|
| `sudo systemctl` / system-level units | DataAPI unit is `--user` (`theeyebeta-dataapi`). Prod/system conventions conflict; AGENTS.md already documents the trap. |
| `tb` CLI, `uv run`, Alembic, `TB_PROD_MIGRATION_*` | Prod-only tooling; this repo has no migrations/`tb`. |
| Per-unit `.env.<service>` + sops+age | Different secret layout; DataAPI uses one `.env`. |
| Order/trade/OMS/broker, `LIVE_TRADING`, MASTER_ADMIN RBAC | Trading-system domain; not DataAPI. |
| Investment operating-model skill / agent hierarchy | Prod AI trading staff; not applicable. |
| `db-engineer` skill + schema references | Prod schema ownership; DataAPI is a read consumer of `theeyebeta` + local `iam` SQL helpers. |
| architecture-advisor skill | Already available at parent monorepo level if needed; not DataAPI-specific ops. |
| Mac mini CI runner provisioning / Valkey / deploy.yml Tailscale hop lore | Prod CI topology; DataAPI has its own self-hosted runner + `ci.yml` deploy job. |
