# TheEyeBetaDataAPI

Internet-exposed FastAPI service for read-only market-data context and AI-assisted responses.

## Runtime and entrypoints

- Framework: FastAPI + Uvicorn/Gunicorn
- App entrypoint: `app.main:app`
- Development run command: `bash scripts/run_local.sh`
- Production run command: `bash scripts/run_production.sh`
- Default host/port for host deployment: `127.0.0.1:7000`

## API endpoints

- `GET /`
- `GET /health`
- `POST /api/v1/auth/token` (requires `X-API-Key`)
- `GET /api/v1/context` (requires API key or Bearer JWT)
- `POST /api/v1/chat` (requires API key or Bearer JWT)

## Quick start

```bash
cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with real values
bash scripts/run_local.sh
```

Swagger docs: `http://127.0.0.1:7000/docs`

## Required environment variables

Minimum required values:

- `DATABASE_URL`
- `API_KEY` (24+ chars)
- `JWT_SECRET` (24+ chars)

Recommended production values:

- `ENVIRONMENT=production`
- `DEBUG=false`
- `API_HOST=127.0.0.1`
- `API_PORT=7000`
- `TRUST_PROXY_HEADERS=true` (when behind Cloudflare Tunnel/reverse proxy)
- `TRUSTED_HOSTS=api.theeyebeta.store,dataapi.theeyebeta.store,127.0.0.1,localhost`
- `CORS_ORIGINS=https://theeyebeta.store`
- `RATE_LIMIT_PER_MINUTE=120`

## Cloudflare Tunnel mapping (recommended)

Run this API on loopback and point Cloudflare Tunnel to:

- `http://127.0.0.1:7000`

Example `cloudflared` ingress:

```yaml
ingress:
  - hostname: api.theeyebeta.store
    service: http://127.0.0.1:7000
  - hostname: dataapi.theeyebeta.store
    service: http://127.0.0.1:7000
  - service: http_status:404
```

## Verification

Local:

```bash
curl -s http://127.0.0.1:7000/
curl -s http://127.0.0.1:7000/health
```

Authenticated context request:

```bash
curl -s -H "X-API-Key: $API_KEY" "http://127.0.0.1:7000/api/v1/context?ticker=AAPL"
```

Remote smoke test (after Tunnel is configured):

```bash
API_BASE_URL="https://api.theeyebeta.store" API_KEY="$API_KEY" bash scripts/verify_remote_access.sh
```

## TypeScript frontend tester

The test dashboard is now TypeScript-based:

- Server source: `frontend/src/server.ts`
- Browser source: `frontend/src/client.ts`

Run on any computer:

```bash
cd frontend
npm install
npm start
```

This builds TypeScript and starts the tester at `http://localhost:3000`.

## Reusable plugin for other repos

Use the plugin package at `packages/theeyebeta-dataapi-plugin`:

```bash
cd packages/theeyebeta-dataapi-plugin
npm install
npm run build
```

Then in another repo:

```bash
npm install ../TheEyeBetaDataAPI/packages/theeyebeta-dataapi-plugin
```

or after publishing:

```bash
npm install @theeyebeta/dataapi-plugin
```

## GitHub repo creation

`gh` is required and must be authenticated first:

```bash
gh auth login
bash scripts/create_github_repo.sh TheEyeBetaDataAPI public
```

## Docker compose (optional)

`docker compose up --build -d` starts:

- `dataapi` on loopback `127.0.0.1:7000`
- `nginx` on loopback `127.0.0.1:80` proxying to dataapi

For Cloudflare Tunnel, direct origin to `http://127.0.0.1:7000` is preferred.
