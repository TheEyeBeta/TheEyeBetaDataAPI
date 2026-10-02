-- Least-privilege runtime role for TheEyeBetaDataAPI.
--
-- Ownership (docs/OWNERSHIP.md; TheEyeBetaProd docs/architecture/ownership-and-contracts.md):
--   * TheEyeBetaProd owns the `theeyebeta` schema, its migrations and the role
--     `api_readonly` (created NOLOGIN by Prod migration 0092 with SELECT on the
--     eight theeyebeta.dataapi_* policy tables). DataAPI never creates, alters,
--     drops or re-grants `api_readonly`. On older hosts `api_readonly` may
--     itself be a LOGIN role created by a previous version of this file; leave
--     it in place, because Prod's migrations depend on it.
--   * TheEyeBetaDataAPI owns the `iam` schema and the login role `api_service`.
--
-- DATABASE_URL connects as `api_service`, never as `postgres`, a schema owner,
-- or `tb_app`. `api_service` gets:
--   1. membership in Prod's `api_readonly`  -> policy reads (contract C1/C2);
--   2. SELECT on the explicit theeyebeta market-data allowlist below
--      -> INTERIM: Prod contract C3 ("which role reads market tables") is open.
--      These grants belong in a Prod migration on `api_readonly`; until then
--      this file applies them. Tables absent on the server are skipped;
--   3. column-scoped iam writes for auth, refresh tokens, audit and account
--      lifecycle. No DELETE/TRUNCATE anywhere, no DDL, no theeyebeta writes.
--
-- Run as a privileged owner AFTER Prod migrations (0092+) and AFTER
-- deploy/iam_api_key_schema.sql, iam_user_api_key_schema.sql,
-- iam_refresh_tokens.sql and iam_auth_audit.sql. Idempotent.
-- Verified by tests/integration (IAM) and tests/contract (Prod schema @ contracts/prod/PROD_SHA).

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_readonly') THEN
        RAISE EXCEPTION 'role api_readonly is missing: apply TheEyeBetaProd migrations (0092_dataapi_policy_control) first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_service') THEN
        CREATE ROLE api_service LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END $$;

-- Set the password out of band (never commit it):
--   ALTER ROLE api_service WITH PASSWORD '<from password manager>';

-- ---------------------------------------------------------------------------
-- 1. Policy reads: inherit whatever Prod grants api_readonly (C1).
-- ---------------------------------------------------------------------------
GRANT api_readonly TO api_service;

-- ---------------------------------------------------------------------------
-- 2. theeyebeta market-data reads (INTERIM, see header). Allowlist, not ALL
--    TABLES: Prod-internal tables (agents, audit_checkpoints, admin users,
--    credentials) stay invisible to the API, including to /api/v1/data/tables.
--    Keep in sync with contracts/prod/objects.txt + host_only_tables.txt.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA theeyebeta TO api_service;
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        -- created by Prod migrations
        'audit_cap_events', 'audit_log', 'corporate_actions', 'exchanges',
        'fixed_income_curve_metrics', 'fixed_income_signals', 'fundamentals',
        'fundamentals_company', 'ind_technical_daily', 'instruments',
        'latest_snapshots', 'macro_indicators', 'market_cap_daily', 'market_news',
        'orders', 'positions', 'prices_daily', 'public_ticker_map', 'sector_daily',
        'trading_calendar', 'trask_components', 'worker_heartbeats',
        -- host-only: exist on production but no Prod migration creates them
        'fund_balance_q', 'fund_cashflow_q', 'fund_income_q', 'ind_risk_daily',
        'ind_valuation_daily', 'price_ticks', 'provider_sync_runs',
        'returns_snapshot_daily', 'ticker_news', 'trask_audit_events_archive'
    ]
    LOOP
        IF to_regclass('theeyebeta.' || t) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT ON theeyebeta.%I TO api_service', t);
        ELSE
            RAISE NOTICE 'theeyebeta.% not present; SELECT not granted', t;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 3. iam: service-client auth (app/auth/service_clients.py)
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA iam TO api_service;
GRANT SELECT ON iam.service_clients, iam.service_client_scopes TO api_service;
GRANT SELECT ON iam.service_client_secrets TO api_service;
GRANT UPDATE (last_used_at, last_used_ip) ON iam.service_client_secrets TO api_service;
GRANT INSERT ON iam.service_client_events TO api_service;
GRANT USAGE ON SEQUENCE iam.service_client_events_event_id_seq TO api_service;

-- iam: user API keys (app/auth/user_api_keys.py)
GRANT SELECT ON iam.user_api_keys TO api_service;
-- last_used_*: key verification. is_active/revoked_*: the
-- iam.revoke_user_keys_on_disable trigger (SECURITY INVOKER) fired by an
-- admin account deactivation runs with this role's privileges.
GRANT UPDATE (last_used_at, last_used_ip, is_active, revoked_at, revoked_reason)
    ON iam.user_api_keys TO api_service;
GRANT INSERT ON iam.user_api_key_events TO api_service;
GRANT USAGE ON SEQUENCE iam.user_api_key_events_event_id_seq TO api_service;

-- iam: admin account lifecycle (app/services/account_service.py). Soft delete only.
GRANT SELECT ON iam.users TO api_service;
GRANT INSERT (email, display_name, organization, plan, created_by) ON iam.users TO api_service;
GRANT UPDATE (is_active, updated_by, updated_at) ON iam.users TO api_service;

-- iam: refresh tokens (app/repositories/sql_refresh_tokens.py)
GRANT SELECT ON iam.refresh_tokens TO api_service;
GRANT INSERT (subject, client_id, token_hash, expires_at, metadata) ON iam.refresh_tokens TO api_service;
GRANT UPDATE (revoked_at, replaced_by) ON iam.refresh_tokens TO api_service;

-- iam: scope-denial audit (app/auth/audit.py)
GRANT INSERT ON iam.auth_audit_log TO api_service;
GRANT USAGE ON SEQUENCE iam.auth_audit_log_event_id_seq TO api_service;

COMMIT;

-- Optional guard rails (review timings against real query latency first):
--   ALTER ROLE api_service SET statement_timeout = '30s';
--   ALTER ROLE api_service SET idle_in_transaction_session_timeout = '60s';
--
-- Cut-over on a host where DATABASE_URL still uses another role: apply this
-- file, switch DATABASE_URL to api_service, smoke Lens + Admin
-- (docs/E2E_VERIFICATION.md). Do NOT drop api_readonly (Prod-owned).
--
-- Verify:
--   SET ROLE api_service;
--   SELECT count(*) FROM theeyebeta.dataapi_locks;        -- ok (via api_readonly)
--   SELECT count(*) FROM theeyebeta.instruments;          -- ok
--   SELECT count(*) FROM theeyebeta.agents;               -- permission denied
--   DELETE FROM iam.users WHERE false;                    -- permission denied
--   CREATE TABLE theeyebeta.x (id int);                   -- permission denied
