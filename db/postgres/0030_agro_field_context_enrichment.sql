-- Latest stated field context for the private operating cache.  These are
-- visit facts, not predicted crop state, diagnosis, or field-boundary claims.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

ALTER TABLE agro_entity_operating_snapshots
    ADD COLUMN IF NOT EXISTS reported_plot_count INTEGER NOT NULL DEFAULT 0
        CHECK (reported_plot_count >= 0),
    ADD COLUMN IF NOT EXISTS latest_crop_stage TEXT,
    ADD COLUMN IF NOT EXISTS latest_water_condition TEXT,
    ADD COLUMN IF NOT EXISTS latest_kit_status TEXT,
    ADD COLUMN IF NOT EXISTS latest_field_observed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS agro_idx_entity_operating_snapshot_field_context
    ON agro_entity_operating_snapshots (source_id, entity_kind, latest_field_observed_at DESC);

REVOKE ALL ON TABLE agro_entity_operating_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_entity_operating_snapshots TO agro_vc_runtime;

COMMIT;
