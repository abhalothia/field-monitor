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

-- A run freezes the recipient/context decision that existed before one send.
-- Raw opaque context tokens are never persisted; only a one-way digest can be
-- used for exact inbound correlation.  ``profile_id`` is nullable solely for
-- a legacy prompt adapter, which must supply ``legacy_prompt_id`` instead.
CREATE TABLE IF NOT EXISTS agro_communication_interaction_runs (
    id TEXT PRIMARY KEY,
    profile_id TEXT REFERENCES agro_communication_profiles(id),
    endpoint_id TEXT NOT NULL REFERENCES agro_communication_endpoints(id),
    allocation_id TEXT REFERENCES agro_crop_allocations(id),
    work_item_id TEXT REFERENCES agro_work_items(id),
    field_information_request_id TEXT REFERENCES agro_field_information_requests(id),
    workflow_version_id TEXT,
    campaign_snapshot_id TEXT,
    legacy_prompt_id TEXT UNIQUE REFERENCES agro_communication_prompts(id),
    context_token_hash TEXT NOT NULL UNIQUE
        CHECK (char_length(context_token_hash) = 64 AND context_token_hash = lower(context_token_hash)),
    expected_intents_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'ready', 'dispatching', 'dispatched', 'responded', 'expired', 'cancelled'
    )),
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at),
    CHECK (profile_id IS NOT NULL OR legacy_prompt_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS agro_communication_interaction_dispatches (
    id TEXT PRIMARY KEY,
    interaction_run_id TEXT NOT NULL UNIQUE REFERENCES agro_communication_interaction_runs(id),
    provider TEXT NOT NULL,
    provider_message_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'accepted', 'scheduled', 'delivered', 'failed', 'unknown'
    )),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (provider, provider_message_id)
);

-- A stable workflow identity has immutable, independently publishable
-- versions. Audience and trigger payloads are typed descriptors, not SQL or
-- CRM query text. A run records the weekly idempotency dimension separately
-- from the immutable interaction correlation capture.
CREATE TABLE IF NOT EXISTS agro_communication_workflows (
    id TEXT PRIMARY KEY,
    workflow_key TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_communication_workflow_versions (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES agro_communication_workflows(id),
    version INTEGER NOT NULL CHECK (version > 0),
    purpose TEXT NOT NULL CHECK (purpose IN (
        'work_prompt', 'weekly_farmer_checkin', 'field_evidence_request',
        'local_weather_observation', 'problem_report', 'callback_coordination',
        'safety_escalation', 'operational_campaign'
    )),
    owner_id TEXT NOT NULL REFERENCES agro_people(id),
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'paused')),
    trigger_json JSONB NOT NULL,
    audience_json JSONB NOT NULL,
    template_id TEXT NOT NULL REFERENCES agro_communication_templates(id),
    expected_intents_json JSONB NOT NULL,
    response_deadline_hours INTEGER NOT NULL CHECK (response_deadline_hours > 0),
    quiet_hours_json JSONB,
    frequency_cap INTEGER CHECK (frequency_cap > 0),
    escalation_owner_id TEXT REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    UNIQUE (workflow_id, version)
);

