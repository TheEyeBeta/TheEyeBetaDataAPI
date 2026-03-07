-- Production DB hardening for TheEyeBetaDataAPI
-- Run as a privileged DB user on the primary trusted PostgreSQL instance.

BEGIN;

-- 1) Create readonly role for API access
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_readonly') THEN
        CREATE ROLE api_readonly LOGIN;
    END IF;
END$$;

-- Set password manually after creation (recommended from secure channel):
-- ALTER ROLE api_readonly WITH PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';

-- 2) Restrict dangerous defaults
REVOKE ALL ON DATABASE postgres FROM api_readonly;

-- 3) Schema visibility
GRANT USAGE ON SCHEMA public TO api_readonly;

-- 4) Table/view read grants (allowlist only)
GRANT SELECT ON TABLE tickers TO api_readonly;
GRANT SELECT ON TABLE latest_snapshot TO api_readonly;
GRANT SELECT ON TABLE market_news TO api_readonly;
GRANT SELECT ON TABLE signals TO api_readonly;

-- 5) Future read grants only (optional; keep scoped)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO api_readonly;

-- 6) Explicitly prevent write operations
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM api_readonly;

COMMIT;

-- Verification examples:
-- \du api_readonly
-- SET ROLE api_readonly;
-- SELECT COUNT(*) FROM tickers;
