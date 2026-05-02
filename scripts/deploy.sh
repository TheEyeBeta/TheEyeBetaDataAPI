#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEALTH_URL="http://127.0.0.1:7000/health"
HEALTH_RETRIES=15
HEALTH_INTERVAL=4
SERVICE_NAME="theeyebeta-dataapi"

log() { echo "[deploy] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

cd "$REPO_DIR"

log "Pulling latest code from origin..."
git fetch origin main
git reset --hard origin/main

log "Installing dependencies..."
"$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

log "Restarting service..."
sudo systemctl restart "$SERVICE_NAME"

log "Waiting for health check at $HEALTH_URL..."
for i in $(seq 1 $HEALTH_RETRIES); do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        log "Health check passed."
        exit 0
    fi
    log "Attempt $i/$HEALTH_RETRIES — not ready yet, waiting ${HEALTH_INTERVAL}s..."
    sleep "$HEALTH_INTERVAL"
done

log "ERROR: Service did not become healthy after $((HEALTH_RETRIES * HEALTH_INTERVAL))s."
sudo journalctl -u "$SERVICE_NAME" --no-pager -n 50 2>/dev/null || true
exit 1
