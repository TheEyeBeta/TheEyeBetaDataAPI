# TheEyeBetaDataAPI — Agent Instructions

## Starting / Stopping the API (the simple way)

`server.sh` at the repo root is the one script you need.
**It runs in the background — no editor, no terminal, no Cursor needs to stay open.**

```bash
./server.sh          # toggle: start if stopped, stop if running
./server.sh start    # start on 0.0.0.0:7000 (background, survives terminal close)
./server.sh stop     # stop
./server.sh restart  # stop + start
./server.sh status   # is it running?
./server.sh logs     # tail the live log (server.log)
```

The process runs via `nohup` and writes its PID to `.server.pid`.
Close your terminal, close Cursor, disconnect SSH — the API keeps running.

To confirm it's healthy after starting:

```bash
curl http://127.0.0.1:7000/health
```

---

## Starting All Native Services (API + tunnel + other engines)

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

## systemd (if installed as a Linux service)

If the systemd service has been installed (`sudo bash scripts/install_service.sh`), use:

```bash
sudo systemctl restart theeyebeta-dataapi   # restart
sudo systemctl status  theeyebeta-dataapi   # check
sudo journalctl -u theeyebeta-dataapi -f    # tail logs
```

The systemd service survives reboots automatically. Use `server.sh` if systemd is not set up.

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
