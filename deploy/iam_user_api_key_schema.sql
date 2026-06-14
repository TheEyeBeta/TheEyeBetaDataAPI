-- End-user identities and personal API keys for TheEyeBetaDataAPI.
-- Mirrors the service-client model in deploy/iam_api_key_schema.sql:
--   * Keys are hashed with pgcrypto bcrypt (crypt + gen_salt('bf', 12)).
--   * A globally unique, indexed prefix makes Bearer-token lookup O(1)
--     (callers present only the raw key, with no client_id to scope by).
--   * Verification re-derives the hash with crypt(:raw_key, key_hash) — never
--     an equality match against a freshly salted hash.
--   * Issue/revoke actions are recorded in iam.user_api_key_events.
--
-- Apply after deploy/iam_api_key_schema.sql (it reuses iam.set_updated_at()).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS iam;

CREATE TABLE IF NOT EXISTS iam.users (
    user_uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    display_name text,
    organization text,
    plan text NOT NULL DEFAULT 'free',
    is_active boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL DEFAULT 'system',
    updated_by text,
    CHECK (email = lower(email)),
    CHECK (char_length(email) BETWEEN 3 AND 320),
    CHECK (position('@' in email) > 1),
    CHECK (plan IN ('free', 'starter', 'pro', 'enterprise'))
);

CREATE TABLE IF NOT EXISTS iam.user_api_keys (
    key_uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_uuid uuid NOT NULL REFERENCES iam.users(user_uuid) ON DELETE CASCADE,
    key_prefix text NOT NULL,
    key_hash text NOT NULL,
    hash_algorithm text NOT NULL DEFAULT 'bcrypt',
    name text,
    scopes text[] NOT NULL DEFAULT ARRAY[]::text[],
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    expires_at timestamptz,
    revoked_at timestamptz,
    revoked_reason text,
    last_used_at timestamptz,
    last_used_ip inet,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Prefix is globally unique: it is the only thing we can look up by when a
    -- caller presents a bare Bearer key.
    UNIQUE (key_prefix),
    CHECK (key_prefix ~ '^[0-9a-f]{16}$'),
    CHECK (length(key_hash) >= 32)
);

CREATE TABLE IF NOT EXISTS iam.user_api_key_events (
    event_id bigserial PRIMARY KEY,
    user_uuid uuid REFERENCES iam.users(user_uuid) ON DELETE SET NULL,
    key_uuid uuid REFERENCES iam.user_api_keys(key_uuid) ON DELETE SET NULL,
    event_type text NOT NULL,
    actor_type text NOT NULL,
    actor_subject text NOT NULL,
    request_id text,
    event_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (actor_type IN ('user', 'admin', 'system')),
    CHECK (length(event_type) >= 3)
);

CREATE INDEX IF NOT EXISTS idx_users_active
    ON iam.users (is_active, plan);

CREATE INDEX IF NOT EXISTS idx_user_api_keys_user
    ON iam.user_api_keys (user_uuid);

CREATE INDEX IF NOT EXISTS idx_user_api_keys_active
    ON iam.user_api_keys (user_uuid, is_active)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_user_api_key_events_user_created
    ON iam.user_api_key_events (user_uuid, created_at DESC);

-- Validate a scope array against the same grammar service-client scopes use.
CREATE OR REPLACE FUNCTION iam.validate_scope_array(p_scopes text[])
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_scope text;
BEGIN
    FOREACH v_scope IN ARRAY COALESCE(p_scopes, ARRAY[]::text[])
    LOOP
        IF v_scope !~ '^[a-z][a-z0-9-]*:[a-z*][a-z0-9*-]*$' THEN
            RAISE EXCEPTION 'Invalid scope: %', v_scope;
        END IF;
    END LOOP;
END;
$$;

-- Revoke a user's keys when the account is deactivated (mirrors the
-- revoke-on-disable trigger for service clients).
CREATE OR REPLACE FUNCTION iam.revoke_user_keys_on_disable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.is_active = true AND NEW.is_active = false THEN
        UPDATE iam.user_api_keys
        SET
            is_active = false,
            revoked_at = COALESCE(revoked_at, now()),
            revoked_reason = COALESCE(revoked_reason, 'user disabled')
        WHERE user_uuid = NEW.user_uuid
          AND is_active = true;

        INSERT INTO iam.user_api_key_events (user_uuid, event_type, actor_type, actor_subject, event_payload)
        VALUES (
            NEW.user_uuid,
            'user_disabled',
            'system',
            COALESCE(NULLIF(NEW.updated_by, ''), 'system'),
            '{}'::jsonb
        );
    END IF;

    RETURN NEW;
END;
$$;

