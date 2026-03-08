#!/usr/bin/env bash
# -----------------------------------------------------------------------
# Provision service clients for all known integration points.
#
# This script creates database-backed API credentials for:
#   1. AI-Financial-Advisor backend (app_type: mobile-backend)
#   2. TheEyeBetaLocal remote engine (app_type: trade-engine)
#   3. Admin tooling (app_type: admin-tool)
#
# Usage:
#   cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
#   bash scripts/provision_integrations.sh [--environment production]
#
# Prerequisites:
#   - PostgreSQL running with TheEyeBeta2025Live database
#   - IAM schema applied (deploy/iam_api_key_schema.sql)
#   - Python venv activated or available at .venv/
# -----------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT="${1:-production}"

cd "$REPO_ROOT"

# Activate venv if available
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f "../TheEyeBetaLocal/.venv/bin/activate" ]; then
    source "../TheEyeBetaLocal/.venv/bin/activate"
fi

echo "========================================="
echo "  DataAPI Integration Provisioning"
echo "  Environment: $ENVIRONMENT"
echo "========================================="
echo ""

provision() {
    local client_id="$1"
    local display_name="$2"
    local app_type="$3"
    local extra_args="${4:-}"

    echo "--- Provisioning: $client_id ($app_type) ---"
    python scripts/provision_db_service_client.py \
        --client-id "$client_id" \
        --display-name "$display_name" \
        --app-type "$app_type" \
        --environment "$ENVIRONMENT" \
        --created-by "provision-integrations" \
        --allow-existing \
        $extra_args
    echo ""
}

# 1. AI-Financial-Advisor backend
#    Default scopes: advisor:read, market:read, symbols:read
#    Additional: signals:read (for trading signals page)
provision "ai-advisor-${ENVIRONMENT}" \
    "AI Financial Advisor ($ENVIRONMENT)" \
    "mobile-backend" \
    "--scope signals:read"

# 2. Trade Engine remote instance
#    Default scopes: trades:write, portfolio:read, internal:jobs
#    Additional: market:read (for data verification)
provision "trade-engine-${ENVIRONMENT}" \
    "Trade Engine Remote ($ENVIRONMENT)" \
    "trade-engine" \
    "--scope market:read"

# 3. Admin tool
#    Default scopes: admin:read, admin:write, internal:jobs
provision "admin-tool-${ENVIRONMENT}" \
    "Admin Dashboard ($ENVIRONMENT)" \
    "admin-tool"

echo "========================================="
echo "  IMPORTANT: Save the API keys above!"
echo "  They are shown only once."
echo "========================================="
echo ""
echo "Add to consuming service .env files:"
echo "  DATAAPI_URL=https://api.theeyebeta.store"
echo "  DATAAPI_CLIENT_ID=<client_id>"
echo "  DATAAPI_CLIENT_SECRET=<api_key from above>"
echo "  DATAAPI_ENABLED=true"
