#!/usr/bin/env bash
set -euo pipefail

# Remote smoke test from laptop/anywhere
# Usage:
#   API_BASE_URL=https://api.yourdomain.com SERVICE_CLIENT_ID=vi-app SERVICE_CLIENT_SECRET=... bash scripts/verify_remote_access.sh

: "${API_BASE_URL:?Set API_BASE_URL, e.g. https://api.yourdomain.com}"
: "${SERVICE_CLIENT_ID:?Set SERVICE_CLIENT_ID}"
: "${SERVICE_CLIENT_SECRET:?Set SERVICE_CLIENT_SECRET}"

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

echo "[3/4] Advisor context with Bearer token"
curl -fsS "${API_BASE_URL}/api/v1/context?ticker=AAPL" \
  -H "Authorization: Bearer ${TOKEN}" | head -c 500
echo -e "\n"

echo "[4/4] Chat endpoint with Bearer token"
curl -fsS -X POST "${API_BASE_URL}/api/v1/advisor/chat" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"question":"Give me a quick trusted snapshot for AAPL","ticker":"AAPL"}' | head -c 500
echo -e "\n\nRemote verification complete."
