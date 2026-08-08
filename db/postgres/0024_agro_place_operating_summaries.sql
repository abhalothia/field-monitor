-- Private rollups for fast village/block/district context.  These are derived
-- solely from the typed source graph and never establish a farm boundary,
-- ownership, or a diagnosis.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_place_operating_summaries (
    source_id TEXT NOT NULL,
    place_key TEXT NOT NULL,
    reported_farm_count INTEGER NOT NULL DEFAULT 0 CHECK (reported_farm_count >= 0),
    farmer_count INTEGER NOT NULL DEFAULT 0 CHECK (farmer_count >= 0),
    field_worker_count INTEGER NOT NULL DEFAULT 0 CHECK (field_worker_count >= 0),
    open_task_count INTEGER NOT NULL DEFAULT 0 CHECK (open_task_count >= 0),
    visit_count INTEGER NOT NULL DEFAULT 0 CHECK (visit_count >= 0),
    issue_report_count INTEGER NOT NULL DEFAULT 0 CHECK (issue_report_count >= 0),
    location_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (location_evidence_count >= 0),
    photo_reference_count INTEGER NOT NULL DEFAULT 0 CHECK (photo_reference_count >= 0),
    latest_activity_at TIMESTAMPTZ,
    enrichment_version TEXT NOT NULL CHECK (char_length(enrichment_version) BETWEEN 1 AND 32),
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, place_key),
    FOREIGN KEY (source_id, place_key)
        REFERENCES agro_place_catalog (source_id, place_key)
);

CREATE INDEX IF NOT EXISTS agro_idx_place_operating_summaries_activity
    ON agro_place_operating_summaries (source_id, latest_activity_at DESC);

CREATE INDEX IF NOT EXISTS agro_idx_place_operating_summaries_open_work
    ON agro_place_operating_summaries (source_id, open_task_count DESC, latest_activity_at DESC);

REVOKE ALL ON TABLE agro_place_operating_summaries FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_place_operating_summaries TO agro_vc_runtime;

COMMIT;
