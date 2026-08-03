-- Native field capture, intentionally separate from source ingestion and
-- communications. Apply manually after reviewed migrations 0001-0006 with
-- the private agro migration role. Nothing here exposes a table through
-- Supabase's public Data API or stores a raw browser capability token.

BEGIN;
SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_field_capture_passes (
    id TEXT PRIMARY KEY,
    field_information_request_id TEXT NOT NULL REFERENCES agro_field_information_requests(id),
    signal_template_id TEXT NOT NULL REFERENCES agro_signal_templates(id),
    signal_template_version INTEGER NOT NULL CHECK (signal_template_version > 0),
    token_hash TEXT NOT NULL UNIQUE CHECK (char_length(token_hash) = 64 AND token_hash = lower(token_hash)),
    issued_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'used', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK ((status = 'revoked' AND revoked_at IS NOT NULL) OR (status <> 'revoked' AND revoked_at IS NULL))
);

CREATE TABLE IF NOT EXISTS agro_field_capture_candidates (
    id TEXT PRIMARY KEY,
    field_information_request_id TEXT NOT NULL REFERENCES agro_field_information_requests(id),
    field_capture_pass_id TEXT NOT NULL REFERENCES agro_field_capture_passes(id),
    allocation_id TEXT NOT NULL REFERENCES agro_crop_allocations(id),
    actor_person_id TEXT NOT NULL REFERENCES agro_people(id),
    signal_template_id TEXT NOT NULL REFERENCES agro_signal_templates(id),
    signal_template_version INTEGER NOT NULL CHECK (signal_template_version > 0),
    observed_at TIMESTAMPTZ NOT NULL,
    values_json JSONB NOT NULL,
    evidence_artifact_id TEXT REFERENCES agro_evidence_artifacts(id),
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('review', 'accepting', 'accepted', 'rejected')),
    reviewed_by_person_id TEXT REFERENCES agro_people(id),
    reviewed_at TIMESTAMPTZ,
    accepted_signal_id TEXT REFERENCES agro_field_signals(id),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (field_capture_pass_id, idempotency_key),
    CHECK (
        (status IN ('review', 'accepting') AND reviewed_by_person_id IS NULL
            AND reviewed_at IS NULL AND accepted_signal_id IS NULL)
        OR (status = 'accepted' AND reviewed_by_person_id IS NOT NULL
            AND reviewed_at IS NOT NULL AND accepted_signal_id IS NOT NULL)
        OR (status = 'rejected' AND reviewed_by_person_id IS NOT NULL
            AND reviewed_at IS NOT NULL AND accepted_signal_id IS NULL)
    )
);

CREATE OR REPLACE FUNCTION agro_guard_field_capture_pass()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'field capture passes are append-only';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.field_information_request_id IS DISTINCT FROM OLD.field_information_request_id
           OR NEW.signal_template_id IS DISTINCT FROM OLD.signal_template_id
           OR NEW.signal_template_version IS DISTINCT FROM OLD.signal_template_version
           OR NEW.token_hash IS DISTINCT FROM OLD.token_hash
           OR NEW.issued_by_person_id IS DISTINCT FROM OLD.issued_by_person_id
           OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'field capture pass scope is immutable';
        END IF;
        IF NOT ((OLD.status = 'active' AND NEW.status IN ('used', 'revoked'))
                OR (OLD.status = NEW.status AND OLD.revoked_at IS NOT DISTINCT FROM NEW.revoked_at)) THEN
            RAISE EXCEPTION 'invalid field capture pass transition';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION agro_guard_field_capture_candidate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'field capture candidates are append-only';
    END IF;
    IF TG_OP = 'INSERT' AND NOT EXISTS (
        SELECT 1
        FROM agro_field_capture_passes pass
        JOIN agro_field_information_requests request
          ON request.id = pass.field_information_request_id
        WHERE pass.id = NEW.field_capture_pass_id
          AND pass.field_information_request_id = NEW.field_information_request_id
          AND pass.signal_template_id = NEW.signal_template_id
          AND pass.signal_template_version = NEW.signal_template_version
          AND request.allocation_id = NEW.allocation_id
          AND request.target_person_id = NEW.actor_person_id
          AND (NOT request.evidence_required OR NEW.evidence_artifact_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'field capture candidate does not match its scoped pass';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.field_information_request_id IS DISTINCT FROM OLD.field_information_request_id
           OR NEW.field_capture_pass_id IS DISTINCT FROM OLD.field_capture_pass_id
           OR NEW.allocation_id IS DISTINCT FROM OLD.allocation_id
           OR NEW.actor_person_id IS DISTINCT FROM OLD.actor_person_id
           OR NEW.signal_template_id IS DISTINCT FROM OLD.signal_template_id
           OR NEW.signal_template_version IS DISTINCT FROM OLD.signal_template_version
           OR NEW.observed_at IS DISTINCT FROM OLD.observed_at
           OR NEW.values_json IS DISTINCT FROM OLD.values_json
           OR NEW.evidence_artifact_id IS DISTINCT FROM OLD.evidence_artifact_id
           OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'field capture candidate is immutable';
        END IF;
        IF NOT ((OLD.status = 'review' AND NEW.status IN ('accepting', 'rejected'))
                OR (OLD.status = 'accepting' AND NEW.status = 'accepted')
                OR (OLD.status = NEW.status
                    AND OLD.reviewed_by_person_id IS NOT DISTINCT FROM NEW.reviewed_by_person_id
                    AND OLD.reviewed_at IS NOT DISTINCT FROM NEW.reviewed_at
                    AND OLD.accepted_signal_id IS NOT DISTINCT FROM NEW.accepted_signal_id)) THEN
            RAISE EXCEPTION 'invalid field capture candidate transition';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agro_field_capture_passes_guard ON agro_field_capture_passes;
CREATE TRIGGER agro_field_capture_passes_guard
BEFORE UPDATE OR DELETE ON agro_field_capture_passes
FOR EACH ROW EXECUTE FUNCTION agro_guard_field_capture_pass();

DROP TRIGGER IF EXISTS agro_field_capture_candidates_guard ON agro_field_capture_candidates;
CREATE TRIGGER agro_field_capture_candidates_guard
BEFORE INSERT OR UPDATE OR DELETE ON agro_field_capture_candidates
FOR EACH ROW EXECUTE FUNCTION agro_guard_field_capture_candidate();

CREATE INDEX IF NOT EXISTS agro_idx_field_capture_passes_request_status_expiry
    ON agro_field_capture_passes (field_information_request_id, status, expires_at, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_field_capture_candidates_request_status_created
    ON agro_field_capture_candidates (field_information_request_id, status, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_field_capture_candidates_allocation_created
    ON agro_field_capture_candidates (allocation_id, created_at);

REVOKE ALL ON TABLE agro_field_capture_passes, agro_field_capture_candidates FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_guard_field_capture_pass() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_guard_field_capture_candidate() FROM PUBLIC;

COMMIT;
