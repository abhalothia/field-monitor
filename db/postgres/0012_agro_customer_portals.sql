-- Customer portal and phone-identity foundation.  This stays in the private
-- ``agro`` schema: browser clients do not receive direct table access.
--
-- A TrackWick contact point is deliberately not an identity.  A portal
-- identity can be created only after an accountable person explicitly invites
-- the phone number and the holder completes the configured OTP challenge.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

-- The initial email-only membership shape predates the phone-first portal.
-- Keep its role authority, but permit a verified phone identity as an
-- alternative to email.  Auth metadata is still not an authority source.
ALTER TABLE agro_access_memberships
    ADD COLUMN IF NOT EXISTS identity_phone TEXT;

ALTER TABLE agro_access_memberships
    DROP CONSTRAINT IF EXISTS agro_access_memberships_check;

ALTER TABLE agro_access_memberships
    ADD CONSTRAINT agro_access_memberships_identity_check CHECK (
        (identity_status = 'identity_pending'
            AND auth_subject IS NULL AND identity_email IS NULL AND identity_phone IS NULL)
        OR
        (identity_status = 'invited'
            AND auth_subject IS NULL
            AND (identity_email IS NOT NULL OR identity_phone IS NOT NULL)
            AND invited_at IS NOT NULL)
        OR
        (identity_status = 'active'
            AND auth_subject IS NOT NULL
            AND (identity_email IS NOT NULL OR identity_phone IS NOT NULL)
            AND activated_at IS NOT NULL)
        OR identity_status = 'suspended'
    );

CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_access_memberships_phone
    ON agro_access_memberships (identity_phone)
    WHERE identity_phone IS NOT NULL;

CREATE TABLE IF NOT EXISTS agro_customer_portals (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z][a-z0-9-]{1,62}$'),
    display_name TEXT NOT NULL CHECK (char_length(trim(display_name)) BETWEEN 1 AND 160),
    hostname TEXT NOT NULL UNIQUE CHECK (hostname = lower(hostname) AND hostname ~ '^[a-z0-9][a-z0-9.-]{1,251}[a-z0-9]$'),
    status TEXT NOT NULL CHECK (status IN ('active', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_portal_identities (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL UNIQUE REFERENCES agro_people(id),
    phone_e164 TEXT NOT NULL UNIQUE CHECK (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
    auth_subject TEXT UNIQUE,
    identity_status TEXT NOT NULL CHECK (identity_status IN ('invited', 'active', 'suspended')),
    invited_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    last_authenticated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (identity_status = 'invited' AND auth_subject IS NULL AND verified_at IS NULL)
        OR (identity_status = 'active' AND auth_subject IS NOT NULL AND verified_at IS NOT NULL)
        OR identity_status = 'suspended'
    )
);

CREATE TABLE IF NOT EXISTS agro_portal_memberships (
    id TEXT PRIMARY KEY,
    portal_id TEXT NOT NULL REFERENCES agro_customer_portals(id),
    person_id TEXT NOT NULL REFERENCES agro_people(id),
    identity_id TEXT REFERENCES agro_portal_identities(id),
    portal_role TEXT NOT NULL CHECK (portal_role IN ('owner', 'admin', 'field_worker', 'farmer')),
    membership_status TEXT NOT NULL CHECK (membership_status IN ('identity_pending', 'invited', 'active', 'suspended')),
    invited_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (portal_id, person_id),
    CHECK (
        (membership_status = 'identity_pending' AND identity_id IS NULL)
        OR (membership_status = 'invited' AND identity_id IS NOT NULL AND invited_at IS NOT NULL)
        OR (membership_status = 'active' AND identity_id IS NOT NULL AND activated_at IS NOT NULL)
        OR membership_status = 'suspended'
    )
);

CREATE INDEX IF NOT EXISTS agro_idx_portal_memberships_portal_role_status
    ON agro_portal_memberships (portal_id, portal_role, membership_status);
CREATE INDEX IF NOT EXISTS agro_idx_portal_memberships_identity
    ON agro_portal_memberships (identity_id, membership_status)
    WHERE identity_id IS NOT NULL;

REVOKE ALL ON TABLE agro_customer_portals FROM PUBLIC;
REVOKE ALL ON TABLE agro_portal_identities FROM PUBLIC;
REVOKE ALL ON TABLE agro_portal_memberships FROM PUBLIC;

-- The Vercel runtime can resolve and activate an already invited identity. It
-- cannot create portals, invite phones, or alter schema. Provisioning remains
-- an accountable private-admin operation.
GRANT SELECT ON TABLE agro_people TO agro_vc_runtime;
GRANT SELECT, UPDATE ON TABLE agro_access_memberships TO agro_vc_runtime;
GRANT SELECT ON TABLE agro_customer_portals TO agro_vc_runtime;
GRANT SELECT, UPDATE ON TABLE agro_portal_identities TO agro_vc_runtime;
GRANT SELECT, UPDATE ON TABLE agro_portal_memberships TO agro_vc_runtime;

COMMIT;
