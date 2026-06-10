# TheEyeBetaDataAPI — Agent Instructions

## Starting the App

When asked to start all native services (Data API :7000 + TheEyeBetaLocal engine/API/Trask + tunnel), use:

```bash
bash scripts/start_all_native.sh
```

This also runs `scripts/sync_tunnel.sh` and starts the watchdog. **No Docker** for app ports.

## Cloudflare Tunnel (TheEyeBeta2025)

Public URLs:

- `https://dataapi.theeyebeta.store` → `127.0.0.1:7000` (this repo)
- `https://api.theeyebeta.store` → `127.0.0.1:8000` (TheEyeBetaLocal)

```bash
bash scripts/sync_tunnel.sh              # no sudo — DNS + remote ingress + fallback connector
sudo bash scripts/fix_tunnel.sh          # permanent systemd fix (required once if dataapi 502)
```

Full guide: `docs/TUNNEL_RUNBOOK.md`. Canonical config: `deploy/cloudflared-config.yml`.

When asked to start or restart only the Data API, use:

```bash
bash scripts/run_production.sh
```

- The API binds to `127.0.0.1:7000`
- Confirm healthy: `curl -sf http://127.0.0.1:7000/health`

If the systemd service is installed (production Linux server), restart it with:

```bash
sudo systemctl restart theeyebeta-dataapi
```

To tail logs on the Linux server:

```bash
sudo journalctl -u theeyebeta-dataapi -f
```

## One-Time Setup on Linux Server

Run this once to install the app as a background service that starts on boot:

```bash
sudo bash scripts/install_service.sh
```

That's it. The app will start automatically on reboot and restart itself if it crashes.

## Auto-Deploy Pipeline

Pushes to `main` trigger automatic deployment via GitHub Actions:

1. CI runs all tests (`pytest`) on `ubuntu-latest`
2. If tests pass, the `deploy` job runs on the **self-hosted runner** (Linux server)
3. `scripts/deploy.sh` pulls latest `main`, updates pip dependencies, restarts the systemd service, and validates `/health`

### One-Time Runner Setup (Linux Server)

Go to: **GitHub → repo Settings → Actions → Runners → New self-hosted runner → Linux**

Run the commands GitHub provides, then:

```bash
cd actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
```

## Project Layout

```
app/          FastAPI application (routes, services, auth, db)
scripts/      Operational scripts (deploy, install_service, bootstrap, rotate secrets)
deploy/       Nginx config and DB schema
tests/        Pytest test suite
pytest.ini
```

## Environment

Requires a `.env` file at the repo root (never committed). Generate with:

```bash
python scripts/bootstrap_local_env.py --database-url "postgresql+psycopg://..."
```
