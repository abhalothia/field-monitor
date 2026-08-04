-- Named AGRO CEO access. Application authority is deliberately separate from
-- a person's operational role and from Supabase Auth's mutable user metadata.
-- Apply with the reviewed private migration role; this private schema remains
-- outside Supabase's Data API.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_access_memberships (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL UNIQUE REFERENCES agro_people(id),
    auth_subject TEXT UNIQUE,
    identity_email TEXT,
    access_role TEXT NOT NULL CHECK (access_role IN ('owner', 'admin')),
    identity_status TEXT NOT NULL CHECK (identity_status IN ('identity_pending', 'invited', 'active', 'suspended')),
    invited_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    last_authenticated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (identity_status = 'identity_pending' AND auth_subject IS NULL AND identity_email IS NULL)
        OR (identity_status = 'invited' AND auth_subject IS NULL AND identity_email IS NOT NULL AND invited_at IS NOT NULL)
        OR (identity_status = 'active' AND auth_subject IS NOT NULL AND identity_email IS NOT NULL AND activated_at IS NOT NULL)
        OR identity_status = 'suspended'
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_access_memberships_email
    ON agro_access_memberships (lower(identity_email))
    WHERE identity_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS agro_idx_access_memberships_role_status
    ON agro_access_memberships (access_role, identity_status);

REVOKE ALL ON TABLE agro_access_memberships FROM PUBLIC;

COMMIT;
