#!/usr/bin/env bash
set -euo pipefail

# Remote smoke test from laptop/anywhere
# Usage:
#   API_BASE_URL=https://api.yourdomain.com API_KEY=... bash scripts/verify_remote_access.sh

: "${API_BASE_URL:?Set API_BASE_URL, e.g. https://api.yourdomain.com}"
: "${API_KEY:?Set API_KEY}"

echo "[1/4] Health check"
curl -fsS "${API_BASE_URL}/health" | sed 's/^/  /'
echo

echo "[2/4] Context with API key"
curl -fsS -H "X-API-Key: ${API_KEY}" "${API_BASE_URL}/api/v1/context?ticker=AAPL" | head -c 400
echo -e "\n"

echo "[3/4] Issue JWT token"
TOKEN_RESPONSE=$(curl -fsS -X POST "${API_BASE_URL}/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d '{"subject":"remote-laptop-check","expires_minutes":30}')

echo "  ${TOKEN_RESPONSE}" | head -c 300
echo

TOKEN=$(echo "${TOKEN_RESPONSE}" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
if [[ -z "${TOKEN}" ]]; then
  echo "Failed to parse access_token from response"
  exit 1
fi

echo "[4/4] Chat endpoint with Bearer token"
curl -fsS -X POST "${API_BASE_URL}/api/v1/chat" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"question":"Give me a quick trusted snapshot for AAPL","ticker":"AAPL"}' | head -c 500
echo -e "\n\nRemote verification complete."
