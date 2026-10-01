#!/usr/bin/env bash
# Deploy / restart the DataAPI production service.
#
#   - Code: checks out DEPLOY_SHA (CI passes the tested commit) or origin/main,
#     only if it is on origin/main. Skipped with DEPLOY_SKIP_GIT_SYNC=1.
#   - Restart: the --user systemd unit only. If the unit is not visible this
#     FAILS; a tmux-run gunicorn is started only with
#     DEPLOY_ALLOW_TMUX_FALLBACK=1 (dev boxes without the unit).
#   - Health: /health must report "database": true.
#   - Rollback: if a git sync happened and health fails, the previous commit
#     is restored, reinstalled and restarted; the script still exits non-zero.
set -euo pipefail

DEFAULT_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="${DEPLOY_REPO_DIR:-$DEFAULT_REPO_DIR}"
HEALTH_URL="${DEPLOY_HEALTH_URL:-http://127.0.0.1:7000/health}"
HEALTH_RETRIES="${DEPLOY_HEALTH_RETRIES:-15}"
HEALTH_INTERVAL="${DEPLOY_HEALTH_INTERVAL:-4}"
DEPLOY_SHA="${DEPLOY_SHA:-}"
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
    if [ "${DEPLOY_ALLOW_TMUX_FALLBACK:-}" != "1" ]; then
        log "ERROR: --user unit '$SERVICE_NAME' not found (XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR)."
        log "Refusing to start a second, unmanaged gunicorn. Install the unit"
        log "(scripts/install_service.sh) or set DEPLOY_ALLOW_TMUX_FALLBACK=1 on a dev box."
        return 1
    fi
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

PREVIOUS_SHA="$(git rev-parse HEAD)"
SYNCED=""

if [ -z "${DEPLOY_SKIP_GIT_SYNC:-}" ]; then
    log "Fetching origin/main..."
    git fetch origin main
    target="${DEPLOY_SHA:-$(git rev-parse origin/main)}"
    if ! git merge-base --is-ancestor "$target" origin/main; then
        log "ERROR: $target is not on origin/main; refusing to deploy it."
        exit 1
    fi
    log "Deploying $target (previous $PREVIOUS_SHA)"
    git reset --hard "$target"
    SYNCED=1
else
    log "Skipping git sync because DEPLOY_SKIP_GIT_SYNC is set."
fi

REQUIRED_PYTHON_VERSION="3.12"

ensure_venv_python_version() {
    local venv_python="$REPO_DIR/.venv/bin/python"
    if [ -x "$venv_python" ]; then
        local current_version
        current_version="$("$venv_python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
        if [ "$current_version" = "$REQUIRED_PYTHON_VERSION" ]; then
            return 0
        fi
        log "Existing .venv is Python ${current_version:-unknown}, not $REQUIRED_PYTHON_VERSION — recreating."
        rm -rf "$REPO_DIR/.venv"
    fi

    if ! command -v "python$REQUIRED_PYTHON_VERSION" >/dev/null 2>&1; then
        log "ERROR: python$REQUIRED_PYTHON_VERSION is not installed on this host."
        exit 1
    fi

    log "Creating .venv with python$REQUIRED_PYTHON_VERSION..."
    "python$REQUIRED_PYTHON_VERSION" -m venv "$REPO_DIR/.venv"
}

install_dependencies() {
    if [ -z "${DEPLOY_SKIP_PIP_INSTALL:-}" ]; then
        ensure_venv_python_version
        log "Installing dependencies..."
        "$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
    else
        log "Skipping dependency install because DEPLOY_SKIP_PIP_INSTALL is set."
    fi
}

restart_service() {
    if service_exists; then
        log "Restarting service via systemd (--user)..."
        systemctl --user restart "$SERVICE_NAME"
    else
        restart_via_tmux
    fi
}

wait_healthy() {
    log "Waiting for health check at $HEALTH_URL (database must be true)..."
    local body
    for i in $(seq 1 "$HEALTH_RETRIES"); do
        body="$(curl -sf --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
        if printf '%s' "$body" | grep -Eq '"database"[[:space:]]*:[[:space:]]*true'; then
            log "Health check passed."
            return 0
        fi
        log "Attempt $i/$HEALTH_RETRIES — not ready yet (${body:-no response}), waiting ${HEALTH_INTERVAL}s..."
        sleep "$HEALTH_INTERVAL"
    done
    log "ERROR: Service did not become healthy after $((HEALTH_RETRIES * HEALTH_INTERVAL))s."
    journalctl --user -u "$SERVICE_NAME" --no-pager -n 50 2>/dev/null || true
    return 1
}

install_dependencies
restart_service
if wait_healthy; then
    log "Deployed $(git rev-parse HEAD)."
    exit 0
fi

if [ -n "$SYNCED" ] && [ "$(git rev-parse HEAD)" != "$PREVIOUS_SHA" ]; then
    log "ROLLBACK: restoring $PREVIOUS_SHA"
    git reset --hard "$PREVIOUS_SHA"
    install_dependencies
    restart_service
    if wait_healthy; then
        log "Rollback to $PREVIOUS_SHA is healthy. The deploy itself FAILED."
    else
        log "ERROR: rollback to $PREVIOUS_SHA is ALSO unhealthy — operator action required."
    fi
fi
exit 1
