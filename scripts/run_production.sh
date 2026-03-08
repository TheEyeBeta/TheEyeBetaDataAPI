#!/usr/bin/env bash
set -euo pipefail

api_host_override="${API_HOST:-}"
api_port_override="${API_PORT:-}"
gunicorn_workers_override="${GUNICORN_WORKERS:-}"
python_bin="${PYTHON_BIN:-python3}"
if ! command -v "${python_bin}" >/dev/null 2>&1; then
  python_bin="python"
fi
if ! command -v "${python_bin}" >/dev/null 2>&1; then
  echo "Python interpreter not found. Set PYTHON_BIN or install python3."
  exit 1
fi

# Load .env safely without shell-evaluating values like JSON.
if [ -f ".env" ]; then
  eval "$(
    "${python_bin}" - <<'PY'
from dotenv import dotenv_values
import shlex

for key, value in dotenv_values(".env").items():
    if value is None:
        continue
    print(f"export {key}={shlex.quote(value)}")
PY
  )"
fi

if [ -n "${api_host_override}" ]; then
  API_HOST="${api_host_override}"
fi
if [ -n "${api_port_override}" ]; then
  API_PORT="${api_port_override}"
fi
if [ -n "${gunicorn_workers_override}" ]; then
  GUNICORN_WORKERS="${gunicorn_workers_override}"
fi

exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${GUNICORN_WORKERS:-2}" \
  -b "${API_HOST:-127.0.0.1}:${API_PORT:-7000}" \
  --access-logfile - \
  --error-logfile -
