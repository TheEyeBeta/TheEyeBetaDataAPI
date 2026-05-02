#!/usr/bin/env bash
# One-time setup: installs the app as a systemd service on Linux.
# Run once with sudo: sudo bash scripts/install_service.sh
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "Error: this script must be run as root (use sudo)." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="theeyebeta-dataapi"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Resolve the real user who invoked sudo (falls back to root)
RUN_USER="${SUDO_USER:-root}"
RUN_GROUP="$(id -gn "$RUN_USER")"

# Create .venv if it doesn't exist
if [ ! -d "$REPO_DIR/.venv" ]; then
    echo "Creating .venv..."
    sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"
fi

echo "Installing dependencies..."
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

echo "Writing unit file to $UNIT_FILE..."
cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=TheEyeBeta Data API
After=network.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${REPO_DIR}
Environment="PATH=${REPO_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=${REPO_DIR}/scripts/run_production.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling service..."
systemctl enable "$SERVICE_NAME"

echo "Restarting service..."
systemctl restart "$SERVICE_NAME"

echo ""
echo "Service installed and started."
echo "Logs: sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "Useful commands:"
echo "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
echo "  Start:   sudo systemctl start ${SERVICE_NAME}"
echo "  Restart: sudo systemctl restart ${SERVICE_NAME}"
echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
