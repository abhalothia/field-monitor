-- FFL PostgreSQL/Supabase bootstrap.  Apply manually with a reviewed migration
-- role to the confirmed FFL project only; application startup never applies it.
--
-- This is deliberately a private schema.  Do not add `ffl` to Supabase's Data
-- API exposed schemas and do not grant browser clients access to these tables.
-- Create a least-privilege runtime database role separately, grant it USAGE on
-- this schema plus the exact table privileges it needs, and keep its DSN only
-- in the server/worker secret store.  No Supabase service-role key belongs in
-- a browser, Vercel preview, fixture, or git repository.

BEGIN;

CREATE SCHEMA IF NOT EXISTS ffl;
REVOKE ALL ON SCHEMA ffl FROM PUBLIC;
SET LOCAL search_path = ffl, pg_catalog;

CREATE TABLE IF NOT EXISTS operating_units (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS land_parcels (
    id TEXT PRIMARY KEY, operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
    name TEXT NOT NULL, area_hectares DOUBLE PRECISION NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS operational_blocks (
    id TEXT PRIMARY KEY, operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
    name TEXT NOT NULL, area_hectares DOUBLE PRECISION NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS block_parcels (
    operational_block_id TEXT NOT NULL REFERENCES operational_blocks(id),
    land_parcel_id TEXT NOT NULL REFERENCES land_parcels(id), created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (operational_block_id, land_parcel_id)
);
CREATE TABLE IF NOT EXISTS rights_to_operate (
    id TEXT PRIMARY KEY, land_parcel_id TEXT NOT NULL REFERENCES land_parcels(id),
    right_type TEXT NOT NULL, starts_on DATE NOT NULL, ends_on DATE NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY, operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
    name TEXT NOT NULL, starts_on DATE NOT NULL, ends_on DATE NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS crop_allocations (
    id TEXT PRIMARY KEY, operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
    operational_block_id TEXT NOT NULL REFERENCES operational_blocks(id), season_id TEXT NOT NULL REFERENCES seasons(id),
    crop_name TEXT NOT NULL, cultivar TEXT, area_hectares DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS signal_templates (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    fields_json JSONB NOT NULL, owner_id TEXT NOT NULL REFERENCES people(id), published_at TIMESTAMPTZ NOT NULL,
    UNIQUE (name, version)
);
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL REFERENCES crop_allocations(id), title TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES people(id), due_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS exception_records (
    id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL REFERENCES crop_allocations(id), title TEXT NOT NULL,
    severity TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES people(id),
    fallback_owner_id TEXT NOT NULL REFERENCES people(id), observed_at TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL REFERENCES crop_allocations(id), title TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES people(id), review_due_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
    from_status TEXT NOT NULL, to_status TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES people(id),
    reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_artifacts (
    id TEXT PRIMARY KEY, content_hash TEXT NOT NULL UNIQUE, media_type TEXT NOT NULL,
    storage_reference TEXT NOT NULL, original_filename TEXT, size_bytes BIGINT,
    source_uri TEXT, created_by_person_id TEXT REFERENCES people(id), created_at TIMESTAMPTZ NOT NULL,
    CHECK (size_bytes IS NULL OR size_bytes >= 0),
    CHECK (char_length(content_hash) = 64 AND content_hash = lower(content_hash))
);
CREATE TABLE IF NOT EXISTS field_signals (
    id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
    template_id TEXT NOT NULL REFERENCES signal_templates(id), template_version INTEGER NOT NULL CHECK (template_version > 0),
    observed_at TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL, actor_id TEXT NOT NULL REFERENCES people(id),
    evidence_artifact_id TEXT REFERENCES evidence_artifacts(id), values_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'rejected')),
    supersedes_signal_id TEXT REFERENCES field_signals(id), created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS crop_stage_checkpoints (
    id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL REFERENCES crop_allocations(id), stage_name TEXT NOT NULL,
    planned_for TIMESTAMPTZ NOT NULL, status TEXT NOT NULL CHECK (status IN ('planned', 'completed', 'skipped', 'superseded')),
    expected_evidence_json JSONB NOT NULL, template_id TEXT REFERENCES signal_templates(id),
    template_version INTEGER CHECK (template_version IS NULL OR template_version > 0), completed_at TIMESTAMPTZ,
    supersedes_checkpoint_id TEXT REFERENCES crop_stage_checkpoints(id), created_at TIMESTAMPTZ NOT NULL,
    CHECK ((template_id IS NULL AND template_version IS NULL) OR (template_id IS NOT NULL AND template_version IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS harvest_records (
    id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL REFERENCES crop_allocations(id), harvest_starts_on DATE NOT NULL,
    harvest_ends_on DATE, quantity DOUBLE PRECISION NOT NULL CHECK (quantity >= 0), canonical_unit TEXT NOT NULL,
    measurement_method TEXT NOT NULL, quality_metrics_json JSONB NOT NULL,
    evidence_artifact_id TEXT REFERENCES evidence_artifacts(id),
    status TEXT NOT NULL CHECK (status IN ('preliminary', 'final', 'corrected')),
    correction_of_id TEXT REFERENCES harvest_records(id), corrected_by_person_id TEXT REFERENCES people(id),
    correction_reason TEXT, created_at TIMESTAMPTZ NOT NULL,
    CHECK ((correction_of_id IS NULL AND corrected_by_person_id IS NULL AND correction_reason IS NULL)
        OR (correction_of_id IS NOT NULL AND corrected_by_person_id IS NOT NULL AND correction_reason IS NOT NULL)),
    CHECK ((correction_of_id IS NULL AND status <> 'corrected') OR (correction_of_id IS NOT NULL AND status = 'corrected'))
);
CREATE TABLE IF NOT EXISTS season_reviews (
    id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL REFERENCES crop_allocations(id), owner_id TEXT NOT NULL REFERENCES people(id),
    confirmed_practices_json JSONB NOT NULL, invalidated_assumptions_json JSONB NOT NULL,
    unresolved_questions_json JSONB NOT NULL, proposed_playbook_changes_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'reviewed', 'published')), reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS source_registry (
    id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, source_type TEXT NOT NULL,
    purpose TEXT NOT NULL, authority_level TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES people(id),
    credentials_reference TEXT, endpoint TEXT, permitted_data_classes_json JSONB NOT NULL,
    freshness_target_hours DOUBLE PRECISION CHECK (freshness_target_hours IS NULL OR freshness_target_hours >= 0),
    license_notes TEXT, schema_version TEXT NOT NULL, mapping_version TEXT NOT NULL,
    default_coverage_json JSONB NOT NULL, enabled BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS source_runs (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES source_registry(id), cursor TEXT,
    coverage_json JSONB NOT NULL, fetched_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed', 'unavailable', 'quarantined')),
    rows_received INTEGER NOT NULL DEFAULT 0 CHECK (rows_received >= 0),
    rows_accepted INTEGER NOT NULL DEFAULT 0 CHECK (rows_accepted >= 0 AND rows_accepted <= rows_received),
    error_summary TEXT, next_retry_at TIMESTAMPTZ, mapping_version TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS regional_signals (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES source_registry(id), source_run_id TEXT REFERENCES source_runs(id),
    source_identifier TEXT NOT NULL, source_url TEXT, region TEXT NOT NULL, signal_type TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL, valid_from TIMESTAMPTZ, valid_to TIMESTAMPTZ,
    coverage_json JSONB NOT NULL, resolution TEXT,
    freshness_target_hours DOUBLE PRECISION CHECK (freshness_target_hours IS NULL OR freshness_target_hours >= 0),
    signal_kind TEXT NOT NULL CHECK (signal_kind IN ('observation', 'forecast', 'human_assessment', 'model_inference', 'aggregate_statistic')),
    value_json JSONB NOT NULL, status TEXT NOT NULL CHECK (status IN ('available', 'stale', 'unavailable', 'quarantined')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY, purpose TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('received', 'profiled', 'review', 'published', 'quarantined', 'failed')),
    content_hash TEXT NOT NULL UNIQUE, evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id),
    mapping_version TEXT NOT NULL, source_id TEXT REFERENCES source_registry(id), owner_id TEXT NOT NULL REFERENCES people(id),
    received_at TIMESTAMPTZ NOT NULL, reviewed_at TIMESTAMPTZ, reviewed_by_id TEXT REFERENCES people(id),
    published_at TIMESTAMPTZ, profile_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL,
    CHECK (char_length(content_hash) = 64 AND content_hash = lower(content_hash))
);
CREATE TABLE IF NOT EXISTS import_rows (
    id TEXT PRIMARY KEY, import_batch_id TEXT NOT NULL REFERENCES import_batches(id),
    row_number INTEGER NOT NULL CHECK (row_number > 0), raw_json JSONB NOT NULL, mapped_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'valid', 'invalid', 'ambiguous', 'quarantined', 'published')),
    validation_errors_json JSONB NOT NULL, target_entity_type TEXT, target_entity_id TEXT,
    published_record_id TEXT, created_at TIMESTAMPTZ NOT NULL, UNIQUE (import_batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS playbooks (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'published', 'retired')),
    owner_id TEXT NOT NULL REFERENCES people(id), protocol_json JSONB NOT NULL, effective_from DATE,
    approved_by_person_id TEXT REFERENCES people(id), approved_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (name, version)
);
CREATE TABLE IF NOT EXISTS trials (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, hypothesis TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES people(id),
    protocol_version TEXT NOT NULL, decision_question TEXT NOT NULL, treatment_json JSONB NOT NULL,
    comparator_json JSONB NOT NULL, eligibility_rule_json JSONB NOT NULL, measurements_json JSONB NOT NULL,
    guardrails_json JSONB NOT NULL, status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'paused', 'stopped', 'completed')),
    starts_on DATE, ends_on DATE, status_reason TEXT, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS trial_allocations (
    id TEXT PRIMARY KEY, trial_id TEXT NOT NULL REFERENCES trials(id), allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
    arm TEXT NOT NULL CHECK (arm IN ('treatment', 'comparator')),
    status TEXT NOT NULL CHECK (status IN ('eligible', 'enrolled', 'withdrawn', 'excluded')),
    enrolled_at TIMESTAMPTZ, withdrawn_at TIMESTAMPTZ, reason TEXT, created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (trial_id, allocation_id)
);
CREATE TABLE IF NOT EXISTS trial_confounders (
    id TEXT PRIMARY KEY, trial_id TEXT NOT NULL REFERENCES trials(id), allocation_id TEXT REFERENCES crop_allocations(id),
    category TEXT NOT NULL, description TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
    evidence_artifact_id TEXT REFERENCES evidence_artifacts(id), actor_id TEXT NOT NULL REFERENCES people(id),
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS trial_conclusions (
    id TEXT PRIMARY KEY, trial_id TEXT NOT NULL REFERENCES trials(id), reviewer_id TEXT NOT NULL REFERENCES people(id),
    status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'approved', 'rejected')), result_json JSONB NOT NULL,
    confidence_level TEXT NOT NULL CHECK (confidence_level IN ('low', 'medium', 'high')),
    limitations_json JSONB NOT NULL, evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id),
    playbook_id TEXT REFERENCES playbooks(id),
    playbook_decision TEXT NOT NULL CHECK (playbook_decision IN ('none', 'create', 'revise', 'promote', 'retire')),
    approved_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL,
    CHECK (playbook_decision <> 'promote' OR (status = 'approved' AND approved_at IS NOT NULL AND playbook_id IS NOT NULL))
);

-- The communications tables intentionally retain only redacted metadata and
-- sealed receipts.  Provider raw payloads, phone numbers, media URLs, and
-- credentials do not belong in routine queries or logs.
CREATE TABLE IF NOT EXISTS communication_endpoints (
    id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id), provider TEXT NOT NULL,
    address TEXT NOT NULL, locale TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL, UNIQUE (provider, address)
);
CREATE TABLE IF NOT EXISTS communication_consents (
    id TEXT PRIMARY KEY, endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id), purpose TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')), granted_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ, evidence TEXT NOT NULL, UNIQUE (endpoint_id, purpose)
);
CREATE TABLE IF NOT EXISTS communication_consent_events (
    id TEXT PRIMARY KEY, endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id), purpose TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')), actor_id TEXT,
    provenance TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_templates (
    id TEXT PRIMARY KEY, template_key TEXT NOT NULL, version INTEGER NOT NULL CHECK (version > 0),
    locale TEXT NOT NULL, purpose TEXT NOT NULL, body TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'retired')),
    owner_id TEXT NOT NULL REFERENCES people(id), provider_template_id TEXT,
    provider_approval_state TEXT NOT NULL DEFAULT 'not_required', created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (template_key, version, locale)
);
CREATE TABLE IF NOT EXISTS communication_prompts (
    id TEXT PRIMARY KEY, work_item_id TEXT NOT NULL REFERENCES work_items(id),
    allocation_id TEXT NOT NULL REFERENCES crop_allocations(id), endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
    template_id TEXT NOT NULL REFERENCES communication_templates(id), initiated_by_person_id TEXT NOT NULL REFERENCES people(id),
    idempotency_key TEXT NOT NULL UNIQUE, logical_action_key TEXT, provider_message_id TEXT UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'scheduled', 'delivered', 'failed', 'unknown', 'responded', 'no_response')),
    created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_events (
    id TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_event_id TEXT NOT NULL, provider_message_id TEXT,
    event_type TEXT NOT NULL, contact_fingerprint TEXT NOT NULL, endpoint_id TEXT REFERENCES communication_endpoints(id),
    envelope_json JSONB NOT NULL, status TEXT NOT NULL CHECK (status IN ('received', 'processed', 'review_required', 'quarantined')),
    received_at TIMESTAMPTZ NOT NULL, UNIQUE (provider, provider_event_id)
);
CREATE TABLE IF NOT EXISTS communication_attachments (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES communication_events(id), source_reference TEXT NOT NULL,
    media_type TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('unavailable', 'retained', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at TIMESTAMPTZ, last_error TEXT, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_evidence_links (
    attachment_id TEXT PRIMARY KEY REFERENCES communication_attachments(id),
    evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id), retained_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_candidates (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE REFERENCES communication_events(id),
    prompt_id TEXT REFERENCES communication_prompts(id), allocation_id TEXT REFERENCES crop_allocations(id),
    work_item_id TEXT REFERENCES work_items(id), endpoint_id TEXT REFERENCES communication_endpoints(id),
    kind TEXT NOT NULL CHECK (kind IN ('signal', 'exception')), status TEXT NOT NULL CHECK (status IN ('review', 'accepted', 'rejected')),
    draft_json JSONB NOT NULL, accepted_record_type TEXT, accepted_record_id TEXT,
    reviewed_by_person_id TEXT REFERENCES people(id), reviewed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_deliveries (
    id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL REFERENCES communication_prompts(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('attempting', 'accepted', 'unknown', 'failed')),
    provider_message_id TEXT, error_summary TEXT, created_at TIMESTAMPTZ NOT NULL, UNIQUE (prompt_id, attempt)
);
CREATE TABLE IF NOT EXISTS communication_schema_migrations (
    version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_quarantines (
    id TEXT PRIMARY KEY, provider TEXT NOT NULL, reason TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_receipts (
    event_id TEXT PRIMARY KEY REFERENCES communication_events(id), ciphertext TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'processed', 'retryable', 'quarantined')),
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, claim_token TEXT, lease_expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_reconciliations (
    id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL REFERENCES communication_prompts(id), provider_message_id TEXT,
    provider_status TEXT, provider_error_code INTEGER,
    outcome TEXT NOT NULL CHECK (outcome IN ('awaiting_webhook', 'reconciled', 'lookup_unavailable')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_field_signals_allocation_observed ON field_signals (allocation_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_crop_stage_checkpoints_allocation_planned ON crop_stage_checkpoints (allocation_id, planned_for);
CREATE INDEX IF NOT EXISTS idx_harvest_records_allocation_created ON harvest_records (allocation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_season_reviews_allocation_created ON season_reviews (allocation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_source_runs_source_created ON source_runs (source_id, created_at);
CREATE INDEX IF NOT EXISTS idx_regional_signals_region_observed ON regional_signals (region, observed_at);
CREATE INDEX IF NOT EXISTS idx_import_rows_batch_number ON import_rows (import_batch_id, row_number);
CREATE INDEX IF NOT EXISTS idx_import_batches_purpose_received ON import_batches (purpose, received_at);
CREATE INDEX IF NOT EXISTS idx_trial_allocations_trial ON trial_allocations (trial_id);
CREATE INDEX IF NOT EXISTS idx_trials_owner_created ON trials (owner_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trial_confounders_trial ON trial_confounders (trial_id);
CREATE INDEX IF NOT EXISTS idx_trial_conclusions_trial ON trial_conclusions (trial_id);
CREATE INDEX IF NOT EXISTS idx_communication_prompts_endpoint_status ON communication_prompts (endpoint_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_communication_prompts_logical_action
    ON communication_prompts (logical_action_key) WHERE logical_action_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_communication_events_contact ON communication_events (provider, contact_fingerprint);
CREATE INDEX IF NOT EXISTS idx_communication_reconciliations_prompt ON communication_reconciliations (prompt_id, created_at);

REVOKE ALL ON ALL TABLES IN SCHEMA ffl FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA ffl FROM PUBLIC;

COMMIT;
