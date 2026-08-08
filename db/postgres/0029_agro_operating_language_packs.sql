-- Private, review-first language and issue-group enrichments for the operating
-- vocabulary.  These records improve display and search only: they never
-- change source facts, merge places, identify people, or create a diagnosis.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

CREATE TABLE IF NOT EXISTS agro_operating_vocabulary_localizations (
    source_id TEXT NOT NULL,
    vocabulary_kind TEXT NOT NULL,
    source_context TEXT NOT NULL,
    raw_fingerprint TEXT NOT NULL,
    locale_code TEXT NOT NULL CHECK (locale_code IN ('hi')),
    display_label TEXT,
    search_aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(search_aliases_json) = 'array'),
    mapping_state TEXT NOT NULL CHECK (mapping_state IN (
        'suggested', 'reviewed', 'rejected', 'unmapped'
    )),
    mapping_method TEXT NOT NULL CHECK (mapping_method IN ('ai', 'manual')),
    confidence NUMERIC(4, 3) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    classifier_model TEXT CHECK (classifier_model IS NULL OR char_length(classifier_model) BETWEEN 1 AND 120),
    mapping_version TEXT NOT NULL CHECK (char_length(mapping_version) BETWEEN 1 AND 32),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    classified_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, vocabulary_kind, source_context, raw_fingerprint, locale_code),
    FOREIGN KEY (source_id, vocabulary_kind, source_context, raw_fingerprint)
        REFERENCES agro_operating_vocabulary_terms (
            source_id, vocabulary_kind, source_context, raw_fingerprint
        ),
    CHECK (
        (mapping_state IN ('suggested', 'reviewed') AND display_label IS NOT NULL)
        OR (mapping_state IN ('rejected', 'unmapped') AND display_label IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS agro_idx_operating_vocabulary_localizations_state
    ON agro_operating_vocabulary_localizations (source_id, locale_code, mapping_state);

-- A group is merely a review queue for vocabulary values that already share a
-- proposed normalized key.  It deliberately stores no raw phrase or person.
CREATE TABLE IF NOT EXISTS agro_operating_issue_group_proposals (
    source_id TEXT NOT NULL REFERENCES agro_source_registry(id),
    source_context TEXT NOT NULL CHECK (source_context IN ('reported_disease', 'reported_pest')),
    normalized_key TEXT NOT NULL CHECK (normalized_key ~ '^[a-z0-9][a-z0-9_-]{0,79}$'),
    display_label TEXT NOT NULL CHECK (char_length(display_label) BETWEEN 1 AND 160),
    member_count INTEGER NOT NULL CHECK (member_count >= 2),
    occurrence_count INTEGER NOT NULL CHECK (occurrence_count >= 0),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    mapping_state TEXT NOT NULL CHECK (mapping_state IN ('suggested', 'reviewed', 'rejected')),
    mapping_method TEXT NOT NULL CHECK (mapping_method IN ('deterministic', 'manual')),
    mapping_version TEXT NOT NULL CHECK (char_length(mapping_version) BETWEEN 1 AND 32),
    reviewed_at TIMESTAMPTZ,
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, source_context, normalized_key)
);

CREATE INDEX IF NOT EXISTS agro_idx_operating_issue_group_proposals_state
    ON agro_operating_issue_group_proposals (source_id, mapping_state, last_seen_at DESC);

-- One display/local-search pack per already-deterministic composite place.
-- A localization cannot alter the source village/block/district or join places.
CREATE TABLE IF NOT EXISTS agro_place_localizations (
    source_id TEXT NOT NULL,
    place_key TEXT NOT NULL,
    locale_code TEXT NOT NULL CHECK (locale_code IN ('hi')),
    village_label TEXT,
    block_label TEXT,
    district_label TEXT,
    search_aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(search_aliases_json) = 'array'),
    mapping_state TEXT NOT NULL CHECK (mapping_state IN (
        'suggested', 'reviewed', 'rejected', 'unmapped'
    )),
    mapping_method TEXT NOT NULL CHECK (mapping_method IN ('ai', 'manual')),
    confidence NUMERIC(4, 3) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    classifier_model TEXT CHECK (classifier_model IS NULL OR char_length(classifier_model) BETWEEN 1 AND 120),
    mapping_version TEXT NOT NULL CHECK (char_length(mapping_version) BETWEEN 1 AND 32),
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    classified_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, place_key, locale_code),
    FOREIGN KEY (source_id, place_key) REFERENCES agro_place_catalog(source_id, place_key),
    CHECK (
        (mapping_state IN ('suggested', 'reviewed')
         AND (village_label IS NOT NULL OR block_label IS NOT NULL OR district_label IS NOT NULL))
        OR (mapping_state IN ('rejected', 'unmapped')
            AND village_label IS NULL AND block_label IS NULL AND district_label IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS agro_idx_place_localizations_state
    ON agro_place_localizations (source_id, locale_code, mapping_state);

REVOKE ALL ON TABLE agro_operating_vocabulary_localizations FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE agro_operating_issue_group_proposals FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE agro_place_localizations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_operating_vocabulary_localizations TO agro_vc_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_operating_issue_group_proposals TO agro_vc_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE agro_place_localizations TO agro_vc_runtime;

COMMIT;