-- Issue a personal API key for an existing, active user.
-- Returns the raw key exactly once; only its bcrypt hash is persisted.
CREATE OR REPLACE FUNCTION iam.issue_user_api_key(
    p_user_uuid uuid,
    p_name text,
    p_scopes text[],
    p_created_by text,
    p_expires_at timestamptz DEFAULT NULL
)
RETURNS TABLE (
    key_uuid uuid,
    user_uuid uuid,
    key_prefix text,
    api_key text,
    scopes text[],
    expires_at timestamptz
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_active boolean;
    v_prefix text;
    v_api_key text;
    v_key_uuid uuid;
    v_scopes text[] := COALESCE(p_scopes, ARRAY[]::text[]);
BEGIN
    SELECT u.is_active INTO v_user_active
    FROM iam.users u
    WHERE u.user_uuid = p_user_uuid
    FOR UPDATE;

    IF v_user_active IS NULL THEN
        RAISE EXCEPTION 'Unknown user: %', p_user_uuid;
    END IF;
    IF v_user_active = false THEN
        RAISE EXCEPTION 'User is inactive: %', p_user_uuid;
    END IF;

    PERFORM iam.validate_scope_array(v_scopes);

    LOOP
        -- 8 random bytes -> 16 lowercase hex chars. The runtime parser reads a
        -- fixed 16-char prefix after the 'teb_uk_' tag, so the random secret may
        -- safely contain underscores from base64url.
        v_prefix := lower(encode(gen_random_bytes(8), 'hex'));
        v_api_key := format(
            'teb_uk_%s_%s',
            v_prefix,
            regexp_replace(
                translate(encode(gen_random_bytes(24), 'base64'), '+/=', '-__'),
                '[^A-Za-z0-9_-]',
                '',
                'g'
            )
        );

        BEGIN
            INSERT INTO iam.user_api_keys (
                user_uuid,
                key_prefix,
                key_hash,
                hash_algorithm,
                name,
                scopes,
                created_by,
                expires_at
            )
            VALUES (
                p_user_uuid,
                v_prefix,
                crypt(v_api_key, gen_salt('bf', 12)),
                'bcrypt',
                NULLIF(trim(COALESCE(p_name, '')), ''),
                v_scopes,
                p_created_by,
                p_expires_at
            )
            RETURNING iam.user_api_keys.key_uuid
            INTO v_key_uuid;
            EXIT;
        EXCEPTION
            WHEN unique_violation THEN
                CONTINUE;
        END;
    END LOOP;

    INSERT INTO iam.user_api_key_events (
        user_uuid,
        key_uuid,
        event_type,
        actor_type,
        actor_subject,
        event_payload
    )
    VALUES (
        p_user_uuid,
        v_key_uuid,
        'key_issued',
        'admin',
        p_created_by,
        jsonb_build_object(
            'key_uuid', v_key_uuid,
            'key_prefix', v_prefix,
            'scopes', to_jsonb(v_scopes),
            'expires_at', p_expires_at
        )
    );

    RETURN QUERY
    SELECT
        v_key_uuid,
        p_user_uuid,
        v_prefix,
        v_api_key,
        v_scopes,
        p_expires_at;
END;
$$;

-- Upsert a user by email and issue a key in one call (convenience for tooling).
CREATE OR REPLACE FUNCTION iam.provision_user_api_key(
    p_email text,
    p_display_name text,
    p_name text,
    p_scopes text[],
    p_created_by text DEFAULT 'system',
    p_plan text DEFAULT 'free',
    p_expires_at timestamptz DEFAULT NULL
)
RETURNS TABLE (
    user_uuid uuid,
    email text,
    key_uuid uuid,
    key_prefix text,
    api_key text,
    scopes text[],
    expires_at timestamptz
)
LANGUAGE plpgsql
AS $$
-- OUT columns above (e.g. "email") share names with iam.users columns; resolve
-- bare references to the column so ON CONFLICT (email) is unambiguous.
#variable_conflict use_column
DECLARE
    v_email text := lower(trim(p_email));
    v_user_uuid uuid;
BEGIN
    INSERT INTO iam.users (email, display_name, plan, created_by, updated_by)
    VALUES (v_email, NULLIF(trim(COALESCE(p_display_name, '')), ''), p_plan, p_created_by, p_created_by)
    ON CONFLICT (email) DO UPDATE
        SET display_name = COALESCE(EXCLUDED.display_name, iam.users.display_name),
            is_active = true,
            updated_by = p_created_by
    RETURNING iam.users.user_uuid INTO v_user_uuid;

    RETURN QUERY
    SELECT
        v_user_uuid,
        v_email,
        issued.key_uuid,
        issued.key_prefix,
        issued.api_key,
        issued.scopes,
        issued.expires_at
    FROM iam.issue_user_api_key(v_user_uuid, p_name, p_scopes, p_created_by, p_expires_at) issued;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON iam.users;
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON iam.users
FOR EACH ROW
EXECUTE FUNCTION iam.set_updated_at();

DROP TRIGGER IF EXISTS trg_users_revoke_keys ON iam.users;
CREATE TRIGGER trg_users_revoke_keys
AFTER UPDATE OF is_active ON iam.users
FOR EACH ROW
EXECUTE FUNCTION iam.revoke_user_keys_on_disable();

COMMIT;

-- Runtime grants (adjust role name to match DATABASE_URL). Run separately as a
-- privileged user once the API role exists:
--
--   GRANT USAGE ON SCHEMA iam TO api_service;
--   GRANT SELECT, UPDATE ON iam.user_api_keys TO api_service;  -- UPDATE: last_used_* only
--   GRANT SELECT ON iam.users TO api_service;
--   GRANT INSERT ON iam.user_api_key_events TO api_service;
--   GRANT USAGE ON SEQUENCE iam.user_api_key_events_event_id_seq TO api_service;
