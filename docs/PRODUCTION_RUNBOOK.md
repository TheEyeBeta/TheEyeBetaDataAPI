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
  - keep DataAPI's database role read-only; `admin-service` commits administrator-authorized
    policy mutations and audit rows using its existing privileged connection.

## 3) Start service

```bash
cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
source .venv/bin/activate
bash scripts/run_production.sh
```

## 4) Cloudflare Tunnel config

```yaml
ingress:
  - hostname: api.theeyebeta.store
    service: http://127.0.0.1:7000
  - hostname: dataapi.theeyebeta.store
    service: http://127.0.0.1:7000
  - service: http_status:404
```

## 5) Verification checklist

Local process:

```bash
ss -ltnp | rg ':7000'
curl -s http://127.0.0.1:7000/health
```

Service credentials flow:

```bash
TOKEN=$(curl -s -X POST "http://127.0.0.1:7000/api/v1/auth/service-token" \
  -u "vi-app:<SERVICE_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["market:read","advisor:read"]}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
```

Capability checks:

```bash
curl -s "http://127.0.0.1:7000/api/v1/market-data/quotes?symbols=AAPL,MSFT" \
  -H "Authorization: Bearer ${TOKEN}"

curl -s "http://127.0.0.1:7000/api/v1/advisor/context?ticker=AAPL" \
  -H "Authorization: Bearer ${TOKEN}"
```

Read-only table API check:

```bash
curl -s "http://127.0.0.1:7000/api/v1/data/tables/latest_snapshots/rows?symbol=AAPL&limit=1" \
  -H "Authorization: Bearer ${TOKEN}"
```

Remote smoke:

```bash
API_BASE_URL="https://api.theeyebeta.store" \
SERVICE_CLIENT_ID="vi-app" \
SERVICE_CLIENT_SECRET="<SERVICE_SECRET>" \
bash scripts/verify_remote_access.sh
```

## 6) Security operations

- Provision or rotate DB-backed service credentials:
  - `python scripts/provision_db_service_client.py --client-id <id> --display-name \"...\" --app-type <type> --allow-existing`
- Rotate JWT secrets separately (app token signing secrets in `.env`):
  - `python scripts/rotate_secrets.py`
- Keep service scopes minimal per consumer.
- Use distinct principals per consumer (mobile backend, VI, trade engine, admin/internal).
- Require `Idempotency-Key` for write routes.
- Enable JWKS and mTLS in production when identity provider and proxy are ready.
- Remove direct public admin ingress only after DataAPI gateway smoke tests prove that MFA, RBAC,
  confirmation, SQL protection, and audit correlation are preserved.
