# TheEyeBetaDataAPI Production Runbook (Cloudflare Tunnel)

This runbook is the deployment baseline for exposing the API through Cloudflare Tunnel from a home server.

## 1) Architecture

- Public ingress: Cloudflare edge HTTPS
- Origin service on home server: `http://127.0.0.1:7000`
- App runtime: Gunicorn + Uvicorn worker (`app.main:app`)
- Database: private PostgreSQL using read-only credentials

## 2) Database hardening

Run `deploy/db_security.sql` as a privileged DB user, then use only the read-only role in `DATABASE_URL`.

## 3) Production environment

Create `.env` from `.env.example` and set real values:

```dotenv
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql+psycopg://api_readonly:REPLACE_ME@127.0.0.1:5432/theeyebeta
API_KEY=REPLACE_WITH_STRONG_RANDOM_API_KEY_MIN_24_CHARS
JWT_SECRET=REPLACE_WITH_STRONG_RANDOM_JWT_SECRET_MIN_24_CHARS
API_HOST=127.0.0.1
API_PORT=7000
TRUST_PROXY_HEADERS=true
TRUSTED_HOSTS=api.theeyebeta.store,dataapi.theeyebeta.store,127.0.0.1,localhost
CORS_ORIGINS=https://theeyebeta.store
RATE_LIMIT_PER_MINUTE=120
```

## 4) Start the API

```bash
cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
source .venv/bin/activate
bash scripts/run_production.sh
```

## 5) Cloudflare Tunnel config

Set both hostnames to the same local origin:

```yaml
ingress:
  - hostname: api.theeyebeta.store
    service: http://127.0.0.1:7000
  - hostname: dataapi.theeyebeta.store
    service: http://127.0.0.1:7000
  - service: http_status:404
```

## 6) Verification

Local checks:

```bash
ss -ltnp | rg ':7000'
curl -s http://127.0.0.1:7000/
curl -s http://127.0.0.1:7000/health
```

Public checks:

```bash
curl -s https://api.theeyebeta.store/
curl -s https://dataapi.theeyebeta.store/health
curl -s -H "X-API-Key: ${API_KEY}" "https://api.theeyebeta.store/api/v1/context?ticker=AAPL"
```

## 7) Operational notes

- Do not expose the API directly on public interfaces.
- Keep `TRUST_PROXY_HEADERS=true` only when ingress is Cloudflare Tunnel or a trusted reverse proxy.
- Rotate `API_KEY` and `JWT_SECRET` regularly.
- If secrets were ever committed, rotate immediately before go-live.
