# End-to-End Verification

Verify from a separate machine that the API is reachable through the Cloudflare
Tunnel and returns real database-backed data. Every step is read-only.

**Release gates:** smoke **Lens** (`ai-advisor-production`) and the
**TheEyeBetaAdmin Frontend** (`/admin/*` gateway). See
[`IAM_CONSUMER_INVENTORY.md`](IAM_CONSUMER_INVENTORY.md).

## 1) Prerequisites

- The API is running on the host at `127.0.0.1:7000`.
- Tunnel ingress routes `dataapiprod.theeyebeta.store -> http://127.0.0.1:7000`.
- You hold service credentials (from IAM / your password manager, never from chat):
  - `ai-advisor-production` — Lens read checks
  - `theeyebeta-prod-admin` (or `admin-tool-production`) — admin checks

```bash
export API_BASE_URL="https://dataapiprod.theeyebeta.store"
export LENS_CLIENT_ID="ai-advisor-production"
export LENS_CLIENT_SECRET="<ai-advisor-production-secret>"
export ADMIN_CLIENT_ID="theeyebeta-prod-admin"
export ADMIN_CLIENT_SECRET="<theeyebeta-prod-admin-secret>"
```

## 2) Health (public)

```bash
curl -sS "${API_BASE_URL}/health"
```

Expected: `{"status":"healthy","database":true,"redis":null}` (`redis` is `null`
when `REDIS_URL` is unset).

## 3) Lens read flow

```bash
LENS_TOKEN=$(curl -sS -X POST "${API_BASE_URL}/api/v1/auth/service-token" \
  -u "${LENS_CLIENT_ID}:${LENS_CLIENT_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["advisor:read","market:read","signals:read","symbols:read"]}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -sS "${API_BASE_URL}/api/v1/advisor/context?ticker=AAPL" \
  -H "Authorization: Bearer ${LENS_TOKEN}"
```

Expected shape (truncated):

```json
{"tickers":[{"ticker":"AAPL","company_name":"Apple Inc."}],"news":[...],"ticker_snapshot":{...}}
```

## 4) Admin Frontend gateway

Unauthenticated probe — expect `401` when the gateway and admin-service are up
(`503` means `ADMIN_GATEWAY_ENABLED=false`):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "${API_BASE_URL}/admin/auth/me"
```

## 5) Admin read flow

```bash
ADMIN_TOKEN=$(curl -sS -X POST "${API_BASE_URL}/api/v1/auth/service-token" \
  -u "${ADMIN_CLIENT_ID}:${ADMIN_CLIENT_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["admin:read"]}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -sS "${API_BASE_URL}/api/v1/admin/audit-events?limit=2" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

Expected shape:

```json
{"events":[{"event_id":"...","event_type":"...","event_category":"...","severity":"...","created_at":"..."}]}
```

## 6) Portfolio ownership (optional, needs a `portfolio:read` client)

Service principals must name the owner; users may only read their own state.

```bash
# Service principal without owner_subject -> 422 VALIDATION_ERROR
curl -sS "${API_BASE_URL}/api/v1/portfolio/state" -H "Authorization: Bearer ${PORTFOLIO_TOKEN}"

# With owner_subject -> 200
curl -sS "${API_BASE_URL}/api/v1/portfolio/state?owner_subject=user-abc&position_limit=2" \
  -H "Authorization: Bearer ${PORTFOLIO_TOKEN}"
```

## 7) One-command smoke

```bash
API_BASE_URL="${API_BASE_URL}" \
SERVICE_CLIENT_ID="${LENS_CLIENT_ID}" \
SERVICE_CLIENT_SECRET="${LENS_CLIENT_SECRET}" \
bash scripts/verify_remote_access.sh
```

Runs health → service token → market quotes → advisor context, redacting the
token from its output.

## 8) Troubleshooting

| Symptom | Meaning |
|---|---|
| `401` on token issue | Wrong client id / secret |
| `403 FORBIDDEN` on a route | Token lacks the scope that route requires |
| `422 REQUEST_VALIDATION_ERROR` | Bad query/body parameter; `message` lists the failing fields |
| `503 DATABASE_UNAVAILABLE` | API is up but the DB query failed or Postgres is down |
| `400 Invalid host header` | Hostname not in `TRUSTED_HOSTS` |
| Connection refused / timeout | API not running on the host, or tunnel not routing to `127.0.0.1:7000` |
