-- Private, tenant-scoped communications identity and consent foundation.
-- This migration does not enable provider traffic or expose any relation to
-- Supabase's Data API. A phone address never establishes a person, portal
-- role, farm, or operating relationship.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_communication_profiles (
    id TEXT PRIMARY KEY,
    portal_id TEXT NOT NULL REFERENCES agro_customer_portals(id),
    person_id TEXT NOT NULL REFERENCES agro_people(id),
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
    locale TEXT NOT NULL,
    time_zone TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (portal_id, person_id)
);

CREATE TABLE IF NOT EXISTS agro_communication_endpoint_verifications (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES agro_communication_profiles(id),
    endpoint_id TEXT NOT NULL REFERENCES agro_communication_endpoints(id),
    verification_method TEXT NOT NULL,
    verified_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    verified_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
    revoked_at TIMESTAMPTZ,
    CHECK ((status = 'active' AND revoked_at IS NULL) OR status IN ('revoked', 'disabled'))
);

CREATE TABLE IF NOT EXISTS agro_communication_endpoint_scopes (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES agro_communication_profiles(id),
    relationship_id TEXT NOT NULL REFERENCES agro_person_operating_relationships(id),
    scope_type TEXT NOT NULL CHECK (scope_type IN (
        'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
    )),
    scope_id TEXT NOT NULL,
    starts_on DATE NOT NULL,
    ends_on DATE,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
    CHECK ((status = 'active' AND ends_on IS NULL) OR status IN ('revoked', 'disabled')),
    UNIQUE (profile_id, relationship_id, scope_type, scope_id)
);

CREATE TABLE IF NOT EXISTS agro_communication_scoped_consents (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES agro_communication_profiles(id),
    endpoint_id TEXT NOT NULL REFERENCES agro_communication_endpoints(id),
    purpose TEXT NOT NULL CHECK (purpose IN (
        'work_prompt', 'weekly_farmer_checkin', 'field_evidence_request',
        'local_weather_observation', 'problem_report', 'callback_coordination',
        'safety_escalation', 'operational_campaign'
    )),
    scope_type TEXT NOT NULL CHECK (scope_type IN (
        'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
    )),
    scope_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('whatsapp')),
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
    evidence TEXT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK ((status = 'active' AND revoked_at IS NULL)
        OR (status = 'revoked' AND revoked_at IS NOT NULL)
        OR status = 'disabled'),
    UNIQUE (endpoint_id, purpose, scope_type, scope_id, channel)
);

-- Every grant and revocation is retained separately from the current-state
-- row. Evidence on the current row is the original capture and is immutable
-- through the application boundary.
CREATE TABLE IF NOT EXISTS agro_communication_scoped_consent_events (
    id TEXT PRIMARY KEY,
    consent_id TEXT NOT NULL REFERENCES agro_communication_scoped_consents(id),
    profile_id TEXT NOT NULL REFERENCES agro_communication_profiles(id),
    endpoint_id TEXT NOT NULL REFERENCES agro_communication_endpoints(id),
    purpose TEXT NOT NULL CHECK (purpose IN (
        'work_prompt', 'weekly_farmer_checkin', 'field_evidence_request',
        'local_weather_observation', 'problem_report', 'callback_coordination',
        'safety_escalation', 'operational_campaign'
    )),
    scope_type TEXT NOT NULL CHECK (scope_type IN (
        'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
    )),
    scope_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('whatsapp')),
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    evidence TEXT NOT NULL,
    actor_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_communication_endpoint_verifications_active
    ON agro_communication_endpoint_verifications (endpoint_id, profile_id)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS agro_idx_communication_profiles_person
    ON agro_communication_profiles (person_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_endpoint_verifications_profile
    ON agro_communication_endpoint_verifications (profile_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_endpoint_verifications_endpoint
    ON agro_communication_endpoint_verifications (endpoint_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_endpoint_verifications_verifier
    ON agro_communication_endpoint_verifications (verified_by_person_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_endpoint_scopes_profile
    ON agro_communication_endpoint_scopes (profile_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_endpoint_scopes_relationship
    ON agro_communication_endpoint_scopes (relationship_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_scoped_consents_profile
    ON agro_communication_scoped_consents (profile_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_scoped_consent_events_consent
    ON agro_communication_scoped_consent_events (consent_id, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_communication_scoped_consent_events_profile
    ON agro_communication_scoped_consent_events (profile_id, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_communication_scoped_consent_events_endpoint
    ON agro_communication_scoped_consent_events (endpoint_id, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_communication_scoped_consent_events_actor
    ON agro_communication_scoped_consent_events (actor_person_id, created_at);

CREATE OR REPLACE FUNCTION agro_reject_scoped_consent_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'communication scoped consent events are append-only';
END;
$function$;

CREATE OR REPLACE FUNCTION agro_reject_scoped_consent_capture_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'communication scoped consent capture is immutable';
END;
$function$;

DROP TRIGGER IF EXISTS agro_communication_scoped_consents_capture_immutable
    ON agro_communication_scoped_consents;
CREATE TRIGGER agro_communication_scoped_consents_capture_immutable
    BEFORE UPDATE OF profile_id, endpoint_id, purpose, scope_type, scope_id,
        channel, evidence, granted_at
    ON agro_communication_scoped_consents
    FOR EACH ROW EXECUTE FUNCTION agro_reject_scoped_consent_capture_mutation();

DROP TRIGGER IF EXISTS agro_communication_scoped_consent_events_no_update
    ON agro_communication_scoped_consent_events;
CREATE TRIGGER agro_communication_scoped_consent_events_no_update
    BEFORE UPDATE ON agro_communication_scoped_consent_events
    FOR EACH ROW EXECUTE FUNCTION agro_reject_scoped_consent_event_mutation();

DROP TRIGGER IF EXISTS agro_communication_scoped_consent_events_no_delete
    ON agro_communication_scoped_consent_events;
CREATE TRIGGER agro_communication_scoped_consent_events_no_delete
    BEFORE DELETE ON agro_communication_scoped_consent_events
    FOR EACH ROW EXECUTE FUNCTION agro_reject_scoped_consent_event_mutation();

REVOKE ALL ON TABLE agro_communication_profiles FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_endpoint_verifications FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_endpoint_scopes FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_scoped_consents FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_scoped_consent_events FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_scoped_consent_event_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_scoped_consent_capture_mutation() FROM PUBLIC;

COMMIT;
