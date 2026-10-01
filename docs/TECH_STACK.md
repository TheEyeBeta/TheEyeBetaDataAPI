# Tech Stack — One Page

**What it is:** TheEyeBetaDataAPI is the single, secured doorway through which
The Eye's products read financial data. Products never touch the database
directly; they ask this service, which checks who they are and what they are
allowed to see.

| Layer | Choice | In plain terms |
|---|---|---|
| **Language** | Python 3.12 | Mainstream, easy to hire for; one language for the whole service |
| **Web framework** | FastAPI (on Starlette), served by gunicorn + uvicorn | Current standard for Python APIs; validates every request and response automatically |
| **Database** | PostgreSQL, accessed through SQLAlchemy 2 + psycopg 3 | Industry-standard database. Market data is read-only here; a separate `iam` area stores logins, keys and audit records |
| **Authentication** | Signed tokens (JWT via PyJWT), hashed client secrets and API keys (bcrypt in PostgreSQL), optional mutual-TLS | Each caller gets a short-lived pass that lists exactly what it may read |
| **Hosting** | One Linux server running the API as a background service (systemd); public access through Cloudflare Tunnel | No open inbound ports: Cloudflare handles HTTPS and forwards traffic privately |
| **CI/CD** | GitHub Actions: unit, PostgreSQL integration and Prod-schema contract tests, lint/format, type checking, dependency audit, secret scan; a self-hosted runner deploys a push to `main` only after all of them pass | Deploys the tested commit, checks database health, rolls back on failure, then runs an Admin end-to-end check |
| **Dependency hygiene** | Pinned versions, `pip-audit` on every push, Dependabot weekly | Known-vulnerable libraries are caught before they ship |
| **Monitoring** | `/health` endpoint; Prometheus metrics at `/metrics`; Grafana dashboard and alert rules committed; logs in journald | Uptime and error-rate visibility (wiring the repo's alerts to the live Prometheus is an open item) |
| **Optional services** | OpenAI (AI-written advisor answers; falls back to plain data summaries), Redis (shared rate limiting) | Both can be switched off without breaking the API |
| **Client library** | TypeScript package (`packages/theeyebeta-dataapi-plugin`) | Lets front-end apps call the API with typed helpers |

**Scale today (2026-10-01):** about 19k lines of Python, 59 documented API
operations, 460 automated tests: 41 against a real PostgreSQL and 70 that run
every data route against TheEyeBetaProd's schema. Two production consumers:
Lens (AI financial advisor) and the TheEyeBetaAdmin terminal.

**Where to look next:** [Architecture](ARCHITECTURE.md) ·
[Known technical debt](TECH_DEBT.md) · [API reference](API_REFERENCE.md)
