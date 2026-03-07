#!/usr/bin/env bash
set -euo pipefail

api_host_override="${API_HOST:-}"
api_port_override="${API_PORT:-}"
gunicorn_workers_override="${GUNICORN_WORKERS:-}"

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
if [ -n "${gunicorn_workers_override}" ]; then
  GUNICORN_WORKERS="${gunicorn_workers_override}"
fi

exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${GUNICORN_WORKERS:-2}" \
  -b "${API_HOST:-127.0.0.1}:${API_PORT:-7000}" \
  --access-logfile - \
  --error-logfile -
