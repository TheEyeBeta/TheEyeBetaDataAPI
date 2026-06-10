#!/usr/bin/env bash
# Start all TheEyeBeta2025 services natively (no Docker) and sync Cloudflare Tunnel.
# Data API: 127.0.0.1:7000 | TheEyeBetaLocal: engine + API :8000 + Trask :8090
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${THEEYE_LOCAL_REPO:-$(cd "$REPO_DIR/../TheEyeBetaLocal" 2>/dev/null && pwd || true)}"
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
else
  echo ""
  echo "==> TheEyeBetaLocal repo not found at $LOCAL_DIR — skipping engine/API/Trask"
fi

echo ""
echo "==> Cloudflare Tunnel"
bash "$REPO_DIR/scripts/sync_tunnel.sh"

echo ""
echo "==> Watchdog (keeps services + tunnel alive)"
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
echo "Permanent tunnel fix (if dataapi tunnel still fails): sudo bash scripts/fix_tunnel.sh"
echo "Docs: docs/TUNNEL_RUNBOOK.md"
