-- Private, additive lifecycle reservation for approved communications sends.
-- This migration is deliberately separate from 0021 so already-provisioned
-- production databases receive the outbox relation safely.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_communication_outbox (
    id TEXT PRIMARY KEY,
    interaction_run_id TEXT NOT NULL UNIQUE REFERENCES agro_communication_interaction_runs(id),
    legacy_prompt_id TEXT REFERENCES agro_communication_prompts(id),
    provider_message_id TEXT UNIQUE,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'dispatching', 'dispatched', 'suppressed', 'failed', 'unknown'
    )),
    policy_code TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS agro_idx_communication_outbox_status
    ON agro_communication_outbox (status, updated_at);

REVOKE ALL ON TABLE agro_communication_outbox FROM PUBLIC;

COMMIT;
