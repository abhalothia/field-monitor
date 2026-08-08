-- Private, additive final-send reservation for the communications outbox.
-- The marker serializes scoped opt-out suppression with the final provider
-- attempt without putting provider I/O inside a database transaction.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

ALTER TABLE agro_communication_outbox
    ADD COLUMN IF NOT EXISTS final_send_reserved_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS agro_idx_communication_outbox_final_send_gate
    ON agro_communication_outbox (interaction_run_id, status)
    WHERE final_send_reserved_at IS NULL;

REVOKE ALL ON TABLE agro_communication_outbox FROM PUBLIC;

COMMIT;
