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

COMMIT;
