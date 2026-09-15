# Ops hardening notes (Phase 6) — DataAPI IAM

Companion to [`PRODUCTION_RUNBOOK.md`](PRODUCTION_RUNBOOK.md) and
[`SECRET_ROTATION_RUNBOOK.md`](SECRET_ROTATION_RUNBOOK.md). No new cloud
dependencies; uses the existing Prometheus instrumentator + loopback topology.

## Network / firewall expectations

| Listener | Bind | Notes |
|---|---|---|
| DataAPI | `127.0.0.1:7000` | Public only via Cloudflare Tunnel |
| Postgres | `127.0.0.1:5432` | Must remain loopback-only |
| admin-service | `127.0.0.1:7200` | Loopback-only; DataAPI gateway target |
| Hosted terminal | `127.0.0.1:8080` | Tunnel hostname `admin.theeyebeta.store` |

Confirm on the Linux host (record actual rules in the on-host runbook if they
differ):

```bash
ss -lntp | egrep ':5432|:7000|:7200|:8080'
sudo ufw status verbose   # or: sudo iptables -L -n
```

Postgres and `:7200` must not appear on a public interface.

## Monitoring (existing Prometheus stack)

`prometheus-fastapi-instrumentator` already exposes `/metrics` on DataAPI.

### Committed alert rules

Rules live in [`deploy/prometheus/rules/dataapi_auth.yml`](../deploy/prometheus/rules/dataapi_auth.yml)
and are loaded by [`deploy/prometheus.yml`](../deploy/prometheus.yml) via:

```yaml
rule_files:
  - /etc/prometheus/rules/*.yml
```

`docker-compose.yml` mounts `./deploy/prometheus/rules` at `/etc/prometheus/rules`.

| Alert | Intent |
|---|---|
| `DataAPIAuthFailureSpike` | Brute force / broken clients on `/api/v1/auth/*` (401/403) |
| `DataAPIAuthEndpoint5xx` | Token endpoint outage (5xx on `/api/v1/auth/*`) |
| `DataAPIRefreshAuthFailures` | Coarse proxy for refresh reuse / misconfig (`/api/v1/auth/refresh` 401s) |

Reload after deploying rule changes (compose stack):

```bash
curl -X POST http://127.0.0.1:9090/-/reload
# then open http://127.0.0.1:9090/alerts
```

Native prod today is systemd + tunnel. On `the-eye-beta-server` (probed
2026-09-14), the **live** Prometheus container (`theeyebeta-prometheus-1`)
mounts config from **TheEyeBetaProd**
(`infra/prometheus/prometheus.yml` + `infra/prometheus/alerts.yml`), not from
this repo's `deploy/prometheus.yml`. Grafana on `:3000` was not healthy at
probe time.

Therefore:

1. Rules in this repo are the source of truth for DataAPI auth alerts.
2. To make them fire in the live stack, either reload this compose stack with
   the mounts above, **or** (preferred on the current host) copy/merge
   `deploy/prometheus/rules/dataapi_auth.yml` into the Prod prometheus rules
   path in a separate, explicit change — do not silently edit Prod from a
   DataAPI task without go-ahead.
3. After load: `curl -X POST http://127.0.0.1:9090/-/reload` and check
   `http://127.0.0.1:9090/alerts`.

Until a dedicated refresh-reuse counter exists, also grep journald:

```bash
journalctl --user -u theeyebeta-dataapi --since "1 hour ago" | grep -F "Refresh token already used or revoked"
```


## Rotation cadence

| Secret / key | Cadence | Procedure |
|---|---|---|
| DataAPI JWT signing (`JWT_SECRET` / `JWT_SIGNING_SECRET_*`) | Every **90 days** | [`SECRET_ROTATION_RUNBOOK.md`](SECRET_ROTATION_RUNBOOK.md) |
| `USER_JWT_SECRET` (if not JWKS) | Every **90 days** | Same runbook §B |
| Service client secrets | On compromise or yearly | `provision_db_service_client.py --allow-existing` |
| User API keys | Review monthly | `scripts/report_expiring_user_api_keys.py --within-days 30` |

## Backups

Confirm the host Postgres backup job includes the **`iam`** schema (service
clients, user API keys, refresh tokens, auth audit). If the existing backup is
full-cluster (`pg_dump` / snapshots of `TheEyeBeta2025Live`), `iam` is already
covered — document the job name and retention here on the host. If backups are
schema-filtered, add `iam` explicitly before enabling refresh tokens in prod.
