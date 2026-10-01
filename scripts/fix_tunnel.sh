#!/usr/bin/env bash
# Install deploy/cloudflared-config.yml as /etc/cloudflared/config.yml and
# restart cloudflared. OPERATOR ACTION ONLY: requires TUNNEL_CHANGE_APPROVED=yes.
# Run: sudo TUNNEL_CHANGE_APPROVED=yes bash scripts/fix_tunnel.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="/etc/cloudflared/config.yml"
CANONICAL_CONFIG="$REPO_DIR/deploy/cloudflared-config.yml"
ADMIN_TERMINAL_HEALTH_URL="${ADMIN_TERMINAL_HEALTH_URL:-http://127.0.0.1:8080/healthz}"
TUNNEL_NAME="my-api"
RUN_USER="${SUDO_USER:-root}"

# ---------------------------------------------------------------------------
# Shared-infrastructure guard. This tunnel carries hostnames owned by
# TheEyeBetaProd and TheEyeBetaLocal too (docs/OWNERSHIP.md). Without explicit
# approval this script only prints what it would change and exits 2.
# ---------------------------------------------------------------------------
print_plan() {
  echo "Ingress in $CANONICAL_CONFIG (replaces the WHOLE tunnel ingress):"
  grep -E "hostname:|service:" "$CANONICAL_CONFIG" | sed 's/^/    /'
  echo "admin.theeyebeta.store -> :8080 is the DEBT-01 target; it applies only once $ADMIN_TERMINAL_HEALTH_URL is healthy."
}
if [[ "${TUNNEL_CHANGE_APPROVED:-}" != "yes" ]]; then
  echo "DRY RUN: shared Cloudflare Tunnel configuration is not changed by default."
  print_plan
  echo "To apply, after confirming live routing with the hostname owners:"
  echo "    sudo TUNNEL_CHANGE_APPROVED=yes bash $0"
  exit 2
fi

# ---------------------------------------------------------------------------
# Activation guard (DEBT-01). The config routes admin.theeyebeta.store to the
# AdminFrontend static terminal host on :8080. Applying it while that host is
# down takes the admin hostname offline, so even an approved run stops here
# unless the host answers its health check. Never bypassed automatically.
# ---------------------------------------------------------------------------
if grep -Eq "service:[[:space:]]*http://127\.0\.0\.1:8080" "$CANONICAL_CONFIG"; then
  terminal_health="$(curl -sf --max-time 5 "$ADMIN_TERMINAL_HEALTH_URL" 2>/dev/null || true)"
  if ! printf '%s' "$terminal_health" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
    echo "REFUSING: AdminFrontend terminal host is not healthy at $ADMIN_TERMINAL_HEALTH_URL." >&2
    echo "DO NOT APPLY this tunnel config until that health check passes (DEBT-01)." >&2
    exit 3
  fi
fi

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
sudo -u "$RUN_USER" TUNNEL_CHANGE_APPROVED=yes bash "$REPO_DIR/scripts/sync_tunnel.sh" || true

echo ""
echo "Tunnel fixed (native, no Docker):"
echo "  api.theeyebeta.store     -> 127.0.0.1:8000  (TheEyeBetaLocal Main API)"
echo "  dataapi.theeyebeta.store     -> 127.0.0.1:7000  (TheEyeBetaDataAPI)"
echo "  dataapiprod.theeyebeta.store -> 127.0.0.1:7000  (TheEyeBetaDataAPI prod alias)"
echo "  admin.theeyebeta.store       -> 127.0.0.1:8080  (TheEyeBetaAdminFrontend static terminal host; DEBT-01)"
echo ""
echo "Verify:"
echo "  curl -s https://api.theeyebeta.store/health"
echo "  curl -s https://dataapi.theeyebeta.store/health"
echo "  curl -s https://dataapiprod.theeyebeta.store/health"
echo ""
echo "Docs: docs/TUNNEL_RUNBOOK.md"
