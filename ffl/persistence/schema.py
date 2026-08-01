import sqlite3


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS operating_units (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS land_parcels (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            name TEXT NOT NULL,
            area_hectares REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operational_blocks (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            name TEXT NOT NULL,
            area_hectares REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS block_parcels (
            operational_block_id TEXT NOT NULL REFERENCES operational_blocks(id),
            land_parcel_id TEXT NOT NULL REFERENCES land_parcels(id),
            created_at TEXT NOT NULL,
            PRIMARY KEY (operational_block_id, land_parcel_id)
        );

        CREATE TABLE IF NOT EXISTS rights_to_operate (
            id TEXT PRIMARY KEY,
            land_parcel_id TEXT NOT NULL REFERENCES land_parcels(id),
            right_type TEXT NOT NULL,
            starts_on TEXT NOT NULL,
            ends_on TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS seasons (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            name TEXT NOT NULL,
            starts_on TEXT NOT NULL,
            ends_on TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crop_allocations (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            operational_block_id TEXT NOT NULL REFERENCES operational_blocks(id),
            season_id TEXT NOT NULL REFERENCES seasons(id),
            crop_name TEXT NOT NULL,
            cultivar TEXT,
            area_hectares REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signal_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            published_at TEXT NOT NULL,
            UNIQUE (name, version)
        );

        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            due_at TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exception_records (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            title TEXT NOT NULL,
            severity TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            fallback_owner_id TEXT NOT NULL REFERENCES people(id),
            observed_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            review_due_at TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            actor_id TEXT NOT NULL REFERENCES people(id),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evidence_artifacts (
            id TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL,
            storage_reference TEXT NOT NULL,
            original_filename TEXT,
            size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
            source_uri TEXT,
            created_by_person_id TEXT REFERENCES people(id),
            created_at TEXT NOT NULL,
            CHECK (length(content_hash) = 64 AND content_hash = lower(content_hash))
        );

        CREATE TABLE IF NOT EXISTS field_signals (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            template_id TEXT NOT NULL REFERENCES signal_templates(id),
            template_version INTEGER NOT NULL CHECK (template_version > 0),
            observed_at TEXT NOT NULL,
            received_at TEXT NOT NULL,
            actor_id TEXT NOT NULL REFERENCES people(id),
            evidence_artifact_id TEXT REFERENCES evidence_artifacts(id),
            values_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'rejected')),
            supersedes_signal_id TEXT REFERENCES field_signals(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crop_stage_checkpoints (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            stage_name TEXT NOT NULL,
            planned_for TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('planned', 'completed', 'skipped', 'superseded')),
            expected_evidence_json TEXT NOT NULL,
            template_id TEXT REFERENCES signal_templates(id),
            template_version INTEGER CHECK (template_version IS NULL OR template_version > 0),
            completed_at TEXT,
            supersedes_checkpoint_id TEXT REFERENCES crop_stage_checkpoints(id),
            created_at TEXT NOT NULL,
            CHECK ((template_id IS NULL AND template_version IS NULL) OR (template_id IS NOT NULL AND template_version IS NOT NULL))
        );

        CREATE TABLE IF NOT EXISTS harvest_records (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            harvest_starts_on TEXT NOT NULL,
            harvest_ends_on TEXT,
            quantity REAL NOT NULL CHECK (quantity >= 0),
            canonical_unit TEXT NOT NULL,
            measurement_method TEXT NOT NULL,
            quality_metrics_json TEXT NOT NULL,
            evidence_artifact_id TEXT REFERENCES evidence_artifacts(id),
            status TEXT NOT NULL CHECK (status IN ('preliminary', 'final', 'corrected')),
            correction_of_id TEXT REFERENCES harvest_records(id),
            corrected_by_person_id TEXT REFERENCES people(id),
            correction_reason TEXT,
            created_at TEXT NOT NULL,
            CHECK (
                (correction_of_id IS NULL AND corrected_by_person_id IS NULL AND correction_reason IS NULL)
                OR
                (correction_of_id IS NOT NULL AND corrected_by_person_id IS NOT NULL AND correction_reason IS NOT NULL)
            ),
            CHECK ((correction_of_id IS NULL AND status != 'corrected') OR (correction_of_id IS NOT NULL AND status = 'corrected'))
        );

        CREATE TABLE IF NOT EXISTS season_reviews (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            owner_id TEXT NOT NULL REFERENCES people(id),
            confirmed_practices_json TEXT NOT NULL,
            invalidated_assumptions_json TEXT NOT NULL,
            unresolved_questions_json TEXT NOT NULL,
            proposed_playbook_changes_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'reviewed', 'published')),
            reviewed_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_registry (
            id TEXT PRIMARY KEY,
            source_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            purpose TEXT NOT NULL,
            authority_level TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            credentials_reference TEXT,
            endpoint TEXT,
            permitted_data_classes_json TEXT NOT NULL,
            freshness_target_hours REAL CHECK (freshness_target_hours IS NULL OR freshness_target_hours >= 0),
            license_notes TEXT,
            schema_version TEXT NOT NULL,
            mapping_version TEXT NOT NULL,
            default_coverage_json TEXT NOT NULL,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_runs (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            cursor TEXT,
            coverage_json TEXT NOT NULL,
            fetched_at TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed', 'unavailable', 'quarantined')),
            rows_received INTEGER NOT NULL DEFAULT 0 CHECK (rows_received >= 0),
            rows_accepted INTEGER NOT NULL DEFAULT 0 CHECK (rows_accepted >= 0 AND rows_accepted <= rows_received),
            error_summary TEXT,
            next_retry_at TEXT,
            mapping_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS regional_signals (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            source_identifier TEXT NOT NULL,
            source_url TEXT,
            region TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            received_at TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            coverage_json TEXT NOT NULL,
            resolution TEXT,
            freshness_target_hours REAL CHECK (freshness_target_hours IS NULL OR freshness_target_hours >= 0),
            signal_kind TEXT NOT NULL CHECK (signal_kind IN ('observation', 'forecast', 'human_assessment', 'model_inference', 'aggregate_statistic')),
            value_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('available', 'stale', 'unavailable', 'quarantined')),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_batches (
            id TEXT PRIMARY KEY,
            purpose TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('received', 'profiled', 'review', 'published', 'quarantined', 'failed')),
            content_hash TEXT NOT NULL UNIQUE,
            evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id),
            mapping_version TEXT NOT NULL,
            source_id TEXT REFERENCES source_registry(id),
            owner_id TEXT NOT NULL REFERENCES people(id),
            received_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by_id TEXT REFERENCES people(id),
            published_at TEXT,
            profile_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (length(content_hash) = 64 AND content_hash = lower(content_hash))
        );

        CREATE TABLE IF NOT EXISTS import_rows (
            id TEXT PRIMARY KEY,
            import_batch_id TEXT NOT NULL REFERENCES import_batches(id),
            row_number INTEGER NOT NULL CHECK (row_number > 0),
            raw_json TEXT NOT NULL,
            mapped_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'valid', 'invalid', 'ambiguous', 'quarantined', 'published')),
            validation_errors_json TEXT NOT NULL,
            target_entity_type TEXT,
            target_entity_id TEXT,
            published_record_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (import_batch_id, row_number)
        );

        CREATE TABLE IF NOT EXISTS playbooks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version > 0),
            status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'published', 'retired')),
            owner_id TEXT NOT NULL REFERENCES people(id),
            protocol_json TEXT NOT NULL,
            effective_from TEXT,
            approved_by_person_id TEXT REFERENCES people(id),
            approved_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (name, version)
        );

        CREATE TABLE IF NOT EXISTS trials (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id),
            protocol_version TEXT NOT NULL,
            decision_question TEXT NOT NULL,
            treatment_json TEXT NOT NULL,
            comparator_json TEXT NOT NULL,
            eligibility_rule_json TEXT NOT NULL,
            measurements_json TEXT NOT NULL,
            guardrails_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'paused', 'stopped', 'completed')),
            starts_on TEXT,
            ends_on TEXT,
            status_reason TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trial_allocations (
            id TEXT PRIMARY KEY,
            trial_id TEXT NOT NULL REFERENCES trials(id),
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            arm TEXT NOT NULL CHECK (arm IN ('treatment', 'comparator')),
            status TEXT NOT NULL CHECK (status IN ('eligible', 'enrolled', 'withdrawn', 'excluded')),
            enrolled_at TEXT,
            withdrawn_at TEXT,
            reason TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (trial_id, allocation_id)
        );

        CREATE TABLE IF NOT EXISTS trial_confounders (
            id TEXT PRIMARY KEY,
            trial_id TEXT NOT NULL REFERENCES trials(id),
            allocation_id TEXT REFERENCES crop_allocations(id),
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            evidence_artifact_id TEXT REFERENCES evidence_artifacts(id),
            actor_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trial_conclusions (
            id TEXT PRIMARY KEY,
            trial_id TEXT NOT NULL REFERENCES trials(id),
            reviewer_id TEXT NOT NULL REFERENCES people(id),
            status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'approved', 'rejected')),
            result_json TEXT NOT NULL,
            confidence_level TEXT NOT NULL CHECK (confidence_level IN ('low', 'medium', 'high')),
            limitations_json TEXT NOT NULL,
            evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id),
            playbook_id TEXT REFERENCES playbooks(id),
            playbook_decision TEXT NOT NULL CHECK (playbook_decision IN ('none', 'create', 'revise', 'promote', 'retire')),
            approved_at TEXT,
            created_at TEXT NOT NULL,
            CHECK (playbook_decision != 'promote' OR (status = 'approved' AND approved_at IS NOT NULL AND playbook_id IS NOT NULL))
        );

        CREATE INDEX IF NOT EXISTS idx_field_signals_allocation_observed
            ON field_signals (allocation_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_crop_stage_checkpoints_allocation_planned
            ON crop_stage_checkpoints (allocation_id, planned_for);
        CREATE INDEX IF NOT EXISTS idx_harvest_records_allocation_created
            ON harvest_records (allocation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_season_reviews_allocation_created
            ON season_reviews (allocation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_source_runs_source_created
            ON source_runs (source_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_regional_signals_region_observed
            ON regional_signals (region, observed_at);
        CREATE INDEX IF NOT EXISTS idx_import_rows_batch_number
            ON import_rows (import_batch_id, row_number);
        CREATE INDEX IF NOT EXISTS idx_import_batches_purpose_received
            ON import_batches (purpose, received_at);
        CREATE INDEX IF NOT EXISTS idx_trial_allocations_trial
            ON trial_allocations (trial_id);
        CREATE INDEX IF NOT EXISTS idx_trials_owner_created
            ON trials (owner_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_trial_confounders_trial
            ON trial_confounders (trial_id);
        CREATE INDEX IF NOT EXISTS idx_trial_conclusions_trial
            ON trial_conclusions (trial_id);
        """
    )
    # ``CREATE TABLE IF NOT EXISTS`` cannot add columns to V1 pilot databases
    # already opened before this lifecycle field existed.  Keep this migration
    # idempotent and deliberately narrow.
    import_batch_columns = {row[1] for row in conn.execute("PRAGMA table_info(import_batches)").fetchall()}
    if "reviewed_by_id" not in import_batch_columns:
        conn.execute("ALTER TABLE import_batches ADD COLUMN reviewed_by_id TEXT")
    # V1 initially used a non-null ``enrolled_at`` despite also modelling an
    # ``eligible`` state.  Eligible is intentionally pre-enrolment, so retain
    # existing trial data while rebuilding this isolated table with a nullable
    # timestamp.  No table has a foreign key to trial_allocations.
    trial_allocation_columns = {
        row[1]: row for row in conn.execute("PRAGMA table_info(trial_allocations)").fetchall()
    }
    if trial_allocation_columns.get("enrolled_at", [None, None, None, 0])[3]:
        with conn:
            conn.execute("ALTER TABLE trial_allocations RENAME TO trial_allocations_legacy")
            conn.execute(
                """CREATE TABLE trial_allocations (
                    id TEXT PRIMARY KEY,
                    trial_id TEXT NOT NULL REFERENCES trials(id),
                    allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
                    arm TEXT NOT NULL CHECK (arm IN ('treatment', 'comparator')),
                    status TEXT NOT NULL CHECK (status IN ('eligible', 'enrolled', 'withdrawn', 'excluded')),
                    enrolled_at TEXT,
                    withdrawn_at TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (trial_id, allocation_id)
                )"""
            )
            conn.execute(
                """INSERT INTO trial_allocations
                   (id, trial_id, allocation_id, arm, status, enrolled_at, withdrawn_at, reason, created_at)
                   SELECT id, trial_id, allocation_id, arm, status, enrolled_at, withdrawn_at, reason, created_at
                   FROM trial_allocations_legacy"""
            )
            conn.execute("DROP TABLE trial_allocations_legacy")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trial_allocations_trial ON trial_allocations (trial_id)"
            )
    conn.commit()
