# Agent notes — TheEyeBetaDataAPI

Operational knowledge that isn't obvious from reading the code. See `README.md`
for architecture, setup, and API reference.

**Read the `readme-sync` skill** (`.claude/skills/readme-sync/SKILL.md` or
`.agents/skills/readme-sync/SKILL.md` — identical content, tool-agnostic) before
finishing any task that adds/changes a route, scope, env var, script, or
service/deploy convention. `README.md` and `docs/API_REFERENCE.md` drift from
the code fast if updating them isn't a deliberate step of the change itself.

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
