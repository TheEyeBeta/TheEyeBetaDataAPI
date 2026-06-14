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

---

# End-user API keys

Service clients (above) are backend-to-backend principals. End users are humans
with their own identity and personal keys, modeled in a parallel set of tables.

## A) Apply schema

Run `deploy/iam_user_api_key_schema.sql` **after** `deploy/iam_api_key_schema.sql`
(it reuses `iam.set_updated_at()`).

Creates:

- `iam.users` — end-user identities, keyed by unique lowercased `email`.
- `iam.user_api_keys` — personal keys. Stores a bcrypt hash (pgcrypto `crypt`),
  a globally unique 16-hex `key_prefix` for O(1) Bearer lookup, per-key `scopes`,
  expiry, revocation, and last-used tracking.
- `iam.user_api_key_events` — audit trail (`key_issued`, `key_rejected`, `user_disabled`).

## B) Key format

Issued keys look like `teb_uk_<16hex>_<secret>` (the `teb_uk_` tag distinguishes
them from service keys `teb_sk_`). The runtime reads the fixed 16-char prefix,
looks the row up by `key_prefix`, then verifies with `crypt(:raw_key, key_hash)`.

## C) Provision a user + key

```sql
SELECT *
FROM iam.provision_user_api_key(
  'trader@example.com',
  'Jane Trader',
  'Trading bot',
  ARRAY['market:read','portfolio:read']::text[],
  'admin-user',
  'pro',
  now() + interval '90 days'
);
```

CLI alternative from repo:

```bash
python scripts/provision_user_api_key.py \
  --email trader@example.com \
  --display-name "Jane Trader" \
  --key-name "Trading bot" \
  --scope market:read --scope portfolio:read \
  --plan pro --expires-days 90
```

Both return `api_key` once — store it securely; only the hash is persisted.

## D) Issue/rotate a key for an existing user

```sql
SELECT *
FROM iam.issue_user_api_key(
  '<user_uuid>',
  'CI runner',
  ARRAY['market:read']::text[],
  'admin-user',
  NULL
);
```

## E) Revoke

```sql
-- Single key:
UPDATE iam.user_api_keys
SET is_active = false, revoked_at = now(), revoked_reason = 'rotated'
WHERE key_uuid = '<key_uuid>';

-- All of a user's keys (disabling the user auto-revokes via trigger):
UPDATE iam.users SET is_active = false, updated_by = 'admin-user'
WHERE email = 'trader@example.com';
```

## F) Calling the API

Send the key as a bearer token — no `/auth/service-token` exchange needed:

```
GET /api/v1/market-data/quotes?ticker=AAPL
Authorization: Bearer teb_uk_<16hex>_<secret>
```

`get_principal` detects the `teb_uk_` prefix, validates against
`iam.user_api_keys`, and yields a `user:<user_uuid>` principal carrying the
key's scopes. All other endpoints enforce scopes exactly as they do for service
tokens. Validation failures return a generic `401 Invalid API key`; the specific
reason (revoked/expired/inactive) is recorded in `iam.user_api_key_events`.

## G) Runtime grants

The API role (from `DATABASE_URL`) needs, beyond its service-client grants:

```sql
GRANT SELECT ON iam.users TO api_service;
GRANT SELECT, UPDATE ON iam.user_api_keys TO api_service;  -- UPDATE: last_used_* only
GRANT INSERT ON iam.user_api_key_events TO api_service;
GRANT USAGE ON SEQUENCE iam.user_api_key_events_event_id_seq TO api_service;
```

## H) Not included (deliberate)

Self-service key generation from a logged-in user session (`POST /auth/api-keys`
behind a user JWT) is **not** wired up, because it requires deciding how your
OIDC `sub` maps onto `iam.users.user_uuid`. The DB function, verification, and
provisioning CLI are all ready; add the HTTP endpoint once that mapping is defined.
