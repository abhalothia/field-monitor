-- A manager may establish a canonical Farm and a reviewed Grower relationship
-- from a completed TrackWick registration.  This deliberately does not create
-- a Field, boundary, crop allocation, area, or right-to-operate assertion.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_farm_grower_relationships (
    id TEXT PRIMARY KEY,
    farm_id TEXT NOT NULL REFERENCES agro_farms(id),
    person_id TEXT NOT NULL REFERENCES agro_people(id),
    starts_on DATE NOT NULL,
    ends_on DATE,
    status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
    provenance TEXT NOT NULL,
    reviewed_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK ((status = 'active' AND ends_on IS NULL) OR (status = 'ended' AND ends_on IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_farm_growers_one_active
    ON agro_farm_grower_relationships (farm_id, person_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS agro_farm_candidate_review_cases (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    registration_id TEXT NOT NULL REFERENCES agro_trackwick_registrations(id),
    candidate_fingerprint TEXT NOT NULL CHECK (
        char_length(candidate_fingerprint) = 64
        AND candidate_fingerprint = lower(candidate_fingerprint)
        AND candidate_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    status TEXT NOT NULL CHECK (status IN ('open', 'accepting', 'held', 'accepted', 'rejected')),
    evidence_summary_json JSONB NOT NULL CHECK (jsonb_typeof(evidence_summary_json) = 'object'),
    review_reason TEXT,
    owner_person_id TEXT REFERENCES agro_people(id),
    reviewed_by_person_id TEXT REFERENCES agro_people(id),
    reviewed_at TIMESTAMPTZ,
    accepted_farm_id TEXT REFERENCES agro_farms(id),
    accepted_grower_person_id TEXT REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (registration_id, candidate_fingerprint),
    CHECK (
        (status IN ('open', 'accepting')
            AND review_reason IS NULL AND owner_person_id IS NULL
            AND reviewed_by_person_id IS NULL AND reviewed_at IS NULL
            AND accepted_farm_id IS NULL AND accepted_grower_person_id IS NULL)
        OR (status = 'held'
            AND review_reason IS NOT NULL AND owner_person_id IS NOT NULL
            AND reviewed_by_person_id IS NOT NULL AND reviewed_at IS NOT NULL
            AND accepted_farm_id IS NULL AND accepted_grower_person_id IS NULL)
        OR (status = 'rejected'
            AND review_reason IS NOT NULL AND owner_person_id IS NULL
            AND reviewed_by_person_id IS NOT NULL AND reviewed_at IS NOT NULL
            AND accepted_farm_id IS NULL AND accepted_grower_person_id IS NULL)
        OR (status = 'accepted'
            AND review_reason IS NOT NULL AND owner_person_id IS NULL
            AND reviewed_by_person_id IS NOT NULL AND reviewed_at IS NOT NULL
            AND accepted_farm_id IS NOT NULL AND accepted_grower_person_id IS NOT NULL)
    )
);

CREATE OR REPLACE FUNCTION agro_guard_farm_candidate_review_case()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = agro, pg_catalog
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'farm candidate review cases are append-only';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.registration_id IS DISTINCT FROM OLD.registration_id
       OR NEW.candidate_fingerprint IS DISTINCT FROM OLD.candidate_fingerprint
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'farm candidate review case source is immutable';
    END IF;
    IF NOT ((OLD.status = 'open' AND NEW.status IN ('open', 'accepting', 'held', 'rejected'))
         OR (OLD.status = 'accepting' AND NEW.status = 'accepted')) THEN
        RAISE EXCEPTION 'invalid farm candidate review case transition';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agro_farm_candidate_review_cases_guard ON agro_farm_candidate_review_cases;
CREATE TRIGGER agro_farm_candidate_review_cases_guard
BEFORE UPDATE OR DELETE ON agro_farm_candidate_review_cases
FOR EACH ROW EXECUTE FUNCTION agro_guard_farm_candidate_review_case();

CREATE INDEX IF NOT EXISTS agro_idx_farm_candidate_review_cases_status_updated
    ON agro_farm_candidate_review_cases (status, updated_at DESC);

REVOKE ALL ON TABLE agro_farm_grower_relationships, agro_farm_candidate_review_cases FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION agro_guard_farm_candidate_review_case() FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_farm_grower_relationships, agro_farm_candidate_review_cases TO agro_vc_runtime;

COMMIT;
