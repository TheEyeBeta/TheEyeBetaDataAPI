-- Least-privilege runtime role for TheEyeBetaDataAPI.
--
-- DATABASE_URL should connect as `api_service`, never as `postgres` or any
-- other superuser/owner role. This grants exactly what the app executes:
--
--   theeyebeta.*  read-only (owned by TheEyeBetaProd; the API never writes it)
--   iam.*         the reads/writes behind auth, refresh tokens, audit logging,
--                 and admin account lifecycle, column-scoped where possible
--
-- Run as a privileged owner AFTER the theeyebeta schema exists and AFTER
-- deploy/iam_api_key_schema.sql, iam_user_api_key_schema.sql,
-- iam_refresh_tokens.sql and iam_auth_audit.sql. Safe to re-run.
-- tests/integration/ applies this file and runs the IAM flows as api_service.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_service') THEN
        CREATE ROLE api_service LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END $$;

-- Set the password out of band (never commit it):
--   ALTER ROLE api_service WITH PASSWORD '<from password manager>';

-- ---------------------------------------------------------------------------
-- theeyebeta: read-only market/reference/policy data
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA theeyebeta TO api_service;
GRANT SELECT ON ALL TABLES IN SCHEMA theeyebeta TO api_service;
-- Tables created later by TheEyeBetaProd migrations need a grant too. Run once
-- as the role that owns/creates theeyebeta tables:
--   ALTER DEFAULT PRIVILEGES FOR ROLE <theeyebeta_owner> IN SCHEMA theeyebeta
--       GRANT SELECT ON TABLES TO api_service;

-- ---------------------------------------------------------------------------
-- iam: service-client auth (app/auth/service_clients.py)
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA iam TO api_service;
GRANT SELECT ON iam.service_clients, iam.service_client_scopes TO api_service;
GRANT SELECT ON iam.service_client_secrets TO api_service;
GRANT UPDATE (last_used_at, last_used_ip) ON iam.service_client_secrets TO api_service;
GRANT INSERT ON iam.service_client_events TO api_service;
GRANT USAGE ON SEQUENCE iam.service_client_events_event_id_seq TO api_service;

-- ---------------------------------------------------------------------------
-- iam: user API keys (app/auth/user_api_keys.py)
-- ---------------------------------------------------------------------------
GRANT SELECT ON iam.user_api_keys TO api_service;
-- last_used_*: key verification. is_active/revoked_*: the
-- iam.revoke_user_keys_on_disable trigger (SECURITY INVOKER) fired by an
-- admin account deactivation runs with this role's privileges.
GRANT UPDATE (last_used_at, last_used_ip, is_active, revoked_at, revoked_reason)
    ON iam.user_api_keys TO api_service;
GRANT INSERT ON iam.user_api_key_events TO api_service;
GRANT USAGE ON SEQUENCE iam.user_api_key_events_event_id_seq TO api_service;

-- ---------------------------------------------------------------------------
-- iam: admin account lifecycle (app/services/account_service.py)
-- Soft-delete only: no DELETE privilege anywhere in iam.
-- ---------------------------------------------------------------------------
GRANT SELECT ON iam.users TO api_service;
GRANT INSERT (email, display_name, organization, plan, created_by) ON iam.users TO api_service;
GRANT UPDATE (is_active, updated_by, updated_at) ON iam.users TO api_service;

-- ---------------------------------------------------------------------------
-- iam: refresh tokens (app/repositories/sql_refresh_tokens.py)
-- ---------------------------------------------------------------------------
GRANT SELECT ON iam.refresh_tokens TO api_service;
GRANT INSERT (subject, client_id, token_hash, expires_at, metadata) ON iam.refresh_tokens TO api_service;
GRANT UPDATE (revoked_at, replaced_by) ON iam.refresh_tokens TO api_service;

-- ---------------------------------------------------------------------------
-- iam: scope-denial audit (app/auth/audit.py)
-- ---------------------------------------------------------------------------
GRANT INSERT ON iam.auth_audit_log TO api_service;
GRANT USAGE ON SEQUENCE iam.auth_audit_log_event_id_seq TO api_service;

COMMIT;

-- Optional guard rails (review timings against real query latency first):
--   ALTER ROLE api_service SET statement_timeout = '30s';
--   ALTER ROLE api_service SET idle_in_transaction_session_timeout = '60s';
--
-- Retiring the old role: earlier versions of this file created `api_readonly`
-- with SELECT on the deprecated `public` schema only. It cannot run this API.
-- Once DATABASE_URL uses api_service:
--   REASSIGN OWNED BY api_readonly TO postgres; DROP OWNED BY api_readonly; DROP ROLE api_readonly;
--
-- Verify:
--   SET ROLE api_service;
--   SELECT count(*) FROM iam.service_clients;          -- ok
--   DELETE FROM iam.users WHERE false;                 -- permission denied
--   CREATE TABLE theeyebeta.x (id int);                -- permission denied
