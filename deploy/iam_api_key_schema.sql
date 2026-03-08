BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS iam;

CREATE TABLE IF NOT EXISTS iam.client_types (
    app_type text PRIMARY KEY,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL DEFAULT 'system',
    CHECK (app_type ~ '^[a-z][a-z0-9-]{1,63}$')
);

CREATE TABLE IF NOT EXISTS iam.client_type_default_scopes (
    app_type text NOT NULL REFERENCES iam.client_types(app_type) ON DELETE CASCADE,
    scope text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL DEFAULT 'system',
    PRIMARY KEY (app_type, scope),
    CHECK (scope ~ '^[a-z][a-z0-9-]*:[a-z*][a-z0-9*-]*$')
);

CREATE TABLE IF NOT EXISTS iam.service_clients (
    client_uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id text NOT NULL UNIQUE,
    display_name text NOT NULL,
    app_type text NOT NULL REFERENCES iam.client_types(app_type),
    environment text NOT NULL DEFAULT 'production',
    is_active boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_by text,
    revoked_at timestamptz,
    revoked_reason text,
    CHECK (client_id ~ '^[a-z][a-z0-9-]{2,63}$'),
    CHECK (length(trim(display_name)) >= 3),
    CHECK (environment IN ('development', 'staging', 'production'))
);

CREATE TABLE IF NOT EXISTS iam.service_client_scopes (
    client_uuid uuid NOT NULL REFERENCES iam.service_clients(client_uuid) ON DELETE CASCADE,
    scope text NOT NULL,
    grant_source text NOT NULL DEFAULT 'manual',
    granted_at timestamptz NOT NULL DEFAULT now(),
    granted_by text NOT NULL,
    PRIMARY KEY (client_uuid, scope),
    CHECK (scope ~ '^[a-z][a-z0-9-]*:[a-z*][a-z0-9*-]*$'),
    CHECK (grant_source IN ('manual', 'template', 'migration'))
);

CREATE TABLE IF NOT EXISTS iam.service_client_secrets (
    secret_uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_uuid uuid NOT NULL REFERENCES iam.service_clients(client_uuid) ON DELETE CASCADE,
    secret_prefix text NOT NULL,
    secret_hash text NOT NULL,
    hash_algorithm text NOT NULL DEFAULT 'bcrypt',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    expires_at timestamptz,
    revoked_at timestamptz,
    revoked_reason text,
    last_used_at timestamptz,
    last_used_ip inet,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (client_uuid, secret_prefix),
    CHECK (length(secret_prefix) BETWEEN 6 AND 64),
    CHECK (length(secret_hash) >= 32)
);

CREATE TABLE IF NOT EXISTS iam.service_client_events (
    event_id bigserial PRIMARY KEY,
    client_uuid uuid REFERENCES iam.service_clients(client_uuid) ON DELETE SET NULL,
    event_type text NOT NULL,
    actor_type text NOT NULL,
    actor_subject text NOT NULL,
    request_id text,
    event_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (actor_type IN ('service', 'admin', 'system')),
    CHECK (length(event_type) >= 3)
);

ALTER TABLE iam.service_client_secrets
    ALTER COLUMN hash_algorithm SET DEFAULT 'bcrypt';

CREATE INDEX IF NOT EXISTS idx_service_clients_active
    ON iam.service_clients (is_active, app_type, environment);

CREATE INDEX IF NOT EXISTS idx_service_client_scopes_scope
    ON iam.service_client_scopes (scope);

CREATE INDEX IF NOT EXISTS idx_service_client_secrets_active
    ON iam.service_client_secrets (client_uuid, is_active)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_service_client_events_client_created
    ON iam.service_client_events (client_uuid, created_at DESC);

CREATE OR REPLACE FUNCTION iam.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION iam.apply_default_scopes_for_client()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
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

