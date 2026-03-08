# TheEyeBetaDataAPI

Secure multi-client data access layer between private PostgreSQL and external/internal consumers.

## Architecture model

- Private DB is reachable only by this API service.
- API contracts are domain-oriented and versioned under `/api/v1`.
- Layering is enforced:
  - routes/controllers
  - auth dependencies (principal + scopes)
  - services/use-cases
  - repositories (SQL only)
  - domain models/errors
- Structured API errors are returned for auth, validation, and DB failures.

## Auth model

- User auth:
  - bearer JWT
  - either symmetric secret validation (`USER_JWT_SECRET`) or OIDC/JWKS (`USER_JWT_JWKS_URL`)
- Service auth:
  - client credentials -> scoped bearer token via `POST /api/v1/auth/service-token`
  - optional direct mTLS principal flow (no bearer) via trusted proxy headers:
    - `X-Service-Client-Id`
    - `X-Client-Cert-Subject`
- Scope examples:
  - `market:read`
  - `analytics:read`
  - `trades:write`
  - `admin:*`

## Capability route groups

- `GET /health`
- `POST /api/v1/auth/service-token`
- `GET /api/v1/market-data/quotes`
- `GET /api/v1/symbols/search`
- `GET /api/v1/analytics/snapshots/{ticker}`
- `GET /api/v1/advisor/context` (alias: `GET /api/v1/context`)
- `POST /api/v1/advisor/chat` (alias: `POST /api/v1/chat`)
- `GET /api/v1/signals/latest`
- `GET /api/v1/portfolio/state` (ownership-aware)
- `POST /api/v1/trades/orders` (idempotency key required)
- `GET /api/v1/admin/audit-events`
- `POST /api/v1/internal/jobs/rebuild-indicators`

## Local run

```bash
cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
bash scripts/run_production.sh
```

Default bind: `127.0.0.1:7000`

## Quick verification

```bash
curl -s http://127.0.0.1:7000/health
```

Service token flow:

```bash
TOKEN=$(curl -s -X POST "http://127.0.0.1:7000/api/v1/auth/service-token" \
  -u "vi-app:<SERVICE_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["advisor:read","market:read","signals:read"]}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

curl -s "http://127.0.0.1:7000/api/v1/advisor/context?ticker=AAPL" \
  -H "Authorization: Bearer ${TOKEN}"
```

Remote smoke:

```bash
API_BASE_URL="https://api.theeyebeta.store" \
SERVICE_CLIENT_ID="vi-app" \
SERVICE_CLIENT_SECRET="<SERVICE_SECRET>" \
bash scripts/verify_remote_access.sh
```

## Cloudflare Tunnel origin

Use:

- `http://127.0.0.1:7000`

Example ingress:

```yaml
ingress:
  - hostname: api.theeyebeta.store
    service: http://127.0.0.1:7000
  - hostname: dataapi.theeyebeta.store
    service: http://127.0.0.1:7000
  - service: http_status:404
```

## Optional production hardening toggles

- OIDC/JWKS user JWT validation:
  - `USER_JWT_JWKS_URL`, `USER_JWT_ISSUER`, `USER_JWT_AUDIENCE`, `USER_JWT_ALGORITHMS`
- Redis rate limiting backend:
  - `REDIS_URL`, `RATE_LIMIT_REDIS_PREFIX`
- mTLS service principal flow:
  - `SERVICE_MTLS_ENABLED=true`
  - `SERVICE_MTLS_SUBJECTS_JSON`
  - `TRUST_PROXY_HEADERS=true`

## Rotate local secrets

```bash
cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
source .venv/bin/activate
python scripts/rotate_secrets.py
```

This rotates `JWT_SECRET`, `USER_JWT_SECRET`, and all `SERVICE_CLIENTS_JSON` client secrets.

## Laptop E2E test

Use [OTHEREND_TEST.md](/home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI/OTHEREND_TEST.md) for a complete laptop verification workflow with sample successful responses.

## TypeScript frontend tester

```bash
cd frontend
npm install
npm start
```

Configure `frontend/.env` with `SERVICE_CLIENT_ID` and `SERVICE_CLIENT_SECRET`.

## Reusable plugin

- `packages/theeyebeta-dataapi-plugin`

Build:

```bash
cd packages/theeyebeta-dataapi-plugin
npm install
npm run build
```
