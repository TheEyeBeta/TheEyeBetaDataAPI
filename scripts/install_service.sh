#!/usr/bin/env bash
# One-time setup: installs the app as a --user systemd service on Linux.
# Run once with sudo: sudo bash scripts/install_service.sh
#
# This installs a --user unit (~/.config/systemd/user/theeyebeta-dataapi.service),
# not a system one, so it matches how scripts/deploy.sh and the README's
# "Service management" section manage it (systemctl --user ..., never
# sudo systemctl ...). sudo is only needed here to enable linger for the
# target user, so the --user unit survives reboots and runs without an
# active login session; every other step drops back to that user.
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "Error: this script must be run as root (use sudo)." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="theeyebeta-dataapi"

RUN_USER="${SUDO_USER:-}"
if [ -z "$RUN_USER" ] || [ "$RUN_USER" = "root" ]; then
    echo "Error: run this via 'sudo bash scripts/install_service.sh' as the non-root user who should own the service (SUDO_USER was empty or root)." >&2
    exit 1
fi

RUN_UID="$(id -u "$RUN_USER")"
RUN_GROUP="$(id -gn "$RUN_USER")"
USER_UNIT_DIR="$(eval echo "~${RUN_USER}")/.config/systemd/user"
UNIT_FILE="${USER_UNIT_DIR}/${SERVICE_NAME}.service"

run_as_user() {
    sudo -u "$RUN_USER" XDG_RUNTIME_DIR="/run/user/${RUN_UID}" "$@"
}

# Create .venv if it doesn't exist
if [ ! -d "$REPO_DIR/.venv" ]; then
    echo "Creating .venv..."
    sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"
fi

echo "Installing dependencies..."
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

echo "Enabling linger for ${RUN_USER} (lets the --user unit run without an active login session)..."
loginctl enable-linger "$RUN_USER"

echo "Writing user unit file to $UNIT_FILE..."
sudo -u "$RUN_USER" mkdir -p "$USER_UNIT_DIR"
cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=TheEyeBeta Data API (native, user service)
After=network.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
# Bind all interfaces so a reverse proxy/tunnel on this host can reach it.
Environment=API_HOST=0.0.0.0
Environment=API_PORT=7000
ExecStart=${REPO_DIR}/scripts/run_production.sh
Restart=always
RestartSec=3
StartLimitIntervalSec=0
KillMode=mixed
TimeoutStopSec=20

[Install]
WantedBy=default.target
UNIT
chown "${RUN_USER}:${RUN_GROUP}" "$UNIT_FILE"

echo "Reloading and starting the user service..."
run_as_user systemctl --user daemon-reload
run_as_user systemctl --user enable "$SERVICE_NAME"
run_as_user systemctl --user restart "$SERVICE_NAME"

echo ""
echo "Service installed and started as a --user unit for ${RUN_USER}."
echo ""
echo "Useful commands (run as ${RUN_USER}, not root — no sudo):"
echo "  Stop:    systemctl --user stop ${SERVICE_NAME}"
echo "  Start:   systemctl --user start ${SERVICE_NAME}"
echo "  Restart: systemctl --user restart ${SERVICE_NAME}"
echo "  Status:  systemctl --user status ${SERVICE_NAME}"
echo "  Logs:    journalctl --user -u ${SERVICE_NAME} -f"
