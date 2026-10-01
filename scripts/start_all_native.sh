#!/usr/bin/env bash
# Start services natively (no Docker) and the health watchdog.
# Data API: 127.0.0.1:7000. TheEyeBetaLocal (engine + API :8000 + Trask :8090)
# only when THEEYE_LOCAL_REPO is set explicitly.
# Does NOT change Cloudflare Tunnel configuration: the tunnel is shared
# (docs/OWNERSHIP.md) and changes are an explicit, approved operator action.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${THEEYE_LOCAL_REPO:-}"
LOG_DIR="$REPO_DIR/.runtime-logs"
mkdir -p "$LOG_DIR"

health_ok() {
  curl -sf --max-time 3 "$1" >/dev/null 2>&1
}

echo "==> Stopping obsolete Docker app containers"
if command -v docker >/dev/null 2>&1; then
  for c in theeyebeta-dataapi theeyebeta-dataapi-nginx theeyebeta-api-dev theeyebeta-engine-dev; do
    docker stop "$c" 2>/dev/null || true
    docker rm "$c" 2>/dev/null || true
  done
fi

echo ""
echo "==> Data API (native, port 7000)"
if health_ok "http://127.0.0.1:7000/health"; then
  echo "    Already healthy on :7000"
else
  fuser -k 7000/tcp 2>/dev/null || true
  sleep 1
  cd "$REPO_DIR"
  DEPLOY_SKIP_GIT_SYNC=1 DEPLOY_SKIP_PIP_INSTALL=1 bash scripts/deploy.sh
fi

if [[ -n "$LOCAL_DIR" && -f "$LOCAL_DIR/scripts/start_all_native.sh" ]]; then
  echo ""
  echo "==> TheEyeBetaLocal (engine + API :8000 + Trask)"
  bash "$LOCAL_DIR/scripts/start_all_native.sh"
elif [[ -n "$LOCAL_DIR" && -f "$LOCAL_DIR/scripts/stop_then_start_repo.sh" ]]; then
  echo ""
  echo "==> TheEyeBetaLocal (engine + API :8000 + Trask)"
  bash "$LOCAL_DIR/scripts/stop_then_start_repo.sh"
elif [[ -n "$LOCAL_DIR" ]]; then
  echo "THEEYE_LOCAL_REPO=$LOCAL_DIR has no start script" >&2
  exit 1
else
  echo ""
  echo "==> TheEyeBetaLocal not managed here (set THEEYE_LOCAL_REPO to opt in)"
fi

echo ""
echo "==> Watchdog (restarts services; reports tunnel failures, never reconfigures it)"
if command -v tmux >/dev/null 2>&1; then
  tmux kill-session -t theeyebeta-watchdog 2>/dev/null || true
  tmux new-session -d -s theeyebeta-watchdog "bash $REPO_DIR/scripts/watchdog_all.sh"
  echo "    Started tmux session: theeyebeta-watchdog"
else
  echo "    tmux not installed — run: bash scripts/watchdog_all.sh manually"
fi

echo ""
echo "==> Verify (local)"
echo "  Data API:  curl -s http://127.0.0.1:7000/health"
echo "  Main API:  curl -s http://127.0.0.1:8000/health"
echo "  Trask:     curl -s http://127.0.0.1:8090/health"
echo ""
echo "==> Verify (tunnel)"
echo "  Data API:  curl -s https://dataapi.theeyebeta.store/health"
echo "  Main API:  curl -s https://api.theeyebeta.store/health"
echo ""
echo "Tunnel changes are manual and approved: docs/TUNNEL_RUNBOOK.md"
