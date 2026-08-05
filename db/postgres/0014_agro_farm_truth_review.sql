-- Private manager review state bridging read-only TrackWick evidence to
-- canonical Farm Truth.  This schema is not exposed through the Data API.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_farm_truth_review_cases (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    registration_id TEXT NOT NULL REFERENCES agro_trackwick_registrations(id),
    plot_id TEXT NOT NULL REFERENCES agro_trackwick_registration_plots(id),
    candidate_fingerprint TEXT NOT NULL CHECK (
        char_length(candidate_fingerprint) = 64
        AND candidate_fingerprint = lower(candidate_fingerprint)
        AND candidate_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    status TEXT NOT NULL CHECK (status IN (
        'open', 'accepting', 'needs_evidence', 'accepted', 'rejected'
    )),
    evidence_summary_json JSONB NOT NULL CHECK (jsonb_typeof(evidence_summary_json) = 'object'),
    review_reason TEXT,
    missing_evidence_kind TEXT CHECK (missing_evidence_kind IS NULL OR missing_evidence_kind IN (
        'plot_area', 'crop_season', 'right_to_operate', 'farmer_identity',
        'field_worker_assignment'
    )),
    owner_person_id TEXT REFERENCES agro_people(id),
    reviewed_by_person_id TEXT REFERENCES agro_people(id),
    reviewed_at TIMESTAMPTZ,
    accepted_land_parcel_id TEXT REFERENCES agro_land_parcels(id),
    accepted_operational_block_id TEXT REFERENCES agro_operational_blocks(id),
    accepted_crop_allocation_id TEXT REFERENCES agro_crop_allocations(id),
    accepted_grower_person_id TEXT REFERENCES agro_people(id),
    accepted_field_worker_person_id TEXT REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (plot_id, candidate_fingerprint),
    CHECK (
        (status IN ('open', 'accepting')
            AND review_reason IS NULL AND missing_evidence_kind IS NULL
            AND owner_person_id IS NULL AND reviewed_by_person_id IS NULL
            AND reviewed_at IS NULL AND accepted_land_parcel_id IS NULL
            AND accepted_operational_block_id IS NULL
            AND accepted_crop_allocation_id IS NULL
            AND accepted_grower_person_id IS NULL
            AND accepted_field_worker_person_id IS NULL)
        OR (status = 'needs_evidence'
            AND review_reason IS NOT NULL AND missing_evidence_kind IS NOT NULL
            AND owner_person_id IS NOT NULL AND reviewed_by_person_id IS NOT NULL
            AND reviewed_at IS NOT NULL AND accepted_land_parcel_id IS NULL
            AND accepted_operational_block_id IS NULL
            AND accepted_crop_allocation_id IS NULL
            AND accepted_grower_person_id IS NULL
            AND accepted_field_worker_person_id IS NULL)
        OR (status = 'rejected'
            AND review_reason IS NOT NULL AND missing_evidence_kind IS NULL
            AND owner_person_id IS NULL AND reviewed_by_person_id IS NOT NULL
            AND reviewed_at IS NOT NULL AND accepted_land_parcel_id IS NULL
            AND accepted_operational_block_id IS NULL
            AND accepted_crop_allocation_id IS NULL
            AND accepted_grower_person_id IS NULL
            AND accepted_field_worker_person_id IS NULL)
        OR (status = 'accepted'
            AND review_reason IS NOT NULL AND missing_evidence_kind IS NULL
            AND owner_person_id IS NULL AND reviewed_by_person_id IS NOT NULL
            AND reviewed_at IS NOT NULL AND accepted_land_parcel_id IS NOT NULL
            AND accepted_operational_block_id IS NOT NULL
            AND accepted_crop_allocation_id IS NOT NULL
            AND accepted_grower_person_id IS NOT NULL)
    )
);

CREATE OR REPLACE FUNCTION agro_guard_farm_truth_review_case()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = agro, pg_catalog
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'farm truth review cases are append-only';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.registration_id IS DISTINCT FROM OLD.registration_id
       OR NEW.plot_id IS DISTINCT FROM OLD.plot_id
       OR NEW.candidate_fingerprint IS DISTINCT FROM OLD.candidate_fingerprint
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'farm truth review case source is immutable';
    END IF;
    IF NOT (
        (OLD.status = 'open' AND NEW.status IN ('accepting', 'needs_evidence', 'rejected'))
        OR (OLD.status = 'accepting' AND NEW.status = 'accepted')
        OR (OLD.status = NEW.status
            AND OLD.review_reason IS NOT DISTINCT FROM NEW.review_reason
            AND OLD.missing_evidence_kind IS NOT DISTINCT FROM NEW.missing_evidence_kind
            AND OLD.owner_person_id IS NOT DISTINCT FROM NEW.owner_person_id
            AND OLD.reviewed_by_person_id IS NOT DISTINCT FROM NEW.reviewed_by_person_id
            AND OLD.reviewed_at IS NOT DISTINCT FROM NEW.reviewed_at
            AND OLD.accepted_land_parcel_id IS NOT DISTINCT FROM NEW.accepted_land_parcel_id
            AND OLD.accepted_operational_block_id IS NOT DISTINCT FROM NEW.accepted_operational_block_id
            AND OLD.accepted_crop_allocation_id IS NOT DISTINCT FROM NEW.accepted_crop_allocation_id
            AND OLD.accepted_grower_person_id IS NOT DISTINCT FROM NEW.accepted_grower_person_id
            AND OLD.accepted_field_worker_person_id IS NOT DISTINCT FROM NEW.accepted_field_worker_person_id)
    ) THEN
        RAISE EXCEPTION 'invalid farm truth review case transition';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agro_farm_truth_review_cases_guard ON agro_farm_truth_review_cases;
CREATE TRIGGER agro_farm_truth_review_cases_guard
BEFORE UPDATE OR DELETE ON agro_farm_truth_review_cases
FOR EACH ROW EXECUTE FUNCTION agro_guard_farm_truth_review_case();

CREATE INDEX IF NOT EXISTS agro_idx_farm_truth_review_cases_status_updated
    ON agro_farm_truth_review_cases (status, updated_at DESC);
CREATE INDEX IF NOT EXISTS agro_idx_farm_truth_review_cases_registration_plot
    ON agro_farm_truth_review_cases (registration_id, plot_id);
CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_trackwick_plot_links_one_reviewed
    ON agro_trackwick_plot_operating_links (plot_id) WHERE link_status = 'reviewed';

REVOKE ALL ON TABLE agro_farm_truth_review_cases FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION agro_guard_farm_truth_review_case() FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_farm_truth_review_cases TO agro_vc_runtime;

COMMIT;
