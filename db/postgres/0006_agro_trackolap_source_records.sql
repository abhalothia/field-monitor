-- TrackOlap/TrackWick remains a private, read-only partner context lane.
-- Apply manually with a reviewed migration role; browser clients get no grant.

BEGIN;
SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_trackolap_records (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    import_batch_id TEXT REFERENCES agro_import_batches(id),
    feed TEXT NOT NULL CHECK (feed IN (
        'officers', 'attendance', 'farmer_tasks', 'visits',
        'issue_observations', 'pesticide_events'
    )),
    source_identifier TEXT NOT NULL,
    source_updated_at TIMESTAMPTZ NOT NULL,
    tenant_id TEXT NOT NULL,
    values_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('valid', 'quarantined', 'published')),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, feed, source_identifier, source_updated_at)
);

CREATE INDEX IF NOT EXISTS idx_agro_trackolap_records_source_status_feed
    ON agro_trackolap_records (source_id, status, feed, source_updated_at);

COMMIT;
