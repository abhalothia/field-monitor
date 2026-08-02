-- Durable, one-time acceptance record for the first real AGRO CEO farm.
--
-- Apply manually after 0001 and 0002 with the reviewed private migration role.
-- This does not create any farm data and remains outside Supabase's Data API.

BEGIN;
SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_pilot_setup_acceptances (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL CHECK (char_length(content_hash) = 64 AND content_hash = lower(content_hash)),
    operating_unit_id TEXT NOT NULL REFERENCES agro_operating_units(id),
    manager_person_id TEXT NOT NULL REFERENCES agro_people(id),
    first_work_item_id TEXT NOT NULL REFERENCES agro_work_items(id),
    first_work_required_evidence_json JSONB NOT NULL,
    result_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status = 'accepted'),
    accepted_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (operating_unit_id)
);

-- The unique singleton is inserted in the same transaction as an acceptance.
-- A racing request loses the constraint race and rolls back all of its proposed
-- people, land, work, and location rows.
CREATE TABLE IF NOT EXISTS agro_pilot_setup_bootstrap_guard (
    id TEXT PRIMARY KEY CHECK (id = 'initial_setup'),
    acceptance_id TEXT NOT NULL UNIQUE REFERENCES agro_pilot_setup_acceptances(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS agro_idx_pilot_setup_acceptances_manager_created
    ON agro_pilot_setup_acceptances (manager_person_id, created_at);

REVOKE ALL ON TABLE agro_pilot_setup_acceptances, agro_pilot_setup_bootstrap_guard FROM PUBLIC;

COMMIT;
