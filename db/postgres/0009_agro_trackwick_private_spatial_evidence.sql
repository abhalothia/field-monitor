-- Private typed TrackWick source and spatial evidence lane.
-- This never creates canonical farms, parcels, people, allocations, decisions,
-- or public data. Apply manually with the reviewed private migration role.

BEGIN;

CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_trackwick_parties (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    party_kind TEXT NOT NULL CHECK (party_kind IN ('farmer', 'field_worker')),
    provider_identifier TEXT NOT NULL,
    display_name TEXT NOT NULL,
    crm_status TEXT,
    provider_owner_identifier TEXT,
    provider_tag TEXT,
    provider_created_at TIMESTAMPTZ,
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, party_kind, provider_identifier)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_contact_points (
    id TEXT PRIMARY KEY,
    party_id TEXT NOT NULL REFERENCES agro_trackwick_parties(id),
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    contact_kind TEXT NOT NULL CHECK (contact_kind = 'mobile'),
    contact_value TEXT NOT NULL,
    value_fingerprint TEXT NOT NULL CHECK (char_length(value_fingerprint) = 64 AND value_fingerprint = lower(value_fingerprint)),
    consent_status TEXT NOT NULL CHECK (consent_status IN ('unknown', 'granted', 'revoked')),
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (party_id, contact_kind, value_fingerprint)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_tasks (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    provider_task_id TEXT NOT NULL,
    farmer_party_id TEXT REFERENCES agro_trackwick_parties(id),
    field_worker_party_id TEXT REFERENCES agro_trackwick_parties(id),
    provider_customer_identifier TEXT,
    task_type TEXT NOT NULL,
    task_status TEXT NOT NULL CHECK (task_status IN ('completed', 'in_progress', 'pending', 'unknown')),
    provider_created_at TIMESTAMPTZ,
    provider_started_at TIMESTAMPTZ,
    provider_completed_at TIMESTAMPTZ,
    provider_follow_up_at TIMESTAMPTZ,
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, provider_task_id)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_visits (
    task_id TEXT PRIMARY KEY REFERENCES agro_trackwick_tasks(id),
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    observed_at TIMESTAMPTZ NOT NULL,
    transplanted_on DATE,
    crop_stage TEXT,
    water_condition TEXT,
    crop_condition_score NUMERIC(4, 1) CHECK (crop_condition_score IS NULL OR (crop_condition_score >= 1 AND crop_condition_score <= 10)),
    kit_status TEXT NOT NULL CHECK (kit_status IN ('taken', 'not_taken', 'unknown')),
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_trackwick_visit_findings (
    id TEXT PRIMARY KEY,
    visit_task_id TEXT NOT NULL REFERENCES agro_trackwick_visits(task_id),
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    finding_kind TEXT NOT NULL CHECK (finding_kind IN ('pest', 'disease')),
    reported_value TEXT NOT NULL,
    source_field TEXT NOT NULL,
    declared_severity TEXT NOT NULL CHECK (declared_severity IN ('unknown', 'low', 'moderate', 'high', 'critical')),
    observed_at TIMESTAMPTZ NOT NULL,
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (visit_task_id, finding_kind, source_field, reported_value)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_crop_inputs (
    id TEXT PRIMARY KEY,
    visit_task_id TEXT NOT NULL REFERENCES agro_trackwick_visits(task_id),
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    input_kind TEXT NOT NULL CHECK (input_kind IN ('pesticide', 'fertilizer')),
    event_kind TEXT NOT NULL CHECK (event_kind IN ('applied', 'recommended')),
    reported_product TEXT NOT NULL,
    source_field TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (visit_task_id, input_kind, event_kind, source_field, reported_product)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_registrations (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE REFERENCES agro_trackwick_tasks(id),
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    farmer_party_id TEXT REFERENCES agro_trackwick_parties(id),
    registration_status TEXT NOT NULL CHECK (registration_status IN ('completed', 'in_progress', 'pending', 'unknown')),
    village_name TEXT,
    block_name TEXT,
    district_name TEXT,
    reported_total_area_acres NUMERIC(12, 3),
    reported_plot_count INTEGER CHECK (reported_plot_count IS NULL OR reported_plot_count >= 0),
    reported_pb1_area_acres NUMERIC(12, 3),
    reported_1718_area_acres NUMERIC(12, 3),
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_trackwick_registration_plots (
    id TEXT PRIMARY KEY,
    registration_id TEXT NOT NULL REFERENCES agro_trackwick_registrations(id),
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    gata_number TEXT,
    reported_area_bigha NUMERIC(12, 3),
    plot_type TEXT,
    village_name TEXT,
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (registration_id, ordinal)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_media_references (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    task_id TEXT NOT NULL REFERENCES agro_trackwick_tasks(id),
    provider_media_key TEXT NOT NULL,
    media_kind TEXT NOT NULL CHECK (media_kind IN ('crop_photo', 'plot_photo')),
    remote_url TEXT NOT NULL CHECK (remote_url ~ '^https://trackolap-images-prod\\.s3\\.amazonaws\\.com/'),
    provider_created_at TIMESTAMPTZ,
    source_access_state TEXT NOT NULL CHECK (source_access_state IN ('available', 'unavailable', 'blocked')),
    content_state TEXT NOT NULL CHECK (content_state IN ('remote_only', 'retained', 'failed')),
    exif_state TEXT NOT NULL CHECK (exif_state IN ('not_checked', 'extracted', 'absent', 'unreadable')),
    content_hash TEXT CHECK (content_hash IS NULL OR (char_length(content_hash) = 64 AND content_hash = lower(content_hash))),
    content_type TEXT,
    size_bytes BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, provider_media_key)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_location_observations (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    task_id TEXT REFERENCES agro_trackwick_tasks(id),
    registration_id TEXT REFERENCES agro_trackwick_registrations(id),
    media_reference_id TEXT REFERENCES agro_trackwick_media_references(id),
    provider_location_key TEXT NOT NULL,
    location_kind TEXT NOT NULL CHECK (location_kind IN (
        'task_completion', 'visit_location', 'registration', 'media_capture', 'crm', 'soil'
    )),
    location_confidence TEXT NOT NULL CHECK (location_confidence IN ('declared', 'observed', 'verified')),
    latitude NUMERIC(9, 6) NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
    longitude NUMERIC(9, 6) NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
    geog extensions.geography(POINT, 4326) NOT NULL,
    provider_address TEXT,
    provider_geo_address TEXT,
    provider_accuracy_m NUMERIC(10, 2) CHECK (provider_accuracy_m IS NULL OR provider_accuracy_m >= 0),
    observed_at TIMESTAMPTZ NOT NULL,
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (task_id IS NOT NULL OR registration_id IS NOT NULL OR media_reference_id IS NOT NULL),
    UNIQUE (source_id, provider_location_key)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_worker_days (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    field_worker_party_id TEXT NOT NULL REFERENCES agro_trackwick_parties(id),
    observed_on DATE NOT NULL,
    attendance_status TEXT NOT NULL CHECK (attendance_status IN ('present', 'not_punched', 'unknown')),
    reported_start_time TEXT,
    reported_total_time TEXT,
    source_fingerprint TEXT NOT NULL CHECK (char_length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (field_worker_party_id, observed_on)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_party_person_links (
    id TEXT PRIMARY KEY,
    party_id TEXT NOT NULL REFERENCES agro_trackwick_parties(id),
    person_id TEXT NOT NULL REFERENCES agro_people(id),
    link_status TEXT NOT NULL CHECK (link_status IN ('proposed', 'reviewed', 'rejected')),
    reviewed_by_person_id TEXT REFERENCES agro_people(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (party_id, person_id)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_plot_operating_links (
    id TEXT PRIMARY KEY,
    plot_id TEXT NOT NULL REFERENCES agro_trackwick_registration_plots(id),
    land_parcel_id TEXT REFERENCES agro_land_parcels(id),
    operational_block_id TEXT REFERENCES agro_operational_blocks(id),
    link_status TEXT NOT NULL CHECK (link_status IN ('proposed', 'reviewed', 'rejected')),
    reviewed_by_person_id TEXT REFERENCES agro_people(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (land_parcel_id IS NOT NULL OR operational_block_id IS NOT NULL),
    UNIQUE (plot_id, land_parcel_id, operational_block_id)
);

CREATE TABLE IF NOT EXISTS agro_trackwick_task_allocation_links (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES agro_trackwick_tasks(id),
    crop_allocation_id TEXT NOT NULL REFERENCES agro_crop_allocations(id),
    link_status TEXT NOT NULL CHECK (link_status IN ('proposed', 'reviewed', 'rejected')),
    reviewed_by_person_id TEXT REFERENCES agro_people(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (task_id, crop_allocation_id)
);

CREATE OR REPLACE FUNCTION agro_set_trackwick_location_geog()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = agro, pg_catalog, extensions
AS $$
BEGIN
    NEW.geog := extensions.ST_SetSRID(
        extensions.ST_MakePoint(NEW.longitude, NEW.latitude),
        4326
    )::extensions.geography;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agro_trackwick_locations_set_geog ON agro_trackwick_location_observations;
CREATE TRIGGER agro_trackwick_locations_set_geog
BEFORE INSERT OR UPDATE OF latitude, longitude ON agro_trackwick_location_observations
FOR EACH ROW EXECUTE FUNCTION agro_set_trackwick_location_geog();

CREATE INDEX IF NOT EXISTS agro_idx_trackwick_parties_source_kind
    ON agro_trackwick_parties (source_id, party_kind, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_contacts_party
    ON agro_trackwick_contact_points (party_id, contact_kind);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_tasks_farmer_created
    ON agro_trackwick_tasks (farmer_party_id, provider_created_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_tasks_worker_created
    ON agro_trackwick_tasks (field_worker_party_id, provider_created_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_tasks_open
    ON agro_trackwick_tasks (source_id, provider_created_at DESC)
    WHERE task_status IN ('pending', 'in_progress');
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_visits_observed
    ON agro_trackwick_visits (observed_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_findings_visit
    ON agro_trackwick_visit_findings (visit_task_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_inputs_visit
    ON agro_trackwick_crop_inputs (visit_task_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_registrations_farmer
    ON agro_trackwick_registrations (farmer_party_id, registration_status);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_plots_registration
    ON agro_trackwick_registration_plots (registration_id, ordinal);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_media_task
    ON agro_trackwick_media_references (task_id, provider_created_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_locations_geog
    ON agro_trackwick_location_observations USING GIST (geog);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_locations_source_time
    ON agro_trackwick_location_observations (source_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_locations_task
    ON agro_trackwick_location_observations (task_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_worker_days_worker_date
    ON agro_trackwick_worker_days (field_worker_party_id, observed_on DESC);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_party_links_person
    ON agro_trackwick_party_person_links (person_id, link_status);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_plot_links_parcel
    ON agro_trackwick_plot_operating_links (land_parcel_id, link_status);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_plot_links_block
    ON agro_trackwick_plot_operating_links (operational_block_id, link_status);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_task_links_allocation
    ON agro_trackwick_task_allocation_links (crop_allocation_id, link_status);

REVOKE ALL ON TABLE agro_trackwick_parties, agro_trackwick_contact_points,
    agro_trackwick_tasks, agro_trackwick_visits, agro_trackwick_visit_findings,
    agro_trackwick_crop_inputs, agro_trackwick_registrations,
    agro_trackwick_registration_plots, agro_trackwick_media_references,
    agro_trackwick_location_observations, agro_trackwick_worker_days,
    agro_trackwick_party_person_links, agro_trackwick_plot_operating_links,
    agro_trackwick_task_allocation_links FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_set_trackwick_location_geog() FROM PUBLIC;

COMMIT;

