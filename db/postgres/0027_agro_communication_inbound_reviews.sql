-- Private, additive outcomes for exact WhatsApp inbound routing.
-- Applied after the interaction and outbox migrations so existing production
-- databases gain redacted review/idempotency state without replaying 0021.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_communication_inbound_reviews (
    event_id TEXT PRIMARY KEY REFERENCES agro_communication_events(id),
    state TEXT NOT NULL CHECK (state IN ('identity_review', 'context_review')),
    reason TEXT NOT NULL CHECK (reason IN (
        'endpoint_unresolved', 'interaction_unresolved', 'intent_unrecognized',
        'intent_not_expected', 'intent_requires_human_handling'
    )),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_communication_inbound_outcomes (
    event_id TEXT PRIMARY KEY REFERENCES agro_communication_events(id),
    kind TEXT NOT NULL CHECK (kind IN (
        'review_candidate', 'identity_review', 'context_review', 'opt_out'
    )),
    interaction_run_id TEXT REFERENCES agro_communication_interaction_runs(id),
    candidate_id TEXT REFERENCES agro_communication_candidates(id),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (kind = 'review_candidate' AND candidate_id IS NOT NULL)
        OR (kind = 'opt_out' AND interaction_run_id IS NOT NULL)
        OR kind IN ('identity_review', 'context_review')
    )
);

CREATE INDEX IF NOT EXISTS agro_idx_communication_inbound_outcomes_interaction
    ON agro_communication_inbound_outcomes (interaction_run_id);
CREATE INDEX IF NOT EXISTS agro_idx_communication_inbound_outcomes_candidate
    ON agro_communication_inbound_outcomes (candidate_id);

REVOKE ALL ON TABLE agro_communication_inbound_reviews FROM PUBLIC;
REVOKE ALL ON TABLE agro_communication_inbound_outcomes FROM PUBLIC;

COMMIT;
