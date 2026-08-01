-- FFL administrative context and first-party soil baseline contract.
--
-- Apply manually, after 0001_agro_private_schema.sql, with the reviewed
-- private PostgreSQL migration role.  This migration intentionally contains
-- no external fetches and exposes no new relation through Supabase's Data API.

BEGIN;
SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_operating_unit_locations (
    id TEXT PRIMARY KEY,
    operating_unit_id TEXT NOT NULL REFERENCES agro_operating_units(id),
    country_code TEXT NOT NULL CHECK (country_code = 'IN'),
    state_name TEXT NOT NULL,
    district_name TEXT NOT NULL,
    district_context_key TEXT NOT NULL,
    subdistrict_name TEXT,
    village_name TEXT,
    pincode TEXT CHECK (pincode IS NULL OR pincode ~ '^[0-9]{6}$'),
    verification_method TEXT NOT NULL CHECK (verification_method IN ('field_verified', 'lgd_reference')),
    verified_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    verified_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
    supersedes_location_id TEXT REFERENCES agro_operating_unit_locations(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_soil_baselines (
    id TEXT PRIMARY KEY,
    operating_unit_id TEXT NOT NULL REFERENCES agro_operating_units(id),
    sampled_on DATE NOT NULL,
    depth_cm_start DOUBLE PRECISION CHECK (depth_cm_start IS NULL OR depth_cm_start >= 0),
    depth_cm_end DOUBLE PRECISION CHECK (depth_cm_end IS NULL OR depth_cm_end >= 0),
    lab_name TEXT NOT NULL,
    measurements_json JSONB NOT NULL,
    evidence_artifact_id TEXT NOT NULL REFERENCES agro_evidence_artifacts(id),
    reviewed_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    status TEXT NOT NULL CHECK (status IN ('reviewed', 'superseded')),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (depth_cm_start IS NULL OR depth_cm_end IS NULL OR depth_cm_end >= depth_cm_start)
);

CREATE INDEX IF NOT EXISTS agro_idx_operating_unit_locations_operating_unit
    ON agro_operating_unit_locations (operating_unit_id, verified_at);
CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_operating_unit_locations_one_active
    ON agro_operating_unit_locations (operating_unit_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS agro_idx_operating_unit_locations_verified_by
    ON agro_operating_unit_locations (verified_by_person_id);
CREATE INDEX IF NOT EXISTS agro_idx_operating_unit_locations_supersedes
    ON agro_operating_unit_locations (supersedes_location_id);
CREATE INDEX IF NOT EXISTS agro_idx_soil_baselines_operating_unit_sampled
    ON agro_soil_baselines (operating_unit_id, sampled_on, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_soil_baselines_evidence_artifact
    ON agro_soil_baselines (evidence_artifact_id);
CREATE INDEX IF NOT EXISTS agro_idx_soil_baselines_reviewed_by
    ON agro_soil_baselines (reviewed_by_person_id);

REVOKE ALL ON TABLE agro_operating_unit_locations, agro_soil_baselines FROM PUBLIC;

COMMIT;
