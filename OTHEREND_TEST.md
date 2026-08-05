# Laptop End-to-End Test Guide

Use this to verify from a separate laptop that the public API is reachable through Cloudflare Tunnel and returning real database-backed data.

## 1) Prerequisites

- Server is running this API on `127.0.0.1:7000`.
- Cloudflare Tunnel ingress points to:
  - `dataapi.theeyebeta.store -> http://127.0.0.1:7000`
- You have service credentials from server `.env`:
  - `vi-app` client id/secret (read checks)
  - `trade-engine` client id/secret (write checks)
  - `admin-tool` client id/secret (admin checks)

## 2) Set laptop variables

On your laptop terminal:

```bash
export API_BASE_URL="https://dataapi.theeyebeta.store"
export VI_CLIENT_ID="vi-app"
export VI_CLIENT_SECRET="<vi-app-secret>"
export TRADE_CLIENT_ID="trade-engine"
export TRADE_CLIENT_SECRET="<trade-engine-secret>"
export ADMIN_CLIENT_ID="admin-tool"
export ADMIN_CLIENT_SECRET="<admin-tool-secret>"
```

## 3) Health check (public)

```bash
curl -sS "${API_BASE_URL}/health"
```

Expected shape:

```json
{"status":"healthy","database":true}
```

## 4) Read flow test (advisor context)

Issue VI token:

```bash
VI_TOKEN=$(curl -sS -X POST "${API_BASE_URL}/api/v1/auth/service-token" \
  -u "${VI_CLIENT_ID}:${VI_CLIENT_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["advisor:read","market:read"]}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

Fetch context:

```bash
curl -sS "${API_BASE_URL}/api/v1/context?ticker=AAPL" \
  -H "Authorization: Bearer ${VI_TOKEN}"
```

Expected shape:

```json
{
  "tickers":[{"ticker":"AAPL","company_name":"Apple Inc."}],
  "news":[...],
  "ticker_snapshot":{...}
}
```

Live sample seen on March 8, 2026 (truncated):

```json
{"tickers":[{"ticker":"A","company_name":"Agilent Technologies, Inc."},{"ticker":"AAPL","company_name":"Apple Inc."}, ... ]}
```

## 5) Write flow test (trade + idempotency)

Issue trade-engine token:

```bash
TRADE_TOKEN=$(curl -sS -X POST "${API_BASE_URL}/api/v1/auth/service-token" \
  -u "${TRADE_CLIENT_ID}:${TRADE_CLIENT_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["trades:write","portfolio:read","internal:jobs"]}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

First order:

```bash
curl -sS -X POST "${API_BASE_URL}/api/v1/trades/orders" \
  -H "Authorization: Bearer ${TRADE_TOKEN}" \
  -H "Idempotency-Key: laptop-test-1" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","side":"buy","quantity":1}'
```

Replay same request with same idempotency key:

```bash
curl -sS -X POST "${API_BASE_URL}/api/v1/trades/orders" \
  -H "Authorization: Bearer ${TRADE_TOKEN}" \
  -H "Idempotency-Key: laptop-test-1" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","side":"buy","quantity":1}'
```

Pass criteria:

- First response: `"idempotent_replay": false`
- Second response: same `order_ref`, `"idempotent_replay": true`

Live sample seen on March 8, 2026:

```json
{"status":"accepted","order_ref":"paper-trade-4","idempotency_key":"laptop-doc-sample-1","symbol":"AAPL","side":"buy","quantity":1.0,"executed_price":256.565002,"total_cost":256.565002,"accepted_at":"2026-03-08T00:58:25.355491Z","idempotent_replay":false}
```

Replay sample:

```json
{"status":"accepted","order_ref":"paper-trade-4","idempotency_key":"laptop-doc-sample-1","symbol":"AAPL","side":"buy","quantity":1.0,"executed_price":256.565002,"total_cost":256.565002,"accepted_at":"2026-03-08T00:58:25.355491Z","idempotent_replay":true}
```

## 6) Portfolio ownership check

Missing owner (service principal):

```bash
curl -sS "${API_BASE_URL}/api/v1/portfolio/state" \
  -H "Authorization: Bearer ${TRADE_TOKEN}"
```

Expected: `422` validation error.

With owner:

```bash
curl -sS "${API_BASE_URL}/api/v1/portfolio/state?owner_subject=user-abc&position_limit=2" \
  -H "Authorization: Bearer ${TRADE_TOKEN}"
```

Live sample:

```json
{"owner_subject":"user-abc","valuation":null,"positions":[]}
```

## 7) Internal command + admin audit checks

Queue internal rebuild command:

```bash
curl -sS -X POST "${API_BASE_URL}/api/v1/internal/jobs/rebuild-indicators" \
  -H "Authorization: Bearer ${TRADE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","force":true,"reason":"laptop-e2e"}'
```

Expected shape:

```json
{"status":"accepted","command_id":"<uuid>","command_type":"rebuild_indicators","created_at":"<timestamp>"}
```

Issue admin token:

```bash
ADMIN_TOKEN=$(curl -sS -X POST "${API_BASE_URL}/api/v1/auth/service-token" \
  -u "${ADMIN_CLIENT_ID}:${ADMIN_CLIENT_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["admin:read"]}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

Fetch admin events:

```bash
curl -sS "${API_BASE_URL}/api/v1/admin/audit-events?limit=2" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

Expected shape:

```json
{"events":[{"event_id":"...","event_type":"...","event_category":"...","severity":"...","created_at":"..."}]}
```

## 8) One-command remote smoke

Bash (read-only: health, token, context, chat):

```bash
API_BASE_URL="${API_BASE_URL}" \
SERVICE_CLIENT_ID="${VI_CLIENT_ID}" \
SERVICE_CLIENT_SECRET="${VI_CLIENT_SECRET}" \
bash scripts/verify_remote_access.sh
```

Python (full E2E, cross-platform, all 7 steps):

```bash
API_BASE_URL="${API_BASE_URL}" \
VI_CLIENT_ID="${VI_CLIENT_ID}" VI_CLIENT_SECRET="${VI_CLIENT_SECRET}" \
TRADE_CLIENT_ID="${TRADE_CLIENT_ID}" TRADE_CLIENT_SECRET="${TRADE_CLIENT_SECRET}" \
ADMIN_CLIENT_ID="${ADMIN_CLIENT_ID}" ADMIN_CLIENT_SECRET="${ADMIN_CLIENT_SECRET}" \
python scripts/other_end_e2e_test.py
```

On Windows (PowerShell):

```powershell
$env:API_BASE_URL = "https://dataapi.theeyebeta.store"
$env:VI_CLIENT_ID = "vi-app"; $env:VI_CLIENT_SECRET = "<vi-app-secret>"
$env:TRADE_CLIENT_ID = "trade-engine"; $env:TRADE_CLIENT_SECRET = "<trade-engine-secret>"
$env:ADMIN_CLIENT_ID = "admin-tool"; $env:ADMIN_CLIENT_SECRET = "<admin-tool-secret>"
python scripts/other_end_e2e_test.py
```

## 9) Troubleshooting

- `404` on `api.theeyebeta.store`:
  - That hostname is not mapped to this service yet. Use `dataapi.theeyebeta.store` unless you update tunnel ingress.
- `401` on token issue:
  - Wrong client id/secret.
- `403` when calling route:
  - Token missing required scope for that capability.
- `503 DATABASE_UNAVAILABLE`:
  - API up, but DB query failed or DB unavailable.
- Connection refused / timeout:
  - API process not running locally on server, or Cloudflare tunnel not routing to `http://127.0.0.1:7000`.
