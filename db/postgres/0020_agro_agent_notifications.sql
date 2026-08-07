-- Private manager-defined operating notifications.  These are configuration,
-- never a public data feed or an automated decision-maker.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_agent_notifications (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
    natural_language_rule TEXT NOT NULL CHECK (char_length(btrim(natural_language_rule)) BETWEEN 8 AND 500),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS agro_idx_agent_notifications_enabled_updated
    ON agro_agent_notifications (enabled, updated_at DESC);

REVOKE ALL ON TABLE agro_agent_notifications FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_agent_notifications TO agro_vc_runtime;

COMMIT;
