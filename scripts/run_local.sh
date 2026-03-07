#!/usr/bin/env bash
set -euo pipefail

api_host_override="${API_HOST:-}"
api_port_override="${API_PORT:-}"

if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

if [ -n "${api_host_override}" ]; then
  API_HOST="${api_host_override}"
fi
if [ -n "${api_port_override}" ]; then
  API_PORT="${api_port_override}"
fi

python -m uvicorn app.main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-7000}" --reload
