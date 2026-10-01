# TheEyeBetaDataAPI Production Runbook

## 1) Baseline

- Private PostgreSQL; never expose DB publicly.
- API service is the only DB consumer.
- Public ingress is Cloudflare Tunnel -> `http://127.0.0.1:7000`.
- TLS terminates at Cloudflare edge.

## 2) Required environment

Set `.env` from `.env.example` and configure:

- Core:
  - `DATABASE_URL`
  - `JWT_SECRET`, `JWT_ISSUER`, `JWT_AUDIENCE`
  - `SERVICE_CLIENT_AUTH_MODE=database`
  - DB-backed client credentials in `iam.service_clients` / `iam.service_client_secrets`
  - `TRUSTED_HOSTS`, `CORS_ORIGINS`, `TRUST_PROXY_HEADERS=true`
- User JWT mode (pick one):
  - Symmetric: `USER_JWT_SECRET` (+ `USER_JWT_ALGORITHM`)
  - OIDC/JWKS: `USER_JWT_JWKS_URL`, `USER_JWT_ISSUER`, `USER_JWT_AUDIENCE`, `USER_JWT_ALGORITHMS`
- Optional multi-instance rate limiting:
  - `REDIS_URL`, `RATE_LIMIT_REDIS_PREFIX`
- Optional service mTLS mode:
  - `SERVICE_MTLS_ENABLED=true`
  - `SERVICE_MTLS_SUBJECTS_JSON`
  - `SERVICE_MTLS_HEADER_CLIENT_ID`
  - `SERVICE_MTLS_HEADER_SUBJECT`
- DataAPI policy and administrative gateway:
  - apply TheEyeProd Alembic migration `0092_dataapi_policy_control` before deploying this API;
  - seed an active internal/Lens tenant, application, membership, policy version, and
    `LENS_ACCESS` entitlement through the proxied `admin-service` SQL console. It requires
    MASTER_ADMIN MFA, `X-Confirm: true`, a reason, and an idempotency key; its admin-service
    transaction appends the canonical audit event;
  - set `POLICY_ENFORCEMENT_ENABLED=true`, `ADMIN_GATEWAY_ENABLED=true`, and loopback-only
    `ADMIN_SERVICE_URL=http://127.0.0.1:7200`;
  - run DataAPI as the least-privilege `api_service` role from `deploy/db_security.sql`
    (read-only on `theeyebeta`; column-scoped `iam` writes for auth bookkeeping and account
    lifecycle only). `admin-service` commits administrator-authorized policy mutations and
    audit rows using its own privileged connection.

## 3) One-time host setup

The app runs natively on the machine — no Docker required.

**1. Generate your `.env`:**

```bash
cd /path/to/TheEyeBetaDataAPI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap_local_env.py \
  --environment production \
  --database-url "postgresql+psycopg://api_service:REPLACE_ME@127.0.0.1:5432/TheEyeBeta2025Live"
```

If running behind Cloudflare Tunnel, add `--trust-proxy-headers`.

Connect as the least-privilege `api_service` role, never `postgres`. Create it
once (as a DB owner, after the `deploy/iam_*.sql` files) with
`psql -f deploy/db_security.sql`, then set its password out of band.

`.env` holds every runtime secret (`JWT_SECRET`, `DATABASE_URL`, `SERVICE_CLIENTS_JSON`,
`ADMIN_ACCOUNT_APPROVAL_CODE`, ...) in one file. `bootstrap_local_env.py` and
`rotate_secrets.py` both write it (and any `.env.bak.*` backup) with mode `600`
(owner read/write only) automatically. If you ever hand-edit or copy `.env` by
some other means, re-run `chmod 600 .env` — a `--user` systemd unit like
`theeyebeta-dataapi` always runs as you, so 600 never breaks it. `.env.bak.*`
is git-ignored; never `git add -f` one.

**2. Install as a background service (starts on boot, restarts on crash):**

```bash
sudo bash scripts/install_service.sh
```

