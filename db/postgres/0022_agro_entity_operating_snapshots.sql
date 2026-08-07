-- Private, deterministic operating facts for fast manager read models.
-- This is derived context only: it does not create a canonical farm, identity,
-- field boundary, diagnosis, or provider-facing API surface.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_entity_operating_snapshots (
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('reported_farm', 'farmer', 'field_worker')),
    entity_id TEXT NOT NULL,
    farm_count INTEGER NOT NULL DEFAULT 0 CHECK (farm_count >= 0),
    farmer_count INTEGER NOT NULL DEFAULT 0 CHECK (farmer_count >= 0),
    open_task_count INTEGER NOT NULL DEFAULT 0 CHECK (open_task_count >= 0),
    completed_work_count INTEGER NOT NULL DEFAULT 0 CHECK (completed_work_count >= 0),
    visit_count INTEGER NOT NULL DEFAULT 0 CHECK (visit_count >= 0),
    disease_report_count INTEGER NOT NULL DEFAULT 0 CHECK (disease_report_count >= 0),
    pest_report_count INTEGER NOT NULL DEFAULT 0 CHECK (pest_report_count >= 0),
    location_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (location_evidence_count >= 0),
    photo_reference_count INTEGER NOT NULL DEFAULT 0 CHECK (photo_reference_count >= 0),
    attendance_present_days INTEGER NOT NULL DEFAULT 0 CHECK (attendance_present_days >= 0),
    reported_area_acres NUMERIC(12, 3) CHECK (reported_area_acres IS NULL OR reported_area_acres >= 0),
    latest_activity_at TIMESTAMPTZ,
    enrichment_version TEXT NOT NULL CHECK (char_length(enrichment_version) BETWEEN 1 AND 32),
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, entity_kind, entity_id)
);

CREATE INDEX IF NOT EXISTS agro_idx_entity_operating_snapshot_activity
    ON agro_entity_operating_snapshots (source_id, entity_kind, latest_activity_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_entity_operating_snapshot_open_work
    ON agro_entity_operating_snapshots (source_id, entity_kind, open_task_count DESC, latest_activity_at DESC);

REVOKE ALL ON TABLE agro_entity_operating_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_entity_operating_snapshots TO agro_vc_runtime;

COMMIT;
