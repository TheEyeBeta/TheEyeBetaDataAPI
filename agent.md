# TheEyeBetaDataAPI — Agent Instructions

## Starting the App

When asked to start, run, or restart the app, always use:

```bash
docker compose up --build -d
```

- API runs on port `7000` (`127.0.0.1:7000`)
- Nginx reverse proxy runs on `127.0.0.1:80`
- Confirm healthy: `curl -sf http://127.0.0.1:7000/health`

To stop: `docker compose down`
To tail logs: `docker compose logs -f dataapi`

## Auto-Deploy Pipeline

Pushes to `main` trigger automatic deployment:

1. GitHub Actions runs `pytest` on `ubuntu-latest`
2. If tests pass, the `deploy` job runs on the self-hosted runner (Mac Mini)
3. `scripts/deploy.sh` pulls latest `main`, rebuilds containers, and validates `/health`

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
scripts/      Operational scripts (deploy, bootstrap, rotate secrets)
deploy/       Nginx config and DB schema
tests/        Pytest test suite
docker-compose.yml
Dockerfile
pytest.ini
```

## Environment

Requires a `.env` file (never committed). Generate with:

```bash
python scripts/bootstrap_local_env.py --database-url "postgresql+psycopg://..."
```