CREATE TABLE IF NOT EXISTS agro_communication_workflow_runs (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES agro_communication_profiles(id),
    endpoint_id TEXT NOT NULL REFERENCES agro_communication_endpoints(id),
    allocation_id TEXT NOT NULL REFERENCES agro_crop_allocations(id),
    workflow_version_id TEXT NOT NULL REFERENCES agro_communication_workflow_versions(id),
    interaction_run_id TEXT NOT NULL UNIQUE REFERENCES agro_communication_interaction_runs(id),
    weekly_window TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (profile_id, allocation_id, workflow_version_id, weekly_window)
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
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_runs_profile
    ON agro_communication_interaction_runs (profile_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_runs_endpoint_status
    ON agro_communication_interaction_runs (endpoint_id, status, expires_at);
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_runs_allocation
    ON agro_communication_interaction_runs (allocation_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_runs_work_item
    ON agro_communication_interaction_runs (work_item_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_runs_field_request
    ON agro_communication_interaction_runs (field_information_request_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_runs_workflow
    ON agro_communication_interaction_runs (workflow_version_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_runs_campaign
    ON agro_communication_interaction_runs (campaign_snapshot_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_interaction_dispatches_message
    ON agro_communication_interaction_dispatches (provider, provider_message_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_workflow_versions_workflow_status
    ON agro_communication_workflow_versions (workflow_id, status, version);
CREATE INDEX IF NOT EXISTS agro_idx_communication_workflow_runs_version_window
    ON agro_communication_workflow_runs (workflow_version_id, weekly_window);

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

CREATE OR REPLACE FUNCTION agro_reject_interaction_capture_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'communication interaction capture is immutable';
END;
$function$;

CREATE OR REPLACE FUNCTION agro_reject_interaction_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'communication interactions are append-only';
END;
$function$;

CREATE OR REPLACE FUNCTION agro_reject_workflow_capture_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'communication workflow version capture is immutable';
END;
$function$;

CREATE OR REPLACE FUNCTION agro_reject_workflow_run_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'communication workflow runs are append-only';
END;
$function$;

CREATE OR REPLACE FUNCTION agro_validate_workflow_version_lifecycle()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF (OLD.status = 'draft' AND NEW.status = 'published'
            AND OLD.published_at IS NULL AND NEW.published_at IS NOT NULL)
       OR (OLD.status = 'published' AND NEW.status = 'paused'
            AND NEW.published_at IS NOT DISTINCT FROM OLD.published_at) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'communication workflow version lifecycle is invalid';
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

DROP TRIGGER IF EXISTS agro_communication_interaction_runs_capture_immutable
    ON agro_communication_interaction_runs;
CREATE TRIGGER agro_communication_interaction_runs_capture_immutable
    BEFORE UPDATE OF id, profile_id, endpoint_id, allocation_id, work_item_id,
        field_information_request_id, workflow_version_id, campaign_snapshot_id,
        legacy_prompt_id, context_token_hash, expected_intents_json, created_at, expires_at
    ON agro_communication_interaction_runs
    FOR EACH ROW EXECUTE FUNCTION agro_reject_interaction_capture_mutation();

DROP TRIGGER IF EXISTS agro_communication_interaction_runs_no_delete
    ON agro_communication_interaction_runs;
CREATE TRIGGER agro_communication_interaction_runs_no_delete
    BEFORE DELETE ON agro_communication_interaction_runs
    FOR EACH ROW EXECUTE FUNCTION agro_reject_interaction_delete();

DROP TRIGGER IF EXISTS agro_communication_interaction_dispatches_capture_immutable
    ON agro_communication_interaction_dispatches;
CREATE TRIGGER agro_communication_interaction_dispatches_capture_immutable
    BEFORE UPDATE OF id, interaction_run_id, provider, provider_message_id, created_at
    ON agro_communication_interaction_dispatches
    FOR EACH ROW EXECUTE FUNCTION agro_reject_interaction_capture_mutation();

DROP TRIGGER IF EXISTS agro_communication_interaction_dispatches_no_delete
    ON agro_communication_interaction_dispatches;
CREATE TRIGGER agro_communication_interaction_dispatches_no_delete
    BEFORE DELETE ON agro_communication_interaction_dispatches
    FOR EACH ROW EXECUTE FUNCTION agro_reject_interaction_delete();

DROP TRIGGER IF EXISTS agro_communication_workflow_versions_capture_immutable
    ON agro_communication_workflow_versions;
CREATE TRIGGER agro_communication_workflow_versions_capture_immutable
    BEFORE UPDATE OF id, workflow_id, version, purpose, owner_id, trigger_json,
        audience_json, template_id, expected_intents_json, response_deadline_hours,
        quiet_hours_json, frequency_cap, escalation_owner_id, created_at
    ON agro_communication_workflow_versions
    FOR EACH ROW EXECUTE FUNCTION agro_reject_workflow_capture_mutation();

DROP TRIGGER IF EXISTS agro_communication_workflow_versions_no_delete
    ON agro_communication_workflow_versions;
CREATE TRIGGER agro_communication_workflow_versions_no_delete
    BEFORE DELETE ON agro_communication_workflow_versions
    FOR EACH ROW EXECUTE FUNCTION agro_reject_workflow_capture_mutation();

DROP TRIGGER IF EXISTS agro_communication_workflow_versions_lifecycle_guard
    ON agro_communication_workflow_versions;
CREATE TRIGGER agro_communication_workflow_versions_lifecycle_guard
    BEFORE UPDATE OF status, published_at ON agro_communication_workflow_versions
    FOR EACH ROW EXECUTE FUNCTION agro_validate_workflow_version_lifecycle();

DROP TRIGGER IF EXISTS agro_communication_workflow_runs_no_update
    ON agro_communication_workflow_runs;
CREATE TRIGGER agro_communication_workflow_runs_no_update
    BEFORE UPDATE ON agro_communication_workflow_runs
    FOR EACH ROW EXECUTE FUNCTION agro_reject_workflow_run_mutation();

DROP TRIGGER IF EXISTS agro_communication_workflow_runs_no_delete
    ON agro_communication_workflow_runs;
CREATE TRIGGER agro_communication_workflow_runs_no_delete
    BEFORE DELETE ON agro_communication_workflow_runs
    FOR EACH ROW EXECUTE FUNCTION agro_reject_workflow_run_mutation();

REVOKE ALL ON TABLE agro_communication_profiles FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_endpoint_verifications FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_endpoint_scopes FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_scoped_consents FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_scoped_consent_events FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_interaction_runs FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_interaction_dispatches FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_workflows FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_workflow_versions FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_workflow_runs FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_scoped_consent_event_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_scoped_consent_capture_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_interaction_capture_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_interaction_delete() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_workflow_capture_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_reject_workflow_run_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_validate_workflow_version_lifecycle() FROM PUBLIC;

COMMIT;
