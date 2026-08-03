-- Provider-neutral, durable requests for bounded field facts or proof.
--
-- Apply manually after 0001 through 0004 with the reviewed private migration
-- role.  This migration does not enable a messaging provider, create contacts,
-- or expose any table through Supabase's Data API.
--
-- A request is immutable delivery intent, not an agronomic instruction or a
-- completed field update.  A future adapter may dispatch only a ``ready``
-- request after its own endpoint, consent, template, and capability gates.

BEGIN;
SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_field_information_requests (
    id TEXT PRIMARY KEY,
    allocation_id TEXT NOT NULL REFERENCES agro_crop_allocations(id),
    target_person_id TEXT NOT NULL REFERENCES agro_people(id),
    work_item_id TEXT REFERENCES agro_work_items(id),
    request_kind TEXT NOT NULL CHECK (request_kind IN (
        'field_check', 'evidence_photo', 'irrigation_status',
        'input_application', 'pest_or_deviation', 'harvest_update'
    )),
    evidence_required BOOLEAN NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    request_copy_en TEXT NOT NULL CHECK (char_length(btrim(request_copy_en)) BETWEEN 1 AND 1600),
    request_copy_hi TEXT NOT NULL CHECK (char_length(btrim(request_copy_hi)) BETWEEN 1 AND 1600),
    initiated_by_person_id TEXT REFERENCES agro_people(id),
    initiated_by_system_key TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN (
        'draft', 'ready', 'dispatched', 'responded', 'expired', 'cancelled'
    )),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (initiated_by_person_id IS NOT NULL AND initiated_by_system_key IS NULL)
        OR (initiated_by_person_id IS NULL AND initiated_by_system_key IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS agro_field_information_request_events (
    id TEXT PRIMARY KEY,
    field_information_request_id TEXT NOT NULL REFERENCES agro_field_information_requests(id),
    from_status TEXT NOT NULL CHECK (from_status IN (
        'created', 'draft', 'ready', 'dispatched'
    )),
    to_status TEXT NOT NULL CHECK (to_status IN (
        'draft', 'ready', 'dispatched', 'responded', 'expired', 'cancelled'
    )),
    actor_person_id TEXT REFERENCES agro_people(id),
    actor_system_key TEXT,
    reason TEXT NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 500),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (actor_person_id IS NOT NULL AND actor_system_key IS NULL)
        OR (actor_person_id IS NULL AND actor_system_key IS NOT NULL)
    )
);

-- Cross-table equality cannot be represented by a foreign key here.  Keep the
-- optional work link on the same allocation at the database boundary as well
-- as in the repository validation.
CREATE OR REPLACE FUNCTION agro_validate_field_information_request_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'field information requests are append-only';
    END IF;

    IF NEW.work_item_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM agro_work_items
        WHERE id = NEW.work_item_id AND allocation_id = NEW.allocation_id
    ) THEN
        RAISE EXCEPTION 'linked work item must belong to the same crop allocation';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.allocation_id IS DISTINCT FROM OLD.allocation_id
           OR NEW.target_person_id IS DISTINCT FROM OLD.target_person_id
           OR NEW.work_item_id IS DISTINCT FROM OLD.work_item_id
           OR NEW.request_kind IS DISTINCT FROM OLD.request_kind
           OR NEW.evidence_required IS DISTINCT FROM OLD.evidence_required
           OR NEW.due_at IS DISTINCT FROM OLD.due_at
           OR NEW.request_copy_en IS DISTINCT FROM OLD.request_copy_en
           OR NEW.request_copy_hi IS DISTINCT FROM OLD.request_copy_hi
           OR NEW.initiated_by_person_id IS DISTINCT FROM OLD.initiated_by_person_id
           OR NEW.initiated_by_system_key IS DISTINCT FROM OLD.initiated_by_system_key
           OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'field information request copy is immutable';
        END IF;

        IF NOT (
            (OLD.status = 'draft' AND NEW.status IN ('ready', 'expired', 'cancelled'))
            OR (OLD.status = 'ready' AND NEW.status IN ('dispatched', 'expired', 'cancelled'))
            OR (OLD.status = 'dispatched' AND NEW.status IN ('responded', 'expired', 'cancelled'))
        ) THEN
            RAISE EXCEPTION 'invalid field information request transition';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION agro_prevent_field_information_request_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'field information request events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS agro_field_information_requests_guard ON agro_field_information_requests;
CREATE TRIGGER agro_field_information_requests_guard
BEFORE INSERT OR UPDATE OR DELETE ON agro_field_information_requests
FOR EACH ROW EXECUTE FUNCTION agro_validate_field_information_request_update();

DROP TRIGGER IF EXISTS agro_field_information_request_events_no_mutation
    ON agro_field_information_request_events;
CREATE TRIGGER agro_field_information_request_events_no_mutation
BEFORE UPDATE OR DELETE ON agro_field_information_request_events
FOR EACH ROW EXECUTE FUNCTION agro_prevent_field_information_request_event_mutation();

CREATE INDEX IF NOT EXISTS agro_idx_field_information_requests_allocation_status_due
    ON agro_field_information_requests (allocation_id, status, due_at, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_field_information_requests_target_status_due
    ON agro_field_information_requests (target_person_id, status, due_at, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_field_information_requests_work_item
    ON agro_field_information_requests (work_item_id);
CREATE INDEX IF NOT EXISTS agro_idx_field_information_requests_initiated_by_person
    ON agro_field_information_requests (initiated_by_person_id);
CREATE INDEX IF NOT EXISTS agro_idx_field_information_request_events_request_created
    ON agro_field_information_request_events (field_information_request_id, created_at);
CREATE INDEX IF NOT EXISTS agro_idx_field_information_request_events_actor_person
    ON agro_field_information_request_events (actor_person_id);

REVOKE ALL ON TABLE agro_field_information_requests, agro_field_information_request_events FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_validate_field_information_request_update() FROM PUBLIC;
REVOKE ALL ON FUNCTION agro_prevent_field_information_request_event_mutation() FROM PUBLIC;

COMMIT;