This installs a **`--user`** systemd unit (`~/.config/systemd/user/theeyebeta-dataapi.service`),
not a system one — `sudo` is only used to enable linger for your user so the
service survives reboots without an active login session. Every command that
manages it afterward drops the `sudo` (see Service management below); plain
`sudo systemctl ... theeyebeta-dataapi` will report "Unit could not be found."

Logs are available via journald: `journalctl --user -u theeyebeta-dataapi -f`

**3. Install the GitHub Actions self-hosted runner (auto-deploys on push to `main`):**

GitHub Actions runners are registered per-repo (this account has no org-level runner
pool), and this machine also hosts a separate runner for `TheEyeBetaProd`. **Use a
dedicated directory for this repo's runner — never reuse another repo's runner
directory.** Reusing one re-registers it against this repo and breaks the other
repo's deploys.

```bash
mkdir -p ~/actions-runner-dataapi && cd ~/actions-runner-dataapi
```

Go to: **GitHub → TheEyeBetaDataAPI repo Settings → Actions → Runners → New self-hosted runner → Linux**,
and run the download + `./config.sh` commands GitHub provides from inside
`~/actions-runner-dataapi`. Then:

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

Verify registration succeeded before relying on it: `~/actions-runner-dataapi/.runner`
should exist and its `gitHubUrl` should point at `TheEyeBetaDataAPI`, and
`gh api repos/TheEyeBeta/TheEyeBetaDataAPI/actions/runners` should list it. Without
a registered runner, every push to `main` queues the `deploy` job forever and it
silently never runs — there's no error, just an indefinitely queued job in the
Actions tab.

After this, every push to `main` that passes CI will automatically pull the latest code, update dependencies, restart the service, and verify `/health`.

### Service management

`theeyebeta-dataapi` runs as a **`--user`** systemd unit, not a system one —
no `sudo` for any of these (run as the same user the service was installed
for). `server.sh` is a dev-only helper whose PID file doesn't track this
service; it will report "Not running" even when the API is up.

```bash
# Restart
systemctl --user restart theeyebeta-dataapi

# Stop
systemctl --user stop theeyebeta-dataapi

# Start
systemctl --user start theeyebeta-dataapi

# Status
systemctl --user status theeyebeta-dataapi

# Logs
journalctl --user -u theeyebeta-dataapi -f
```

