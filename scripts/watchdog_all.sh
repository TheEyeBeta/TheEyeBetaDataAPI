#!/usr/bin/env bash
# Keep local services alive: Data API :7000, TheEyeBetaLocal API :8000, Trask :8090
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${THEEYE_LOCAL_REPO:-$(cd "$REPO_DIR/../TheEyeBetaLocal" 2>/dev/null && pwd || true)}"
LOG_DIR="$REPO_DIR/.runtime-logs"
INTERVAL="${WATCHDOG_INTERVAL_SEC:-30}"

mkdir -p "$LOG_DIR"
log() { echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_DIR/watchdog.log"; }

health_ok() {
  curl -sf --max-time 5 "$1" >/dev/null 2>&1
}

ensure_no_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    return
  fi
  for c in theeyebeta-dataapi theeyebeta-dataapi-nginx theeyebeta-api-dev theeyebeta-engine-dev; do
    if docker ps -q -f "name=^${c}$" 2>/dev/null | grep -q .; then
      log "Stopping Docker container $c (native-only mode)"
      docker stop "$c" >/dev/null 2>&1 || true
      docker rm "$c" >/dev/null 2>&1 || true
    fi
  done
}

restart_dataapi() {
  log "Data API unhealthy — restarting via deploy.sh"
  DEPLOY_SKIP_GIT_SYNC=1 DEPLOY_SKIP_PIP_INSTALL=1 bash "$REPO_DIR/scripts/deploy.sh" >>"$LOG_DIR/watchdog.log" 2>&1 || true
}

ensure_tunnel() {
  if health_ok "https://dataapi.theeyebeta.store/health" && health_ok "https://api.theeyebeta.store/health"; then
    return
  fi
  log "Tunnel unhealthy — running sync_tunnel.sh"
  bash "$REPO_DIR/scripts/sync_tunnel.sh" >>"$LOG_DIR/watchdog-cloudflared.log" 2>&1 || true
}

restart_local_stack() {
  if [[ -z "$LOCAL_DIR" || ! -f "$LOCAL_DIR/scripts/deploy.sh" ]]; then
    log "TheEyeBetaLocal not found — cannot restart :8000/:8090"
    return
  fi
  log "Local stack unhealthy — restarting via TheEyeBetaLocal deploy.sh"
  DEPLOY_SKIP_GIT_SYNC=1 DEPLOY_SKIP_PIP_INSTALL=1 bash "$LOCAL_DIR/scripts/deploy.sh" \
    >>"$LOG_DIR/watchdog-local.log" 2>&1 || true
}

log "Watchdog started (interval=${INTERVAL}s)"
log "  Data API: $REPO_DIR"
log "  Local:    ${LOCAL_DIR:-<not found>}"

while true; do
  ensure_no_docker
  ensure_tunnel

  if ! health_ok "http://127.0.0.1:7000/health"; then
    restart_dataapi
  fi

  api_ok=false
  trask_ok=false
  health_ok "http://127.0.0.1:8000/health" && api_ok=true
  health_ok "http://127.0.0.1:8090/health" && trask_ok=true
  if ! $api_ok || ! $trask_ok; then
    restart_local_stack
  fi

  sleep "$INTERVAL"
done
