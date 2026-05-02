#!/usr/bin/env bash
# One-time setup: installs the app as a macOS launchd service.
# Run once on the Mac Mini: bash scripts/install_service.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_NAME="com.theeyebeta.dataapi"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$HOME/Library/Logs/theeyebeta-dataapi"

mkdir -p "$LOG_DIR"

# Create .venv if it doesn't exist
if [ ! -d "$REPO_DIR/.venv" ]; then
    echo "Creating .venv..."
    python3 -m venv "$REPO_DIR/.venv"
fi

echo "Installing dependencies..."
"$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

echo "Writing plist to $PLIST_DEST..."
cat > "$PLIST_DEST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${REPO_DIR}/scripts/run_production.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${REPO_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/stderr.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLIST

# Load it (unload first if already registered)
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo ""
echo "Service installed and started."
echo "Logs: $LOG_DIR"
echo ""
echo "Useful commands:"
echo "  Stop:    launchctl unload ~/Library/LaunchAgents/${PLIST_NAME}.plist"
echo "  Start:   launchctl load   ~/Library/LaunchAgents/${PLIST_NAME}.plist"
echo "  Restart: launchctl kickstart -k gui/\$(id -u)/${PLIST_NAME}"
echo "  Logs:    tail -f ${LOG_DIR}/stdout.log"
