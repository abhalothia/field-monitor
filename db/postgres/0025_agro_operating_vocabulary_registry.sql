-- Private semantic registry for source vocabulary.  It preserves every raw
-- source term, then stores deterministic or reviewable normalisations beside
-- it.  It is intentionally not a diagnosis, an identity resolver, or a
-- browser-facing API surface.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_operating_vocabulary_terms (
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    vocabulary_kind TEXT NOT NULL CHECK (vocabulary_kind IN (
        'task_type', 'reported_issue', 'crop_product'
    )),
    source_context TEXT NOT NULL CHECK (char_length(source_context) BETWEEN 1 AND 160),
    raw_value TEXT NOT NULL CHECK (char_length(raw_value) BETWEEN 1 AND 600),
    raw_fingerprint TEXT NOT NULL CHECK (
        char_length(raw_fingerprint) = 64
        AND raw_fingerprint = lower(raw_fingerprint)
    ),
    occurrence_count INTEGER NOT NULL DEFAULT 0 CHECK (occurrence_count >= 0),
    normalized_key TEXT CHECK (normalized_key IS NULL OR normalized_key ~ '^[a-z0-9][a-z0-9_-]{0,79}$'),
    display_label TEXT CHECK (display_label IS NULL OR char_length(display_label) BETWEEN 1 AND 160),
    mapping_state TEXT NOT NULL DEFAULT 'pending' CHECK (mapping_state IN (
        'pending', 'suggested', 'reviewed', 'rejected', 'unmapped', 'automatic'
    )),
    mapping_method TEXT NOT NULL DEFAULT 'deterministic' CHECK (mapping_method IN (
        'deterministic', 'ai', 'manual'
    )),
    confidence NUMERIC(4, 3) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    classifier_model TEXT CHECK (classifier_model IS NULL OR char_length(classifier_model) BETWEEN 1 AND 120),
    mapping_version TEXT NOT NULL CHECK (char_length(mapping_version) BETWEEN 1 AND 32),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    classified_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, vocabulary_kind, source_context, raw_fingerprint)
);

CREATE INDEX IF NOT EXISTS agro_idx_operating_vocabulary_pending
    ON agro_operating_vocabulary_terms (
        source_id, vocabulary_kind, mapping_state, occurrence_count DESC, last_seen_at DESC
    );

CREATE INDEX IF NOT EXISTS agro_idx_operating_vocabulary_normalized
    ON agro_operating_vocabulary_terms (
        source_id, vocabulary_kind, normalized_key
    ) WHERE normalized_key IS NOT NULL;

REVOKE ALL ON TABLE agro_operating_vocabulary_terms FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_operating_vocabulary_terms TO agro_vc_runtime;

COMMIT;
