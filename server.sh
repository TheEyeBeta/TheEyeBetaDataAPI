#!/usr/bin/env bash
# server.sh — start / stop the API on port 7000
#
#   ./server.sh          → toggle (start if stopped, stop if running)
#   ./server.sh start    → start in background
#   ./server.sh stop     → stop
#   ./server.sh restart  → stop then start
#   ./server.sh status   → print current state
#   ./server.sh logs     → tail the live log

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${REPO}/.server.pid"
LOG_FILE="${REPO}/server.log"
PORT=7000

# ── resolve python ───────────────────────────────────────────────────────────
if [ -x "${REPO}/.venv/bin/python" ]; then
  PYTHON="${REPO}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

# ── helpers ──────────────────────────────────────────────────────────────────
_is_running() {
  [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null
}

_load_env() {
  if [ -f "${REPO}/.env" ]; then
    eval "$(
      "${PYTHON}" - <<'PY'
from dotenv import dotenv_values
import shlex, os
for k, v in dotenv_values(os.path.join(os.environ.get("REPO", "."), ".env")).items():
    if v is not None:
        print(f"export {k}={shlex.quote(v)}")
PY
    )"
  fi
}

# ── commands ─────────────────────────────────────────────────────────────────
start() {
  if _is_running; then
    echo "Already running  (PID $(cat "${PID_FILE}"))  →  http://0.0.0.0:${PORT}"
    return
  fi

  cd "${REPO}"
  REPO="${REPO}" _load_env

  nohup "${PYTHON}" -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    >> "${LOG_FILE}" 2>&1 &

  echo $! > "${PID_FILE}"

  # give it a moment then confirm
  sleep 1
  if _is_running; then
    echo "Started  (PID $(cat "${PID_FILE}"))  →  http://0.0.0.0:${PORT}"
    echo "Logs:    ${LOG_FILE}"
  else
    echo "ERROR: failed to start — check ${LOG_FILE}" >&2
    rm -f "${PID_FILE}"
    exit 1
  fi
}

stop() {
  if ! _is_running; then
    echo "Not running"
    rm -f "${PID_FILE}"
    return
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  kill "${pid}"
  rm -f "${PID_FILE}"
  echo "Stopped  (was PID ${pid})"
}

status() {
  if _is_running; then
    echo "Running  (PID $(cat "${PID_FILE}"))  →  http://0.0.0.0:${PORT}"
  else
    echo "Not running"
  fi
}

logs() {
  if [ ! -f "${LOG_FILE}" ]; then
    echo "No log file yet (${LOG_FILE})"
    exit 0
  fi
  exec tail -f "${LOG_FILE}"
}

# ── dispatch ─────────────────────────────────────────────────────────────────
case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  logs)    logs ;;
  "")
    if _is_running; then stop; else start; fi
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
