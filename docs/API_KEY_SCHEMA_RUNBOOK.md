# API Key Schema Runbook (PostgreSQL / pgAdmin4)

This runbook defines the DB-backed API key model for multi-app service access.

## 1) Apply schema

Use pgAdmin Query Tool (or `psql`) against:

`postgresql://postgres:***@localhost:5432/TheEyeBetaDataAPI`

Run:

```sql
-- Execute full file contents:
-- deploy/iam_api_key_schema.sql
```

## 2) What this creates

- `iam.client_types`
  - Allowed backend app categories (`mobile-backend`, `vi-backend`, `trade-engine`, `admin-tool`).
- `iam.client_type_default_scopes`
  - Default scopes per app type (auto-grant policy).
- `iam.service_clients`
  - Service principal identities.
- `iam.service_client_scopes`
  - Effective granted scopes.
- `iam.service_client_secrets`
  - Hashed API keys (bcrypt), rotation metadata, last-used tracking.
- `iam.service_client_events`
  - Audit trail for create/issue/revoke actions.

## 3) Automatic grant logic

When a client is created in `iam.service_clients`, a trigger auto-inserts default scopes from `iam.client_type_default_scopes`.

## 4) Provision a new client + API key (one command)

```sql
SELECT *
FROM iam.provision_service_client(
  'vi-backend-prod',
  'VI Railway Backend (Prod)',
  'vi-backend',
  'production',
  'admin-user',
  NULL,
  '{"owner":"railway","team":"vi"}'::jsonb
);
```

Returns:

- `client_id`
- `granted_scopes`
- `secret_prefix`
- `api_key` (shown once, store securely)

CLI alternative from repo:

```bash
python scripts/provision_db_service_client.py \
  --client-id vi-backend-prod \
  --display-name "VI Railway Backend (Prod)" \
  --app-type vi-backend \
  --allow-existing
```

## 5) Issue/rotate key for existing client

```sql
SELECT *
FROM iam.issue_service_api_key(
  'vi-backend-prod',
  'admin-user',
  now() + interval '180 days'
);
```

## 6) Revoke/disable client

```sql
UPDATE iam.service_clients
SET
  is_active = false,
  revoked_at = now(),
  revoked_reason = 'decommissioned',
  updated_by = 'admin-user'
WHERE client_id = 'vi-backend-prod';
```

Disabling a client auto-revokes all active secrets via trigger.

## 7) Inspect active clients/scopes

```sql
SELECT c.client_id, c.app_type, c.environment, c.is_active, array_agg(s.scope ORDER BY s.scope) AS scopes
FROM iam.service_clients c
LEFT JOIN iam.service_client_scopes s ON s.client_uuid = c.client_uuid
GROUP BY c.client_id, c.app_type, c.environment, c.is_active
ORDER BY c.client_id;
```

## 8) Important integration note

API runtime service-auth mode is controlled by `SERVICE_CLIENT_AUTH_MODE`:

- `database` (recommended): validate service credentials from `iam.service_client_secrets`.
- `environment`: legacy `SERVICE_CLIENTS_JSON` only.
- `hybrid`: database first, fallback to `SERVICE_CLIENTS_JSON`.

For production DB-backed auth, set:

```env
SERVICE_CLIENT_AUTH_MODE=database
```
