# TheEyeBetaDataAPI — Claude Instructions

## Starting the App

When asked to start, run, or restart the app, **always** use Docker Compose on port 7000:

```bash
docker compose up --build -d
```

- The API binds to `127.0.0.1:7000`
- Nginx reverse proxy runs on `127.0.0.1:80`
- Verify it's healthy: `curl -sf http://127.0.0.1:7000/health`

To stop: `docker compose down`
To view logs: `docker compose logs -f dataapi`

## Auto-Deploy Pipeline

Pushes to `main` trigger automatic deployment via GitHub Actions:

1. CI runs all tests (`pytest`) on `ubuntu-latest`
2. If tests pass, the `deploy` job runs on the **self-hosted runner** (Mac Mini)
3. The runner executes `scripts/deploy.sh` which:
   - Pulls latest `main`
   - Rebuilds and restarts containers (`docker compose up --build -d`)
   - Waits up to 60s for `/health` to pass before declaring success

### One-Time Runner Setup (Mac Mini)

The self-hosted runner must be registered once. Go to:
**GitHub → repo Settings → Actions → Runners → New self-hosted runner → macOS**

Then run the commands GitHub provides, followed by:

```bash
cd actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
```

This installs the runner as a launchd service so it survives reboots.

## Project Layout

```
app/          FastAPI application (routes, services, auth, db)
scripts/      Operational scripts (deploy, bootstrap, rotate secrets)
deploy/       Nginx config and DB schema
tests/        Pytest test suite
docker-compose.yml
Dockerfile
pytest.ini
```

## Environment

- Requires a `.env` file (never committed). Generate one with:
  ```bash
  python scripts/bootstrap_local_env.py --database-url "postgresql+psycopg://..."
  ```
- Production runs behind a Cloudflare Tunnel — no ports are directly exposed to the internet.
