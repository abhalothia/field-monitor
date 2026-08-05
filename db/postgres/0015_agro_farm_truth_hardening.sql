-- Final Farm Truth hardening: exact task/plot provenance, immutable reviewed
-- links, and the least-privilege server role required for reviewed acceptance.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

ALTER TABLE agro_trackwick_tasks
    ADD COLUMN IF NOT EXISTS provider_plot_reference TEXT;

CREATE TABLE IF NOT EXISTS agro_trackwick_task_plot_links (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_run_id TEXT REFERENCES agro_source_runs(id),
    task_id TEXT NOT NULL REFERENCES agro_trackwick_tasks(id),
    registration_id TEXT NOT NULL REFERENCES agro_trackwick_registrations(id),
    plot_id TEXT NOT NULL REFERENCES agro_trackwick_registration_plots(id),
    association_kind TEXT NOT NULL CHECK (association_kind = 'source_explicit'),
    source_fingerprint TEXT NOT NULL CHECK (
        char_length(source_fingerprint) = 64
        AND source_fingerprint = lower(source_fingerprint)
        AND source_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    mapping_version TEXT NOT NULL,
    data_quality_status TEXT NOT NULL CHECK (
        data_quality_status IN ('valid', 'incomplete', 'quarantined')
    ),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (task_id)
);

CREATE INDEX IF NOT EXISTS agro_idx_trackwick_task_plot_links_plot
    ON agro_trackwick_task_plot_links (plot_id, registration_id, data_quality_status);
CREATE INDEX IF NOT EXISTS agro_idx_trackwick_task_plot_links_task
    ON agro_trackwick_task_plot_links (task_id, data_quality_status);
CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_trackwick_task_plot_links_one_plot_per_task
    ON agro_trackwick_task_plot_links (task_id);

CREATE OR REPLACE FUNCTION agro_guard_reviewed_trackwick_link()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = agro, pg_catalog
AS $$
BEGIN
    IF OLD.link_status = 'reviewed' THEN
        RAISE EXCEPTION 'reviewed TrackWick links are immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agro_trackwick_party_person_links_reviewed_guard
    ON agro_trackwick_party_person_links;
CREATE TRIGGER agro_trackwick_party_person_links_reviewed_guard
BEFORE UPDATE OR DELETE ON agro_trackwick_party_person_links
FOR EACH ROW EXECUTE FUNCTION agro_guard_reviewed_trackwick_link();

DROP TRIGGER IF EXISTS agro_trackwick_plot_operating_links_reviewed_guard
    ON agro_trackwick_plot_operating_links;
CREATE TRIGGER agro_trackwick_plot_operating_links_reviewed_guard
BEFORE UPDATE OR DELETE ON agro_trackwick_plot_operating_links
FOR EACH ROW EXECUTE FUNCTION agro_guard_reviewed_trackwick_link();

DROP TRIGGER IF EXISTS agro_trackwick_task_allocation_links_reviewed_guard
    ON agro_trackwick_task_allocation_links;
CREATE TRIGGER agro_trackwick_task_allocation_links_reviewed_guard
BEFORE UPDATE OR DELETE ON agro_trackwick_task_allocation_links
FOR EACH ROW EXECUTE FUNCTION agro_guard_reviewed_trackwick_link();

REVOKE ALL ON TABLE agro_trackwick_task_plot_links FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION agro_guard_reviewed_trackwick_link() FROM PUBLIC, anon, authenticated;

-- Earlier runtime migrations allowed provider-ingest updates across all link
-- tables. These three relations are review provenance, not provider source
-- rows; the application only reads and appends them.
REVOKE UPDATE ON TABLE agro_trackwick_party_person_links FROM agro_vc_runtime;
REVOKE UPDATE ON TABLE agro_trackwick_plot_operating_links FROM agro_vc_runtime;
REVOKE UPDATE ON TABLE agro_trackwick_task_allocation_links FROM agro_vc_runtime;
REVOKE UPDATE ON TABLE agro_farm_truth_review_cases FROM agro_vc_runtime;

-- Current-context and exact private source reads.
GRANT SELECT ON TABLE
    agro_operating_units,
    agro_seasons,
    agro_source_registry,
    agro_trackwick_parties,
    agro_trackwick_tasks,
    agro_trackwick_visits,
    agro_trackwick_registrations,
    agro_trackwick_registration_plots,
    agro_trackwick_task_plot_links
TO agro_vc_runtime;

-- Provider refresh may reconcile only this derived source association.  It
-- cannot mutate registrations, plots, reviewed links, or canonical records.
GRANT INSERT, UPDATE ON TABLE agro_trackwick_task_plot_links TO agro_vc_runtime;

-- Canonical/reviewed records read by replay, directory, and conflict checks.
GRANT SELECT ON TABLE
    agro_land_parcels,
    agro_operational_blocks,
    agro_block_parcels,
    agro_rights_to_operate,
    agro_crop_allocations,
    agro_people,
    agro_person_operating_relationships,
    agro_trackwick_party_person_links,
    agro_trackwick_plot_operating_links,
    agro_trackwick_task_allocation_links,
    agro_audit_events,
    agro_farm_truth_review_cases
TO agro_vc_runtime;

-- One accepted decision appends this exact canonical set. No source table is
-- writable through this grant and no canonical relation receives update or
-- removal authority.
GRANT INSERT ON TABLE
    agro_land_parcels,
    agro_operational_blocks,
    agro_block_parcels,
    agro_rights_to_operate,
    agro_crop_allocations,
    agro_people,
    agro_person_operating_relationships,
    agro_trackwick_party_person_links,
    agro_trackwick_plot_operating_links,
    agro_trackwick_task_allocation_links,
    agro_audit_events,
    agro_farm_truth_review_cases
TO agro_vc_runtime;

-- The review-case state machine is the only Farm Truth row updated in place.
-- Source identity, candidate fingerprint, and creation time remain immutable.
GRANT UPDATE (
    status,
    evidence_summary_json,
    review_reason,
    missing_evidence_kind,
    owner_person_id,
    reviewed_by_person_id,
    reviewed_at,
    accepted_land_parcel_id,
    accepted_operational_block_id,
    accepted_crop_allocation_id,
    accepted_grower_person_id,
    accepted_field_worker_person_id,
    updated_at
) ON agro_farm_truth_review_cases TO agro_vc_runtime;

COMMIT;