CREATE OR REPLACE FUNCTION iam.revoke_client_secrets_on_disable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.is_active = true AND NEW.is_active = false THEN
        UPDATE iam.service_client_secrets
        SET
            is_active = false,
            revoked_at = COALESCE(revoked_at, now()),
            revoked_reason = COALESCE(revoked_reason, NEW.revoked_reason, 'client disabled')
        WHERE client_uuid = NEW.client_uuid
          AND is_active = true;

        INSERT INTO iam.service_client_events (client_uuid, event_type, actor_type, actor_subject, event_payload)
        VALUES (
            NEW.client_uuid,
            'client_disabled',
            'system',
            COALESCE(NULLIF(NEW.updated_by, ''), 'system'),
            jsonb_build_object('revoked_reason', NEW.revoked_reason)
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION iam.issue_service_api_key(
    p_client_id text,
    p_created_by text,
    p_expires_at timestamptz DEFAULT NULL
)
RETURNS TABLE (
    client_uuid uuid,
    client_id text,
    secret_prefix text,
    api_key text,
    expires_at timestamptz
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_client_uuid uuid;
    v_prefix text;
    v_api_key text;
    v_secret_uuid uuid;
BEGIN
    SELECT c.client_uuid
    INTO v_client_uuid
    FROM iam.service_clients c
    WHERE c.client_id = p_client_id
      AND c.is_active = true
    FOR UPDATE;

    IF v_client_uuid IS NULL THEN
        RAISE EXCEPTION 'Unknown or inactive service client: %', p_client_id;
    END IF;

    LOOP
        v_prefix := lower(encode(gen_random_bytes(4), 'hex'));
        v_api_key := format(
            'teb_sk_%s_%s',
            v_prefix,
            regexp_replace(
                translate(encode(gen_random_bytes(24), 'base64'), '+/=', '-__'),
                '[^A-Za-z0-9_-]',
                '',
                'g'
            )
        );

        BEGIN
            INSERT INTO iam.service_client_secrets (
                client_uuid,
                secret_prefix,
                secret_hash,
                hash_algorithm,
                created_by,
                expires_at
            )
            VALUES (
                v_client_uuid,
                v_prefix,
                crypt(v_api_key, gen_salt('bf', 12)),
                'bcrypt',
                p_created_by,
                p_expires_at
            )
            RETURNING iam.service_client_secrets.secret_uuid
            INTO v_secret_uuid;
            EXIT;
        EXCEPTION
            WHEN unique_violation THEN
                CONTINUE;
        END;
    END LOOP;

    INSERT INTO iam.service_client_events (
        client_uuid,
        event_type,
        actor_type,
        actor_subject,
        event_payload
    )
    VALUES (
        v_client_uuid,
        'secret_issued',
        'admin',
        p_created_by,
        jsonb_build_object(
            'secret_uuid', v_secret_uuid,
            'secret_prefix', v_prefix,
            'expires_at', p_expires_at
        )
    );

    RETURN QUERY
    SELECT
        v_client_uuid,
        p_client_id,
        v_prefix,
        v_api_key,
        p_expires_at;
END;
$$;

CREATE OR REPLACE FUNCTION iam.provision_service_client(
    p_client_id text,
    p_display_name text,
    p_app_type text,
    p_environment text DEFAULT 'production',
    p_created_by text DEFAULT 'system',
    p_expires_at timestamptz DEFAULT NULL,
    p_metadata jsonb DEFAULT '{}'::jsonb
)
RETURNS TABLE (
    client_uuid uuid,
    client_id text,
    app_type text,
    environment text,
    granted_scopes text[],
    secret_prefix text,
    api_key text
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_client_uuid uuid;
BEGIN
    INSERT INTO iam.service_clients (
        client_id,
        display_name,
        app_type,
        environment,
        metadata,
        created_by,
        updated_by
    )
    VALUES (
        p_client_id,
        p_display_name,
        p_app_type,
        p_environment,
        COALESCE(p_metadata, '{}'::jsonb),
        p_created_by,
        p_created_by
    )
    RETURNING iam.service_clients.client_uuid
    INTO v_client_uuid;

    INSERT INTO iam.service_client_events (
        client_uuid,
        event_type,
        actor_type,
        actor_subject,
        event_payload
    )
    VALUES (
        v_client_uuid,
        'client_created',
        'admin',
        p_created_by,
        jsonb_build_object('app_type', p_app_type, 'environment', p_environment)
    );

    RETURN QUERY
    WITH issued AS (
        SELECT
            i.client_uuid,
            i.client_id,
            i.secret_prefix,
            i.api_key
        FROM iam.issue_service_api_key(p_client_id, p_created_by, p_expires_at) i
    ),
    scopes AS (
        SELECT array_agg(s.scope ORDER BY s.scope) AS granted_scopes
        FROM iam.service_client_scopes s
        WHERE s.client_uuid = v_client_uuid
    )
    SELECT
        issued.client_uuid,
        issued.client_id,
        p_app_type,
        p_environment,
        COALESCE(scopes.granted_scopes, ARRAY[]::text[]),
        issued.secret_prefix,
        issued.api_key
    FROM issued
    CROSS JOIN scopes;
END;
$$;

DROP TRIGGER IF EXISTS trg_service_clients_set_updated_at ON iam.service_clients;
CREATE TRIGGER trg_service_clients_set_updated_at
BEFORE UPDATE ON iam.service_clients
FOR EACH ROW
EXECUTE FUNCTION iam.set_updated_at();

DROP TRIGGER IF EXISTS trg_service_clients_apply_default_scopes ON iam.service_clients;
CREATE TRIGGER trg_service_clients_apply_default_scopes
AFTER INSERT ON iam.service_clients
FOR EACH ROW
EXECUTE FUNCTION iam.apply_default_scopes_for_client();

DROP TRIGGER IF EXISTS trg_service_clients_revoke_secrets ON iam.service_clients;
CREATE TRIGGER trg_service_clients_revoke_secrets
AFTER UPDATE OF is_active ON iam.service_clients
FOR EACH ROW
EXECUTE FUNCTION iam.revoke_client_secrets_on_disable();

INSERT INTO iam.client_types (app_type, description, created_by) VALUES
    ('mobile-backend', 'Backend serving mobile advisor app users', 'bootstrap'),
    ('vi-backend', 'Backend for VI desktop/laptop analytics', 'bootstrap'),
    ('trade-engine', 'Automated trade execution engine backend', 'bootstrap'),
    ('admin-tool', 'Internal administration and operations tooling', 'bootstrap')
ON CONFLICT (app_type) DO NOTHING;

INSERT INTO iam.client_type_default_scopes (app_type, scope, created_by) VALUES
    ('mobile-backend', 'advisor:read', 'bootstrap'),
    ('mobile-backend', 'market:read', 'bootstrap'),
    ('mobile-backend', 'symbols:read', 'bootstrap'),
    ('vi-backend', 'advisor:read', 'bootstrap'),
    ('vi-backend', 'market:read', 'bootstrap'),
    ('vi-backend', 'symbols:read', 'bootstrap'),
    ('vi-backend', 'analytics:read', 'bootstrap'),
    ('trade-engine', 'trades:write', 'bootstrap'),
    ('trade-engine', 'portfolio:read', 'bootstrap'),
    ('trade-engine', 'internal:jobs', 'bootstrap'),
    ('admin-tool', 'admin:read', 'bootstrap'),
    ('admin-tool', 'admin:write', 'bootstrap'),
    ('admin-tool', 'internal:jobs', 'bootstrap')
ON CONFLICT (app_type, scope) DO NOTHING;

COMMIT;
