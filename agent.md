# TheEyeBetaDataAPI — Agent Instructions

## Starting the App

When asked to start, run, or restart the app, always use:

```bash
bash scripts/run_production.sh
```

- The API binds to `127.0.0.1:7000`
- Confirm healthy: `curl -sf http://127.0.0.1:7000/health`

If the launchd service is installed (production Mac Mini), restart it with:

```bash
launchctl kickstart -k gui/$(id -u)/com.theeyebeta.dataapi
```

To tail logs on the Mac Mini:

```bash
tail -f ~/Library/Logs/theeyebeta-dataapi/stdout.log
```

## One-Time Setup on Mac Mini

Run this once to install the app as a background service that starts on boot:

```bash
bash scripts/install_service.sh
```

That's it. The app will start automatically on reboot and restart itself if it crashes.

## Auto-Deploy Pipeline

Pushes to `main` trigger automatic deployment via GitHub Actions:

1. CI runs all tests (`pytest`) on `ubuntu-latest`
2. If tests pass, the `deploy` job runs on the **self-hosted runner** (Mac Mini)
3. `scripts/deploy.sh` pulls latest `main`, updates pip dependencies, restarts the launchd service, and validates `/health`

### One-Time Runner Setup (Mac Mini)

Go to: **GitHub → repo Settings → Actions → Runners → New self-hosted runner → macOS**

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