`scripts/run_production.sh` runs the same gunicorn command in the foreground
(the unit's `ExecStart` path); use it only for debugging outside systemd.

## 4) Cloudflare Tunnel

Ingress config: [`deploy/cloudflared-config.yml`](../deploy/cloudflared-config.yml).
The tunnel is shared with TheEyeBetaProd (admin hostname) and TheEyeBetaLocal
(`api.*`); the routing table and owners are in [`OWNERSHIP.md`](OWNERSHIP.md).

Tunnel changes are operator actions only. `scripts/fix_tunnel.sh` (installs
`/etc/cloudflared/config.yml`) and `scripts/sync_tunnel.sh` (replaces the
Cloudflare remote ingress) print their plan and exit 2 unless
`TUNNEL_CHANGE_APPROVED=yes` is set. `start_all_native.sh` and
`watchdog_all.sh` never touch the tunnel; the watchdog only logs an ALERT when
the public health probe fails. Resolve DEBT-01 (`admin.theeyebeta.store`
origin) before approving any change. Full guide: [`TUNNEL_RUNBOOK.md`](TUNNEL_RUNBOOK.md).

## 5) Verification checklist

Local process:

```bash
ss -ltnp | rg ':7000'
curl -s http://127.0.0.1:7000/health
```

Product consumers to verify (release gates): **Lens** (`ai-advisor-production`) and
**TheEyeBetaAdmin Frontend** (gateway + `theeyebeta-prod-admin`). See
[`IAM_CONSUMER_INVENTORY.md`](IAM_CONSUMER_INVENTORY.md). `vi-app` is template/legacy only.

Lens / advisor service credentials:

```bash
TOKEN=$(curl -s -X POST "http://127.0.0.1:7000/api/v1/auth/service-token" \
  -u "ai-advisor-production:<SERVICE_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["market:read","advisor:read","signals:read","symbols:read"]}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
```

Capability checks:

```bash
curl -s "http://127.0.0.1:7000/api/v1/market-data/quotes?symbols=AAPL,MSFT" \
  -H "Authorization: Bearer ${TOKEN}"

curl -s "http://127.0.0.1:7000/api/v1/advisor/context?ticker=AAPL" \
  -H "Authorization: Bearer ${TOKEN}"
```

Admin Frontend gateway (unauthenticated — expect 401 when up):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7000/admin/auth/me
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7000/admin/terminal-data/modules
```

Admin data-bridge client (server-side, not the browser):

```bash
ADMIN_TOKEN=$(curl -s -X POST "http://127.0.0.1:7000/api/v1/auth/service-token" \
  -u "theeyebeta-prod-admin:<SERVICE_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["market:read","symbols:read"]}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

curl -s "http://127.0.0.1:7000/api/v1/market-data/quotes?symbols=AAPL" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

Remote smoke:

```bash
API_BASE_URL="https://dataapiprod.theeyebeta.store" \
SERVICE_CLIENT_ID="ai-advisor-production" \
SERVICE_CLIENT_SECRET="<SERVICE_SECRET>" \
bash scripts/verify_remote_access.sh
```

## 6) Security operations

- Provision or rotate DB-backed service credentials:
  - `python scripts/provision_db_service_client.py --client-id <id> --display-name \"...\" --app-type <type> --allow-existing`
- Rotate JWT signing secrets with a verify overlap (no forced logouts):
  - Follow [`SECRET_ROTATION_RUNBOOK.md`](SECRET_ROTATION_RUNBOOK.md)
  - Or `python scripts/rotate_secrets.py` then restart, wait ≥ `SERVICE_TOKEN_EXPIRES_MINUTES`, clear `*_PREVIOUS`
- Keep service scopes minimal per consumer.
- Use distinct principals per product consumer (Lens, Admin Frontend / admin-service).
- Require `X-Idempotency-Key` for `/admin/*` write routes.
- Enable JWKS and mTLS in production when identity provider and proxy are ready.
- Remove direct public admin ingress only after DataAPI gateway smoke tests prove that MFA, RBAC,
  confirmation, SQL protection, and audit correlation are preserved.
- Consumer inventory for TTL / grace planning: [`IAM_CONSUMER_INVENTORY.md`](IAM_CONSUMER_INVENTORY.md).
- Ops hardening (firewall, Prometheus alert sketches, rotation cadence, iam backups):
  [`OPS_HARDENING.md`](OPS_HARDENING.md).

## 7) Optional production hardening toggles

- `iss`/`aud` are required on every JWT decode by default
  (`JWT_REQUIRE_ISS_AUD=true`). Only set `false` as a rollback; check the host
  `.env` does not still pin `false`.
- OIDC/JWKS user JWT validation:
  - `USER_JWT_JWKS_URL`, `USER_JWT_ISSUER`, `USER_JWT_AUDIENCE`, `USER_JWT_ALGORITHMS`
- Redis rate limiting backend:
  - `REDIS_URL`, `RATE_LIMIT_REDIS_PREFIX`
- mTLS service principal flow:
  - `SERVICE_MTLS_ENABLED=true`
  - `SERVICE_MTLS_SUBJECTS_JSON`
  - `TRUST_PROXY_HEADERS=true`

Consumer inventory for rotation / claim-enforcement planning: [`docs/IAM_CONSUMER_INVENTORY.md`](IAM_CONSUMER_INVENTORY.md).

Additive IAM SQL (apply on host Postgres before enabling the matching feature flags):

- `deploy/iam_refresh_tokens.sql` — refresh tokens + `short_lived_tokens_enabled`
- `deploy/iam_auth_audit.sql` — `iam.auth_audit_log` + `least_privilege_default` column

New DB-backed clients can be provisioned narrow with:

```bash
python scripts/provision_db_service_client.py \
  --client-id example-reader \
  --display-name "Example reader" \
  --app-type vi-backend \
  --least-privilege \
  --scope market:read
```
