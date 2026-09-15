-- Additive auth audit log + optional least-privilege default for new clients.
-- Does not change scopes for existing service_clients rows.

BEGIN;

CREATE SCHEMA IF NOT EXISTS iam;

CREATE TABLE IF NOT EXISTS iam.auth_audit_log (
    event_id bigserial PRIMARY KEY,
    subject text,
    scope_required text,
    scope_granted text,
    route text,
    outcome text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (outcome IN ('forbidden', 'authenticated', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_auth_audit_log_created
    ON iam.auth_audit_log (created_at DESC);

-- Opt-in: when true, provision scripts / the default-scopes trigger must not
-- auto-apply client_type_default_scopes beyond explicitly requested scopes.
-- Existing clients are untouched.
ALTER TABLE iam.client_types
    ADD COLUMN IF NOT EXISTS least_privilege_default boolean NOT NULL DEFAULT false;

-- Honor least_privilege_default on INSERT into iam.service_clients.
-- Safe to re-run: replaces the function body used by the existing trigger.
CREATE OR REPLACE FUNCTION iam.apply_default_scopes_for_client()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM iam.client_types ct
        WHERE ct.app_type = NEW.app_type
          AND COALESCE(ct.least_privilege_default, false) = true
    ) THEN
        RETURN NEW;
    END IF;

    INSERT INTO iam.service_client_scopes (client_uuid, scope, grant_source, granted_by)
    SELECT
        NEW.client_uuid,
        defaults.scope,
        'template',
        COALESCE(NULLIF(NEW.created_by, ''), 'system')
    FROM iam.client_type_default_scopes defaults
    WHERE defaults.app_type = NEW.app_type
    ON CONFLICT (client_uuid, scope) DO NOTHING;

    RETURN NEW;
END;
$$;

-- Runtime grants for the API role used in DATABASE_URL (default name: api_service).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_service') THEN
        GRANT USAGE ON SCHEMA iam TO api_service;
        GRANT INSERT ON iam.auth_audit_log TO api_service;
        GRANT USAGE, SELECT ON SEQUENCE iam.auth_audit_log_event_id_seq TO api_service;
    END IF;
END $$;

-- If your API role is not api_service, run (as a privileged owner):
--   GRANT INSERT ON iam.auth_audit_log TO <api_role>;
--   GRANT USAGE, SELECT ON SEQUENCE iam.auth_audit_log_event_id_seq TO <api_role>;

COMMIT;
