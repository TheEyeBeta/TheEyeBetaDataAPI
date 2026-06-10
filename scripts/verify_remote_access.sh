#!/usr/bin/env bash
set -euo pipefail

# Remote smoke test through Cloudflare Tunnel.
# Data API (quotes, advisor, auth):
#   API_BASE_URL=https://dataapi.theeyebeta.store SERVICE_CLIENT_ID=vi-app SERVICE_CLIENT_SECRET=... bash scripts/verify_remote_access.sh
# Main API (TheEyeBetaLocal):
#   API_BASE_URL=https://api.theeyebeta.store ...

API_BASE_URL="${API_BASE_URL:-https://dataapi.theeyebeta.store}"
: "${SERVICE_CLIENT_ID:?Set SERVICE_CLIENT_ID}"
: "${SERVICE_CLIENT_SECRET:?Set SERVICE_CLIENT_SECRET}"

echo "Target: ${API_BASE_URL}"
echo

echo "[1/4] Health check"
curl -fsS "${API_BASE_URL}/health" | sed 's/^/  /'
echo

echo "[2/4] Issue service token (client credentials)"
TOKEN_RESPONSE=$(curl -fsS -X POST "${API_BASE_URL}/api/v1/auth/service-token" \
  -u "${SERVICE_CLIENT_ID}:${SERVICE_CLIENT_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["advisor:read","market:read"]}')

SAFE_TOKEN_RESPONSE=$(echo "${TOKEN_RESPONSE}" | sed -E 's/"access_token":"[^"]+"/"access_token":"<redacted>"/')
echo "  ${SAFE_TOKEN_RESPONSE}" | head -c 400
echo

TOKEN=$(echo "${TOKEN_RESPONSE}" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
if [[ -z "${TOKEN}" ]]; then
  echo "Failed to parse access_token from response"
  exit 1
fi

echo "[3/4] Market quotes with Bearer token"
curl -fsS "${API_BASE_URL}/api/v1/market-data/quotes?symbols=AAPL" \
  -H "Authorization: Bearer ${TOKEN}" | head -c 500
echo -e "\n"

echo "[4/4] Advisor context with Bearer token"
curl -fsS "${API_BASE_URL}/api/v1/advisor/context?ticker=AAPL" \
  -H "Authorization: Bearer ${TOKEN}" | head -c 500
echo -e "\n\nRemote verification complete."
