-- Private, deterministic vocabulary shared by maps, directories, profiles,
-- filters, and future natural-language controls.  This migration never
-- creates an identity, field boundary, diagnosis, or public API surface.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_place_catalog (
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    place_key TEXT NOT NULL CHECK (char_length(place_key) BETWEEN 3 AND 320),
    village_name TEXT,
    block_name TEXT,
    district_name TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    enrichment_version TEXT NOT NULL CHECK (char_length(enrichment_version) BETWEEN 1 AND 32),
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, place_key),
    CHECK (village_name IS NOT NULL OR block_name IS NOT NULL OR district_name IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS agro_idx_place_catalog_hierarchy
    ON agro_place_catalog (source_id, district_name, block_name, village_name);

CREATE TABLE IF NOT EXISTS agro_task_type_taxonomy (
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    task_type_key TEXT NOT NULL CHECK (char_length(task_type_key) BETWEEN 1 AND 160),
    task_kind TEXT NOT NULL CHECK (task_kind IN ('visit', 'registration', 'soil', 'query', 'team_work', 'other')),
    classification_state TEXT NOT NULL DEFAULT 'automatic'
        CHECK (classification_state IN ('automatic', 'reviewed')),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    enrichment_version TEXT NOT NULL CHECK (char_length(enrichment_version) BETWEEN 1 AND 32),
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, task_type_key)
);

CREATE INDEX IF NOT EXISTS agro_idx_task_type_taxonomy_kind
    ON agro_task_type_taxonomy (source_id, task_kind, last_seen_at DESC);

ALTER TABLE agro_entity_operating_snapshots
    ADD COLUMN IF NOT EXISTS place_key TEXT,
    ADD COLUMN IF NOT EXISTS linked_place_count INTEGER NOT NULL DEFAULT 0
        CHECK (linked_place_count >= 0),
    ADD COLUMN IF NOT EXISTS crop_profile TEXT NOT NULL DEFAULT 'not_recorded'
        CHECK (crop_profile IN ('pb1', '1718', 'mixed', 'not_recorded')),
    ADD COLUMN IF NOT EXISTS latest_activity_kind TEXT NOT NULL DEFAULT 'unknown'
        CHECK (latest_activity_kind IN ('registration', 'visit', 'issue', 'work', 'location', 'photo', 'attendance', 'unknown'));

CREATE INDEX IF NOT EXISTS agro_idx_entity_operating_snapshot_crop
    ON agro_entity_operating_snapshots (source_id, entity_kind, crop_profile, latest_activity_at DESC);

REVOKE ALL ON TABLE agro_place_catalog, agro_task_type_taxonomy FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_place_catalog, agro_task_type_taxonomy TO agro_vc_runtime;

COMMIT;
