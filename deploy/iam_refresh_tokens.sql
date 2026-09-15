-- Additive IAM refresh-token support for opted-in service clients.
-- Safe to apply repeatedly (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
-- Does not change behavior for clients with short_lived_tokens_enabled = false.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS iam;

ALTER TABLE iam.service_clients
    ADD COLUMN IF NOT EXISTS short_lived_tokens_enabled boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS iam.refresh_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject text NOT NULL,
    client_id text NOT NULL,
    token_hash text NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    replaced_by uuid REFERENCES iam.refresh_tokens(id),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (length(token_hash) = 64),
    CHECK (length(trim(subject)) >= 3),
    CHECK (length(trim(client_id)) >= 3)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_tokens_hash
    ON iam.refresh_tokens (token_hash);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_client_subject
    ON iam.refresh_tokens (client_id, subject)
    WHERE revoked_at IS NULL;

-- Runtime grants for the API role used in DATABASE_URL (default name: api_service).
-- Adjust the role name if your deployment uses a different login.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_service') THEN
        GRANT USAGE ON SCHEMA iam TO api_service;
        GRANT SELECT, INSERT, UPDATE ON iam.refresh_tokens TO api_service;
        GRANT SELECT ON iam.service_clients TO api_service;
        GRANT SELECT ON iam.service_client_scopes TO api_service;
    END IF;
END $$;

-- If your API role is not api_service, run (as a privileged owner):
--   GRANT USAGE ON SCHEMA iam TO <api_role>;
--   GRANT SELECT, INSERT, UPDATE ON iam.refresh_tokens TO <api_role>;

COMMIT;
