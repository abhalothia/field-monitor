-- Named ID/password access for the private AGRO CEO pilot.  This is an
-- application identity boundary, not Supabase Auth metadata and never a
-- source-contact shortcut.  Passwords are only PBKDF2 hashes; the private
-- schema remains absent from the public Data API.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_password_identities (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL UNIQUE REFERENCES agro_people(id),
    login_id TEXT NOT NULL UNIQUE CHECK (
        login_id = lower(login_id)
        AND char_length(login_id) BETWEEN 3 AND 64
        AND login_id ~ '^[a-z][a-z0-9._-]*$'
    ),
    password_hash TEXT NOT NULL CHECK (password_hash LIKE 'pbkdf2_sha256$%'),
    access_role TEXT NOT NULL CHECK (
        access_role IN ('owner', 'admin', 'field_worker', 'farmer')
    ),
    identity_status TEXT NOT NULL CHECK (
        identity_status IN ('active', 'suspended')
    ),
    password_version INTEGER NOT NULL CHECK (password_version > 0),
    password_changed_at TIMESTAMPTZ NOT NULL,
    last_authenticated_at TIMESTAMPTZ,
    created_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS agro_idx_password_identities_role_status
    ON agro_password_identities (access_role, identity_status);

REVOKE ALL ON TABLE agro_password_identities FROM PUBLIC, anon, authenticated;

-- The server-only Vercel runtime verifies hashes and persists successful
-- sign-ins/provisioning. Browser clients never receive these grants or a DSN.
GRANT SELECT, INSERT, UPDATE ON TABLE agro_password_identities TO agro_vc_runtime;

COMMIT;
