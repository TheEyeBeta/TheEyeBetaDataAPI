#!/usr/bin/env bash
# Push deploy/cloudflared-config.yml to Cloudflare as the tunnel's remote ingress
# and link DNS. OPERATOR ACTION ONLY: requires TUNNEL_CHANGE_APPROVED=yes.
# Never called by the watchdog or start scripts.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANONICAL_CONFIG="$REPO_DIR/deploy/cloudflared-config.yml"
ADMIN_TERMINAL_HEALTH_URL="${ADMIN_TERMINAL_HEALTH_URL:-http://127.0.0.1:8080/healthz}"
RUNTIME_CONFIG="$REPO_DIR/.runtime-logs/cloudflared-native.yml"
TUNNEL_NAME="${TUNNEL_NAME:-my-api}"
CLOUDFLARED_SESSION="${CLOUDFLARED_SESSION:-cloudflared-native}"
LOG_DIR="$REPO_DIR/.runtime-logs"

log() { echo "[sync-tunnel] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

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
  echo "    TUNNEL_CHANGE_APPROVED=yes $0"
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

mkdir -p "$LOG_DIR"
cp "$CANONICAL_CONFIG" "$RUNTIME_CONFIG"

if ! command -v cloudflared >/dev/null 2>&1; then
  log "cloudflared not installed — skipping tunnel sync"
  exit 1
fi

log "Linking DNS hostnames to tunnel $TUNNEL_NAME"
for host in api.theeyebeta.store dataapi.theeyebeta.store dataapiprod.theeyebeta.store; do
  if cloudflared tunnel route dns -f "$TUNNEL_NAME" "$host" >>"$LOG_DIR/sync-tunnel.log" 2>&1; then
    log "  DNS OK: $host"
  else
    log "  DNS skipped or already set: $host"
  fi
done

log "Pushing remote ingress config to Cloudflare"
REPO_DIR="$REPO_DIR" python3 - <<'PY' | tee -a "$LOG_DIR/sync-tunnel.log"
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

repo = Path(os.environ["REPO_DIR"])
text = (repo / "deploy" / "cloudflared-config.yml").read_text()
tunnel_id = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("tunnel:"))
ingress = []
for block in text.split("- hostname:")[1:]:
    lines = block.strip().splitlines()
    hostname = lines[0].strip()
    service = None
    origin_req = {}
    for line in lines[1:]:
        s = line.strip()
        if s.startswith("service:"):
            service = s.split(":", 1)[1].strip()
        if s.startswith("connectTimeout:"):
            origin_req["connectTimeout"] = int(s.split(":", 1)[1].strip().rstrip("s"))
    entry = {"hostname": hostname, "service": service}
    if origin_req:
        entry["originRequest"] = origin_req
    ingress.append(entry)
ingress.append({"service": "http_status:404"})

token_pem = (Path.home() / ".cloudflared" / "cert.pem").read_text()
b64 = token_pem.split("-----BEGIN ARGO TUNNEL TOKEN-----\n")[1].split("\n-----END")[0].replace("\n", "")
payload = json.loads(base64.b64decode(b64))
url = (
    f"https://api.cloudflare.com/client/v4/accounts/{payload['accountID']}"
    f"/cfd_tunnel/{tunnel_id}/configurations"
)
req = urllib.request.Request(
    url,
    data=json.dumps({"config": {"ingress": ingress}}).encode(),
    headers={"Authorization": f"Bearer {payload['apiToken']}", "Content-Type": "application/json"},
    method="PUT",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.load(resp)
        if not result.get("success"):
            print("remote config push failed:", result, file=sys.stderr)
            sys.exit(1)
        print("remote config version:", result["result"]["version"])
except urllib.error.HTTPError as exc:
    print(exc.read().decode(), file=sys.stderr)
    sys.exit(1)
PY

system_config_ok=false
if [[ -r /etc/cloudflared/config.yml ]] \
   && grep -q '127.0.0.1:7000' /etc/cloudflared/config.yml 2>/dev/null \
   && grep -q '127.0.0.1:8000' /etc/cloudflared/config.yml 2>/dev/null; then
  system_config_ok=true
  log "System cloudflared config looks correct"
fi

if ! $system_config_ok; then
  log "System /etc/cloudflared/config.yml still stale — starting fallback connector ($CLOUDFLARED_SESSION)"
  log "Permanent fix: sudo bash scripts/fix_tunnel.sh"
  if command -v tmux >/dev/null 2>&1; then
    tmux kill-session -t "$CLOUDFLARED_SESSION" 2>/dev/null || true
    tmux new-session -d -s "$CLOUDFLARED_SESSION" \
      "cloudflared tunnel --config '$RUNTIME_CONFIG' --metrics localhost:20246 run $TUNNEL_NAME"
    cloudflared tunnel cleanup "$TUNNEL_NAME" >>"$LOG_DIR/sync-tunnel.log" 2>&1 || true
  else
    log "tmux not found; install tmux or run: sudo bash scripts/fix_tunnel.sh"
  fi
else
  tmux kill-session -t "$CLOUDFLARED_SESSION" 2>/dev/null || true
  log "Using systemd cloudflared only"
fi

log "Verifying tunnel endpoints"
for url in https://api.theeyebeta.store/health https://dataapi.theeyebeta.store/health https://dataapiprod.theeyebeta.store/health; do
  if curl -sf --max-time 15 "$url" >/dev/null; then
    log "  OK $url"
  else
    log "  FAIL $url (local services may still be starting)"
  fi
done
