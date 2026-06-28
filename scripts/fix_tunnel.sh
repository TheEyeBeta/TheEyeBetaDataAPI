#!/usr/bin/env bash
# One-time permanent fix: install native Cloudflare Tunnel config to systemd.
# Run: sudo bash scripts/fix_tunnel.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="/etc/cloudflared/config.yml"
CANONICAL_CONFIG="$REPO_DIR/deploy/cloudflared-config.yml"
TUNNEL_NAME="my-api"
RUN_USER="${SUDO_USER:-root}"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/fix_tunnel.sh" >&2
  exit 1
fi

if [[ ! -f "$CANONICAL_CONFIG" ]]; then
  echo "Missing $CANONICAL_CONFIG" >&2
  exit 1
fi

echo "Installing tunnel config to $CONFIG"
cp "$CANONICAL_CONFIG" "$CONFIG"
chmod 644 "$CONFIG"

# Stop duplicate user-level connector before systemd takes over.
sudo -u "$RUN_USER" tmux kill-session -t cloudflared-native 2>/dev/null || true

echo "Restarting cloudflared service..."
systemctl restart cloudflared
sleep 3
systemctl is-active cloudflared

# Sync DNS + remote ingress (will not start fallback once /etc config is correct).
sudo -u "$RUN_USER" bash "$REPO_DIR/scripts/sync_tunnel.sh" || true

echo ""
echo "Tunnel fixed (native, no Docker):"
echo "  api.theeyebeta.store     -> 127.0.0.1:8000  (TheEyeBetaLocal Main API)"
echo "  dataapi.theeyebeta.store     -> 127.0.0.1:7000  (TheEyeBetaDataAPI)"
echo "  dataapiprod.theeyebeta.store -> 127.0.0.1:7000  (TheEyeBetaDataAPI prod alias)"
echo "  admin.theeyebeta.store       -> 127.0.0.1:7200  (TheEyeBetaProd admin)"
echo ""
echo "Verify:"
echo "  curl -s https://api.theeyebeta.store/health"
echo "  curl -s https://dataapi.theeyebeta.store/health"
echo "  curl -s https://dataapiprod.theeyebeta.store/health"
echo ""
echo "Docs: docs/TUNNEL_RUNBOOK.md"
