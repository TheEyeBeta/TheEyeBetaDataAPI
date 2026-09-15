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

-- Opt-in: when true, provision scripts should not auto-apply client_type_default_scopes
-- beyond explicitly requested scopes. Existing clients are untouched.
ALTER TABLE iam.client_types
    ADD COLUMN IF NOT EXISTS least_privilege_default boolean NOT NULL DEFAULT false;

COMMIT;
