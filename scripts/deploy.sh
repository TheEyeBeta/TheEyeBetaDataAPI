#!/usr/bin/env bash
set -euo pipefail

DEFAULT_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="${DEPLOY_REPO_DIR:-$DEFAULT_REPO_DIR}"
HEALTH_URL="${DEPLOY_HEALTH_URL:-http://127.0.0.1:7000/health}"
HEALTH_RETRIES="${DEPLOY_HEALTH_RETRIES:-15}"
HEALTH_INTERVAL="${DEPLOY_HEALTH_INTERVAL:-4}"
SERVICE_NAME="${DEPLOY_SERVICE_NAME:-theeyebeta-dataapi}"
TMUX_SESSION="${DEPLOY_TMUX_SESSION:-theeyebeta-dataapi}"
TMUX_LOG_DIR="${DEPLOY_TMUX_LOG_DIR:-$REPO_DIR/.runtime-logs}"
TMUX_LOG_FILE="${TMUX_LOG_DIR}/${TMUX_SESSION}.log"

log() { echo "[deploy] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# theeyebeta-dataapi is a --user systemd unit, not a system one (see
# ~/.config/systemd/user/theeyebeta-dataapi.service). A plain `systemctl`
# call (no --user) always reports it as not-found, even when it's running.
# XDG_RUNTIME_DIR is set defensively since a CI-invoked, non-interactive
# process may not inherit it the way an interactive login shell does.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

service_exists() {
    local load_state
    load_state="$(systemctl --user show -p LoadState --value "$SERVICE_NAME" 2>/dev/null || true)"
    [ -n "$load_state" ] && [ "$load_state" != "not-found" ]
}

restart_via_tmux() {
    if ! command -v tmux >/dev/null 2>&1; then
        log "ERROR: tmux is required when the systemd service is unavailable."
        return 1
    fi

    mkdir -p "$TMUX_LOG_DIR"

    log "Restarting app in tmux session '$TMUX_SESSION'..."
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
    tmux new-session -d -s "$TMUX_SESSION" \
        "cd '$REPO_DIR' && ./scripts/run_production.sh 2>&1 | tee -a '$TMUX_LOG_FILE'"
}

cd "$REPO_DIR"

if [ -z "${DEPLOY_SKIP_GIT_SYNC:-}" ]; then
    log "Pulling latest code from origin..."
    git fetch origin main
    git reset --hard origin/main
else
    log "Skipping git sync because DEPLOY_SKIP_GIT_SYNC is set."
fi

if [ -z "${DEPLOY_SKIP_PIP_INSTALL:-}" ]; then
    log "Installing dependencies..."
    "$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
else
    log "Skipping dependency install because DEPLOY_SKIP_PIP_INSTALL is set."
fi

if service_exists; then
    log "Restarting service via systemd (--user)..."
    systemctl --user restart "$SERVICE_NAME"
else
    restart_via_tmux
fi

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
journalctl --user -u "$SERVICE_NAME" --no-pager -n 50 2>/dev/null || true
exit 1
