#!/usr/bin/env bash
# One-time setup: installs the app as a systemd service.
# Run once: sudo bash scripts/install_service.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="theeyebeta-dataapi"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
RUN_USER="${SUDO_USER:-$(whoami)}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: sudo bash scripts/install_service.sh"
    exit 1
fi

# Create .venv as the actual user
echo "Creating .venv..."
sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"

echo "Installing dependencies..."
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

echo "Writing service file to $SERVICE_FILE..."
cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=TheEyeBeta Data API
After=network.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${REPO_DIR}/scripts/run_production.sh
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "Service installed and started."
echo ""
echo "Useful commands:"
echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
echo "  Restart: sudo systemctl restart ${SERVICE_NAME}"
echo "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
