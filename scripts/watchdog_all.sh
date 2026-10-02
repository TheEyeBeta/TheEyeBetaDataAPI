#!/usr/bin/env bash
# Health watchdog. Restarts processes; never changes shared infrastructure.
#   - Data API :7000            -> restart via deploy.sh (this repo)
#   - Cloudflare Tunnel probe   -> LOG ONLY. The tunnel is shared with
#     TheEyeBetaProd and TheEyeBetaLocal (docs/OWNERSHIP.md); config changes are
#     an explicit operator action (docs/TUNNEL_RUNBOOK.md).
#   - TheEyeBetaLocal :8000/:8090 -> only when THEEYE_LOCAL_REPO is set explicitly.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${THEEYE_LOCAL_REPO:-}"
if [[ -n "$LOCAL_DIR" && ! -f "$LOCAL_DIR/scripts/deploy.sh" ]]; then
  echo "THEEYE_LOCAL_REPO=$LOCAL_DIR has no scripts/deploy.sh" >&2
  exit 1
fi
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

check_tunnel() {
  if health_ok "https://dataapiprod.theeyebeta.store/health"; then
    return
  fi
  # Deliberately no automatic fix: a config push here would overwrite routing
  # for every hostname on the shared tunnel.
  log "ALERT: https://dataapiprod.theeyebeta.store/health failing; tunnel config NOT changed (operator action)"
}

restart_local_stack() {
  log "Local stack unhealthy — restarting via TheEyeBetaLocal deploy.sh"
  DEPLOY_SKIP_GIT_SYNC=1 DEPLOY_SKIP_PIP_INSTALL=1 bash "$LOCAL_DIR/scripts/deploy.sh" \
    >>"$LOG_DIR/watchdog-local.log" 2>&1 || true
}

log "Watchdog started (interval=${INTERVAL}s)"
log "  Data API: $REPO_DIR"
log "  Local:    ${LOCAL_DIR:-<not managed; set THEEYE_LOCAL_REPO to opt in>}"

while true; do
  ensure_no_docker
  check_tunnel

  if ! health_ok "http://127.0.0.1:7000/health"; then
    restart_dataapi
  fi

  if [[ -n "$LOCAL_DIR" ]]; then
    api_ok=false
    trask_ok=false
    health_ok "http://127.0.0.1:8000/health" && api_ok=true
    health_ok "http://127.0.0.1:8090/health" && trask_ok=true
    if ! $api_ok || ! $trask_ok; then
      restart_local_stack
    fi
  fi

  sleep "$INTERVAL"
done
