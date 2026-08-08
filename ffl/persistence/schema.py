import sqlite3


def create_schema(conn: sqlite3.Connection) -> None:
    # Local SQLite files predate the phone-first portal.  Production uses the
    # reviewed PostgreSQL migration; this tiny additive shim merely keeps an
    # existing developer preview from failing before the full schema script can
    # create its new partial index below.
    existing_access_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(access_memberships)").fetchall()
    }
    if existing_access_columns and "identity_phone" not in existing_access_columns:
        conn.execute("ALTER TABLE access_memberships ADD COLUMN identity_phone TEXT")
    existing_trackwick_task_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(trackwick_tasks)").fetchall()
    }
    if (
        existing_trackwick_task_columns
        and "provider_plot_reference" not in existing_trackwick_task_columns
    ):
        conn.execute(
            "ALTER TABLE trackwick_tasks ADD COLUMN provider_plot_reference TEXT"
        )
    # Keep a long-lived local preview database compatible with the additive
    # operating-classification migration before its new indexes are created.
    existing_snapshot_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(entity_operating_snapshots)").fetchall()
    }
    snapshot_additions = (
        ("place_key", "TEXT"),
        ("linked_place_count", "INTEGER NOT NULL DEFAULT 0"),
        ("crop_profile", "TEXT NOT NULL DEFAULT 'not_recorded'"),
        ("latest_activity_kind", "TEXT NOT NULL DEFAULT 'unknown'"),
    )
    for column_name, definition in snapshot_additions:
        if existing_snapshot_columns and column_name not in existing_snapshot_columns:
            conn.execute(
                f"ALTER TABLE entity_operating_snapshots ADD COLUMN {column_name} {definition}"
            )
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

        CREATE TABLE IF NOT EXISTS farms (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
            reviewed_by_person_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS farm_fields (
            id TEXT PRIMARY KEY,
            farm_id TEXT NOT NULL REFERENCES farms(id),
            operational_block_id TEXT NOT NULL REFERENCES operational_blocks(id),
            starts_on TEXT NOT NULL,
            ends_on TEXT,
            status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
            reviewed_by_person_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL,
            CHECK ((status = 'active' AND ends_on IS NULL) OR (status = 'ended' AND ends_on IS NOT NULL))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_farm_fields_one_active_field
            ON farm_fields (operational_block_id) WHERE status = 'active';

        CREATE TRIGGER IF NOT EXISTS farm_fields_matching_operating_unit_insert
        BEFORE INSERT ON farm_fields
        WHEN NOT EXISTS (
            SELECT 1
            FROM farms
            JOIN operational_blocks
              ON operational_blocks.id = NEW.operational_block_id
            WHERE farms.id = NEW.farm_id
              AND farms.operating_unit_id = operational_blocks.operating_unit_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'farm and field must belong to the same operating unit');
        END;

        CREATE TRIGGER IF NOT EXISTS farm_fields_matching_operating_unit_update
        BEFORE UPDATE OF farm_id, operational_block_id ON farm_fields
        WHEN NOT EXISTS (
            SELECT 1
            FROM farms
            JOIN operational_blocks
              ON operational_blocks.id = NEW.operational_block_id
            WHERE farms.id = NEW.farm_id
              AND farms.operating_unit_id = operational_blocks.operating_unit_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'farm and field must belong to the same operating unit');
        END;

        -- A person may be related to one and only one operating scope at a
        -- time.  The scope is explicit rather than inferred from a name or
        -- imported procurement row: a grower is not automatically a
        -- landholder, and a village is not a field.
        CREATE TABLE IF NOT EXISTS person_operating_relationships (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL REFERENCES people(id),
            scope_type TEXT NOT NULL CHECK (scope_type IN (
                'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
            )),
            operating_unit_id TEXT REFERENCES operating_units(id),
            land_parcel_id TEXT REFERENCES land_parcels(id),
            operational_block_id TEXT REFERENCES operational_blocks(id),
            crop_allocation_id TEXT REFERENCES crop_allocations(id),
            role TEXT NOT NULL CHECK (role IN (
                'grower', 'landholder', 'lessee', 'field_operator', 'manager',
                'agronomist', 'reviewer', 'buyer_contact'
            )),
            starts_on TEXT NOT NULL,
            ends_on TEXT,
            status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
            provenance TEXT,
            reviewed_by_person_id TEXT REFERENCES people(id),
            ended_by_person_id TEXT REFERENCES people(id),
            ended_at TEXT,
            created_at TEXT NOT NULL,
            CHECK (
                (scope_type = 'operating_unit' AND operating_unit_id IS NOT NULL
                    AND land_parcel_id IS NULL AND operational_block_id IS NULL AND crop_allocation_id IS NULL)
                OR
                (scope_type = 'land_parcel' AND land_parcel_id IS NOT NULL
                    AND operating_unit_id IS NULL AND operational_block_id IS NULL AND crop_allocation_id IS NULL)
                OR
                (scope_type = 'operational_block' AND operational_block_id IS NOT NULL
                    AND operating_unit_id IS NULL AND land_parcel_id IS NULL AND crop_allocation_id IS NULL)
                OR
                (scope_type = 'crop_allocation' AND crop_allocation_id IS NOT NULL
                    AND operating_unit_id IS NULL AND land_parcel_id IS NULL AND operational_block_id IS NULL)
            ),
            CHECK ((status = 'active' AND ends_on IS NULL AND ended_by_person_id IS NULL AND ended_at IS NULL)
                OR (status = 'ended' AND ends_on IS NOT NULL)),
            CHECK (provenance IS NOT NULL OR reviewed_by_person_id IS NOT NULL)
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

        -- The request ledger is an intent to collect a bounded fact or proof,
        -- never a provider message or a field update.  Its approved bilingual
        -- copy is immutable: change the intent by cancelling and creating a
        -- fresh request, so a later delivery adapter cannot silently alter the
        -- instruction shown to the field team.
        CREATE TABLE IF NOT EXISTS field_information_requests (
            id TEXT PRIMARY KEY,
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            target_person_id TEXT NOT NULL REFERENCES people(id),
            work_item_id TEXT REFERENCES work_items(id),
            request_kind TEXT NOT NULL CHECK (request_kind IN (
                'field_check', 'evidence_photo', 'irrigation_status',
                'input_application', 'pest_or_deviation', 'harvest_update'
            )),
            evidence_required INTEGER NOT NULL CHECK (evidence_required IN (0, 1)),
            due_at TEXT NOT NULL,
            request_copy_en TEXT NOT NULL CHECK (length(trim(request_copy_en)) BETWEEN 1 AND 1600),
            request_copy_hi TEXT NOT NULL CHECK (length(trim(request_copy_hi)) BETWEEN 1 AND 1600),
            initiated_by_person_id TEXT REFERENCES people(id),
            initiated_by_system_key TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN (
                'draft', 'ready', 'dispatched', 'responded', 'expired', 'cancelled'
            )),
            created_at TEXT NOT NULL,
            CHECK (
                (initiated_by_person_id IS NOT NULL AND initiated_by_system_key IS NULL)
                OR (initiated_by_person_id IS NULL AND initiated_by_system_key IS NOT NULL)
            )
        );

        CREATE TABLE IF NOT EXISTS field_information_request_events (
            id TEXT PRIMARY KEY,
            field_information_request_id TEXT NOT NULL REFERENCES field_information_requests(id),
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            actor_person_id TEXT REFERENCES people(id),
            actor_system_key TEXT,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (
                (actor_person_id IS NOT NULL AND actor_system_key IS NULL)
                OR (actor_person_id IS NULL AND actor_system_key IS NOT NULL)
            )
        );

        CREATE TRIGGER IF NOT EXISTS field_information_requests_copy_immutable
        BEFORE UPDATE OF allocation_id, target_person_id, work_item_id, request_kind,
                         evidence_required, due_at, request_copy_en, request_copy_hi,
                         initiated_by_person_id, initiated_by_system_key, idempotency_key,
                         created_at
        ON field_information_requests
        BEGIN
            SELECT RAISE(ABORT, 'field information request copy is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS field_information_requests_linked_work_matches_allocation
        BEFORE INSERT ON field_information_requests
        WHEN NEW.work_item_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM work_items
            WHERE id = NEW.work_item_id AND allocation_id = NEW.allocation_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'linked work item must belong to the same crop allocation');
        END;

        CREATE TRIGGER IF NOT EXISTS field_information_requests_no_delete
        BEFORE DELETE ON field_information_requests
        BEGIN
            SELECT RAISE(ABORT, 'field information requests are append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS field_information_requests_valid_transition
        BEFORE UPDATE OF status ON field_information_requests
        WHEN NOT (
            (OLD.status = 'draft' AND NEW.status IN ('ready', 'expired', 'cancelled'))
            OR (OLD.status = 'ready' AND NEW.status IN ('dispatched', 'expired', 'cancelled'))
            OR (OLD.status = 'dispatched' AND NEW.status IN ('responded', 'expired', 'cancelled'))
        )
        BEGIN
            SELECT RAISE(ABORT, 'invalid field information request transition');
        END;

        CREATE TRIGGER IF NOT EXISTS field_information_request_events_no_update
        BEFORE UPDATE ON field_information_request_events
        BEGIN
            SELECT RAISE(ABORT, 'field information request events are append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS field_information_request_events_no_delete
        BEFORE DELETE ON field_information_request_events
        BEGIN
            SELECT RAISE(ABORT, 'field information request events are append-only');
        END;

        -- A field capture pass is an opaque bearer capability issued only by
        -- the manager boundary.  The raw token is never in this table; a keyed
        -- digest is enough to resolve it while preserving revocation and audit
        -- context.  It binds one reviewed information request to one immutable
        -- signal template and never decides or completes farm work.
        CREATE TABLE IF NOT EXISTS field_capture_passes (
            id TEXT PRIMARY KEY,
            field_information_request_id TEXT NOT NULL REFERENCES field_information_requests(id),
            signal_template_id TEXT NOT NULL REFERENCES signal_templates(id),
            signal_template_version INTEGER NOT NULL CHECK (signal_template_version > 0),
            token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64 AND token_hash = lower(token_hash)),
            issued_by_person_id TEXT NOT NULL REFERENCES people(id),
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'used', 'revoked')),
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            CHECK ((status = 'revoked' AND revoked_at IS NOT NULL) OR (status != 'revoked' AND revoked_at IS NULL))
        );

        CREATE TABLE IF NOT EXISTS field_capture_candidates (
            id TEXT PRIMARY KEY,
            field_information_request_id TEXT NOT NULL REFERENCES field_information_requests(id),
            field_capture_pass_id TEXT NOT NULL REFERENCES field_capture_passes(id),
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            actor_person_id TEXT NOT NULL REFERENCES people(id),
            signal_template_id TEXT NOT NULL REFERENCES signal_templates(id),
            signal_template_version INTEGER NOT NULL CHECK (signal_template_version > 0),
            observed_at TEXT NOT NULL,
            values_json TEXT NOT NULL,
            evidence_artifact_id TEXT REFERENCES evidence_artifacts(id),
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('review', 'accepting', 'accepted', 'rejected')),
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            accepted_signal_id TEXT REFERENCES field_signals(id),
            created_at TEXT NOT NULL,
            UNIQUE (field_capture_pass_id, idempotency_key),
            CHECK (
                (status IN ('review', 'accepting') AND reviewed_by_person_id IS NULL
                    AND reviewed_at IS NULL AND accepted_signal_id IS NULL)
                OR (status = 'accepted' AND reviewed_by_person_id IS NOT NULL
                    AND reviewed_at IS NOT NULL AND accepted_signal_id IS NOT NULL)
                OR (status = 'rejected' AND reviewed_by_person_id IS NOT NULL
                    AND reviewed_at IS NOT NULL AND accepted_signal_id IS NULL)
            )
        );

        CREATE TRIGGER IF NOT EXISTS field_capture_passes_immutable
        BEFORE UPDATE OF field_information_request_id, signal_template_id, signal_template_version,
                         token_hash, issued_by_person_id, expires_at, created_at
        ON field_capture_passes
        BEGIN
            SELECT RAISE(ABORT, 'field capture pass scope is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS field_capture_passes_valid_transition
        BEFORE UPDATE OF status, revoked_at ON field_capture_passes
        WHEN NOT (
            (OLD.status = 'active' AND NEW.status IN ('used', 'revoked'))
            OR (OLD.status = NEW.status AND OLD.revoked_at IS NEW.revoked_at)
        )
        BEGIN
            SELECT RAISE(ABORT, 'invalid field capture pass transition');
        END;

        CREATE TRIGGER IF NOT EXISTS field_capture_passes_no_delete
        BEFORE DELETE ON field_capture_passes
        BEGIN
            SELECT RAISE(ABORT, 'field capture passes are append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS field_capture_candidates_immutable
        BEFORE UPDATE OF field_information_request_id, field_capture_pass_id, allocation_id,
                         actor_person_id, signal_template_id, signal_template_version, observed_at,
                         values_json, evidence_artifact_id, idempotency_key, created_at
        ON field_capture_candidates
        BEGIN
            SELECT RAISE(ABORT, 'field capture candidate is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS field_capture_candidates_valid_transition
        BEFORE UPDATE OF status, reviewed_by_person_id, reviewed_at, accepted_signal_id
        ON field_capture_candidates
        WHEN NOT (
            (OLD.status = 'review' AND NEW.status IN ('accepting', 'rejected'))
            OR (OLD.status = 'accepting' AND NEW.status = 'accepted')
            OR (OLD.status = NEW.status
                AND OLD.reviewed_by_person_id IS NEW.reviewed_by_person_id
                AND OLD.reviewed_at IS NEW.reviewed_at
                AND OLD.accepted_signal_id IS NEW.accepted_signal_id)
        )
        BEGIN
            SELECT RAISE(ABORT, 'invalid field capture candidate transition');
        END;

        CREATE TRIGGER IF NOT EXISTS field_capture_candidates_no_delete
        BEFORE DELETE ON field_capture_candidates
        BEGIN
            SELECT RAISE(ABORT, 'field capture candidates are append-only');
        END;

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

        -- A first farm is a privileged bootstrap action, not ordinary CRUD.
        -- The singleton guard makes the one-time invariant durable even when
        -- two application processes accept requests at the same instant.
        CREATE TABLE IF NOT EXISTS pilot_setup_acceptances (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL CHECK (length(content_hash) = 64 AND content_hash = lower(content_hash)),
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            manager_person_id TEXT NOT NULL REFERENCES people(id),
            first_work_item_id TEXT NOT NULL REFERENCES work_items(id),
            first_work_required_evidence_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status = 'accepted'),
            accepted_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (operating_unit_id)
        );

        CREATE TABLE IF NOT EXISTS pilot_setup_bootstrap_guard (
            id TEXT PRIMARY KEY CHECK (id = 'initial_setup'),
            acceptance_id TEXT NOT NULL UNIQUE REFERENCES pilot_setup_acceptances(id),
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

        -- Administrative context is deliberately separate from geometry or
        -- land-right evidence.  It lets FFL safely join district context now
        -- without pretending a village/PIN identifies a farm boundary.
        CREATE TABLE IF NOT EXISTS operating_unit_locations (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            country_code TEXT NOT NULL CHECK (country_code = 'IN'),
            state_name TEXT NOT NULL,
            district_name TEXT NOT NULL,
            district_context_key TEXT NOT NULL,
            subdistrict_name TEXT,
            village_name TEXT,
            pincode TEXT CHECK (
                pincode IS NULL OR (length(pincode) = 6 AND pincode NOT GLOB '*[^0-9]*')
            ),
            verification_method TEXT NOT NULL CHECK (verification_method IN ('field_verified', 'lgd_reference')),
            verified_by_person_id TEXT NOT NULL REFERENCES people(id),
            verified_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
            supersedes_location_id TEXT REFERENCES operating_unit_locations(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS soil_baselines (
            id TEXT PRIMARY KEY,
            operating_unit_id TEXT NOT NULL REFERENCES operating_units(id),
            sampled_on TEXT NOT NULL,
            depth_cm_start REAL CHECK (depth_cm_start IS NULL OR depth_cm_start >= 0),
            depth_cm_end REAL CHECK (depth_cm_end IS NULL OR depth_cm_end >= 0),
            lab_name TEXT NOT NULL,
            measurements_json TEXT NOT NULL,
            evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id),
            reviewed_by_person_id TEXT NOT NULL REFERENCES people(id),
            status TEXT NOT NULL CHECK (status IN ('reviewed', 'superseded')),
            created_at TEXT NOT NULL,
            CHECK (
                depth_cm_start IS NULL OR depth_cm_end IS NULL OR depth_cm_end >= depth_cm_start
            )
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

        CREATE TABLE IF NOT EXISTS agent_notifications (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 80),
            natural_language_rule TEXT NOT NULL CHECK (length(trim(natural_language_rule)) BETWEEN 8 AND 500),
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
            created_by_person_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_agent_notifications_enabled_updated
            ON agent_notifications (enabled, updated_at DESC);

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

        -- Private, source-backed operational context.  These rows do not
        -- establish farms, parcels, task completion, or agronomic decisions.
        -- Source revisions are append-only and remain separate from the
        -- reviewed import lifecycle that governs their publication.
        CREATE TABLE IF NOT EXISTS trackolap_records (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            import_batch_id TEXT REFERENCES import_batches(id),
            feed TEXT NOT NULL CHECK (feed IN (
                'officers', 'attendance', 'farmer_tasks', 'visits',
                'issue_observations', 'pesticide_events',
                'farmer_profiles', 'farm_candidates', 'field_workers',
                'crop_context', 'soil_context', 'follow_ups'
            )),
            source_identifier TEXT NOT NULL,
            source_updated_at TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            values_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('valid', 'quarantined', 'published')),
            created_at TEXT NOT NULL,
            UNIQUE (source_id, feed, source_identifier, source_updated_at)
        );

        -- Named application access is independent from a person's field role.
        -- A row without a verified Auth subject is intentionally pending and
        -- cannot authenticate a browser merely because its display name exists.
        CREATE TABLE IF NOT EXISTS access_memberships (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL UNIQUE REFERENCES people(id),
            auth_subject TEXT UNIQUE,
            identity_email TEXT,
            identity_phone TEXT,
            access_role TEXT NOT NULL CHECK (access_role IN ('owner', 'admin')),
            identity_status TEXT NOT NULL CHECK (identity_status IN ('identity_pending', 'invited', 'active', 'suspended')),
            invited_at TEXT,
            activated_at TEXT,
            last_authenticated_at TEXT,
            created_at TEXT NOT NULL,
            CHECK (
                (identity_status = 'identity_pending' AND auth_subject IS NULL AND identity_email IS NULL AND identity_phone IS NULL)
                OR (identity_status = 'invited' AND auth_subject IS NULL AND (identity_email IS NOT NULL OR identity_phone IS NOT NULL) AND invited_at IS NOT NULL)
                OR (identity_status = 'active' AND auth_subject IS NOT NULL AND (identity_email IS NOT NULL OR identity_phone IS NOT NULL) AND activated_at IS NOT NULL)
                OR identity_status = 'suspended'
            )
        );

        -- ID/password access is deliberately separate from imported contacts,
        -- operating roles, and the optional phone portal.  A signed browser
        -- cookie carries only this opaque identity id and a session binding;
        -- active role and status are re-read here for every protected request.
        CREATE TABLE IF NOT EXISTS password_identities (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL UNIQUE REFERENCES people(id),
            login_id TEXT NOT NULL UNIQUE CHECK (
                login_id = lower(login_id)
                AND length(login_id) BETWEEN 3 AND 64
            ),
            password_hash TEXT NOT NULL,
            access_role TEXT NOT NULL CHECK (
                access_role IN ('owner', 'admin', 'field_worker', 'farmer')
            ),
            identity_status TEXT NOT NULL CHECK (
                identity_status IN ('active', 'suspended')
            ),
            password_version INTEGER NOT NULL CHECK (password_version > 0),
            password_changed_at TEXT NOT NULL,
            last_authenticated_at TEXT,
            created_by_person_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL
        );

        -- A customer account is not an operating unit, a farm, or a CRM
        -- tenant.  It owns the hostname and is the outer boundary for a
        -- person's verified portal role.
        CREATE TABLE IF NOT EXISTS customer_portals (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            hostname TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('active', 'suspended')),
            created_at TEXT NOT NULL,
            CHECK (length(slug) BETWEEN 2 AND 63),
            CHECK (hostname = lower(hostname))
        );

        CREATE TABLE IF NOT EXISTS portal_identities (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL UNIQUE REFERENCES people(id),
            phone_e164 TEXT NOT NULL UNIQUE,
            auth_subject TEXT UNIQUE,
            identity_status TEXT NOT NULL CHECK (identity_status IN ('invited', 'active', 'suspended')),
            invited_at TEXT NOT NULL,
            verified_at TEXT,
            last_authenticated_at TEXT,
            created_at TEXT NOT NULL,
            CHECK (
                (identity_status = 'invited' AND auth_subject IS NULL AND verified_at IS NULL)
                OR (identity_status = 'active' AND auth_subject IS NOT NULL AND verified_at IS NOT NULL)
                OR identity_status = 'suspended'
            )
        );

        CREATE TABLE IF NOT EXISTS portal_memberships (
            id TEXT PRIMARY KEY,
            portal_id TEXT NOT NULL REFERENCES customer_portals(id),
            person_id TEXT NOT NULL REFERENCES people(id),
            identity_id TEXT REFERENCES portal_identities(id),
            portal_role TEXT NOT NULL CHECK (portal_role IN ('owner', 'admin', 'field_worker', 'farmer')),
            membership_status TEXT NOT NULL CHECK (membership_status IN ('identity_pending', 'invited', 'active', 'suspended')),
            invited_at TEXT,
            activated_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (portal_id, person_id),
            CHECK (
                (membership_status = 'identity_pending' AND identity_id IS NULL)
                OR (membership_status = 'invited' AND identity_id IS NOT NULL AND invited_at IS NOT NULL)
                OR (membership_status = 'active' AND identity_id IS NOT NULL AND activated_at IS NOT NULL)
                OR membership_status = 'suspended'
            )
        );

        -- Private communications authority is anchored to an explicit portal
        -- membership and canonical person. Provider addresses never establish
        -- person, role, tenant, or operating scope authority.
        CREATE TABLE IF NOT EXISTS communication_profiles (
            id TEXT PRIMARY KEY,
            portal_id TEXT NOT NULL REFERENCES customer_portals(id),
            person_id TEXT NOT NULL REFERENCES people(id),
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
            locale TEXT NOT NULL,
            time_zone TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (portal_id, person_id)
        );

        CREATE TABLE IF NOT EXISTS communication_endpoint_verifications (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES communication_profiles(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            verification_method TEXT NOT NULL,
            verified_by_person_id TEXT NOT NULL REFERENCES people(id),
            verified_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
            revoked_at TEXT,
            CHECK ((status = 'active' AND revoked_at IS NULL) OR status IN ('revoked', 'disabled'))
        );

        CREATE TABLE IF NOT EXISTS communication_endpoint_scopes (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES communication_profiles(id),
            relationship_id TEXT NOT NULL REFERENCES person_operating_relationships(id),
            scope_type TEXT NOT NULL CHECK (scope_type IN (
                'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
            )),
            scope_id TEXT NOT NULL,
            starts_on TEXT NOT NULL,
            ends_on TEXT,
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
            CHECK ((status = 'active' AND ends_on IS NULL) OR status IN ('revoked', 'disabled')),
            UNIQUE (profile_id, relationship_id, scope_type, scope_id)
        );

        CREATE TABLE IF NOT EXISTS communication_scoped_consents (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES communication_profiles(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            purpose TEXT NOT NULL CHECK (purpose IN (
                'work_prompt', 'weekly_farmer_checkin', 'field_evidence_request',
                'local_weather_observation', 'problem_report', 'callback_coordination',
                'safety_escalation', 'operational_campaign'
            )),
            scope_type TEXT NOT NULL CHECK (scope_type IN (
                'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
            )),
            scope_id TEXT NOT NULL,
            channel TEXT NOT NULL CHECK (channel IN ('whatsapp')),
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'disabled')),
            evidence TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            revoked_at TEXT,
            CHECK ((status = 'active' AND revoked_at IS NULL)
                OR (status = 'revoked' AND revoked_at IS NOT NULL)
                OR status = 'disabled'),
            UNIQUE (endpoint_id, purpose, scope_type, scope_id, channel)
        );

        CREATE TABLE IF NOT EXISTS communication_scoped_consent_events (
            id TEXT PRIMARY KEY,
            consent_id TEXT NOT NULL REFERENCES communication_scoped_consents(id),
            profile_id TEXT NOT NULL REFERENCES communication_profiles(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            purpose TEXT NOT NULL CHECK (purpose IN (
                'work_prompt', 'weekly_farmer_checkin', 'field_evidence_request',
                'local_weather_observation', 'problem_report', 'callback_coordination',
                'safety_escalation', 'operational_campaign'
            )),
            scope_type TEXT NOT NULL CHECK (scope_type IN (
                'operating_unit', 'land_parcel', 'operational_block', 'crop_allocation'
            )),
            scope_id TEXT NOT NULL,
            channel TEXT NOT NULL CHECK (channel IN ('whatsapp')),
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
            evidence TEXT NOT NULL,
            actor_person_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_communication_endpoint_verifications_active
            ON communication_endpoint_verifications(endpoint_id, profile_id)
            WHERE status = 'active';
        CREATE INDEX IF NOT EXISTS idx_communication_profiles_person
            ON communication_profiles(person_id);
        CREATE INDEX IF NOT EXISTS idx_communication_endpoint_verifications_profile
            ON communication_endpoint_verifications(profile_id);
        CREATE INDEX IF NOT EXISTS idx_communication_endpoint_verifications_endpoint
            ON communication_endpoint_verifications(endpoint_id);
        CREATE INDEX IF NOT EXISTS idx_communication_endpoint_verifications_verifier
            ON communication_endpoint_verifications(verified_by_person_id);
        CREATE INDEX IF NOT EXISTS idx_communication_endpoint_scopes_profile
            ON communication_endpoint_scopes(profile_id);
        CREATE INDEX IF NOT EXISTS idx_communication_endpoint_scopes_relationship
            ON communication_endpoint_scopes(relationship_id);
        CREATE INDEX IF NOT EXISTS idx_communication_scoped_consents_profile
            ON communication_scoped_consents(profile_id);
        CREATE INDEX IF NOT EXISTS idx_communication_scoped_consent_events_consent
            ON communication_scoped_consent_events(consent_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_communication_scoped_consent_events_profile
            ON communication_scoped_consent_events(profile_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_communication_scoped_consent_events_endpoint
            ON communication_scoped_consent_events(endpoint_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_communication_scoped_consent_events_actor
            ON communication_scoped_consent_events(actor_person_id, created_at);
        CREATE TRIGGER IF NOT EXISTS communication_scoped_consents_capture_immutable
        BEFORE UPDATE OF profile_id, endpoint_id, purpose, scope_type, scope_id,
                         channel, evidence, granted_at
        ON communication_scoped_consents
        BEGIN
            SELECT RAISE(ABORT, 'communication scoped consent capture is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_scoped_consent_events_no_update
        BEFORE UPDATE ON communication_scoped_consent_events
        BEGIN
            SELECT RAISE(ABORT, 'communication scoped consent events are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_scoped_consent_events_no_delete
        BEFORE DELETE ON communication_scoped_consent_events
        BEGIN
            SELECT RAISE(ABORT, 'communication scoped consent events are append-only');
        END;

        -- Interaction captures are immutable correlation authority.  The
        -- raw opaque context token is issued to the outbound adapter once and
        -- never stored; only its SHA-256 digest belongs in the database.
        CREATE TABLE IF NOT EXISTS communication_interaction_runs (
            id TEXT PRIMARY KEY,
            profile_id TEXT REFERENCES communication_profiles(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            allocation_id TEXT REFERENCES crop_allocations(id),
            work_item_id TEXT REFERENCES work_items(id),
            field_information_request_id TEXT REFERENCES field_information_requests(id),
            workflow_version_id TEXT,
            campaign_snapshot_id TEXT,
            legacy_prompt_id TEXT UNIQUE REFERENCES communication_prompts(id),
            context_token_hash TEXT NOT NULL UNIQUE
                CHECK (length(context_token_hash) = 64 AND context_token_hash = lower(context_token_hash)),
            expected_intents_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN (
                'ready', 'dispatching', 'dispatched', 'responded', 'expired', 'cancelled'
            )),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            CHECK (expires_at > created_at),
            CHECK (profile_id IS NOT NULL OR legacy_prompt_id IS NOT NULL)
        );
        CREATE TABLE IF NOT EXISTS communication_interaction_dispatches (
            id TEXT PRIMARY KEY,
            interaction_run_id TEXT NOT NULL UNIQUE REFERENCES communication_interaction_runs(id),
            provider TEXT NOT NULL,
            provider_message_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN (
                'accepted', 'scheduled', 'delivered', 'failed', 'unknown'
            )),
            created_at TEXT NOT NULL,
            UNIQUE (provider, provider_message_id)
        );
        CREATE TABLE IF NOT EXISTS communication_workflows (
            id TEXT PRIMARY KEY,
            workflow_key TEXT NOT NULL UNIQUE,
            owner_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_workflow_versions (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL REFERENCES communication_workflows(id),
            version INTEGER NOT NULL CHECK (version > 0),
            purpose TEXT NOT NULL CHECK (purpose IN (
                'work_prompt', 'weekly_farmer_checkin', 'field_evidence_request',
                'local_weather_observation', 'problem_report', 'callback_coordination',
                'safety_escalation', 'operational_campaign'
            )),
            owner_id TEXT NOT NULL REFERENCES people(id),
            status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'paused')),
            trigger_json TEXT NOT NULL,
            audience_json TEXT NOT NULL,
            template_id TEXT NOT NULL REFERENCES communication_templates(id),
            expected_intents_json TEXT NOT NULL,
            response_deadline_hours INTEGER NOT NULL CHECK (response_deadline_hours > 0),
            quiet_hours_json TEXT,
            frequency_cap INTEGER CHECK (frequency_cap > 0),
            escalation_owner_id TEXT REFERENCES people(id),
            created_at TEXT NOT NULL,
            published_at TEXT,
            UNIQUE (workflow_id, version)
        );
        CREATE TABLE IF NOT EXISTS communication_workflow_runs (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES communication_profiles(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            workflow_version_id TEXT NOT NULL REFERENCES communication_workflow_versions(id),
            interaction_run_id TEXT NOT NULL UNIQUE REFERENCES communication_interaction_runs(id),
            weekly_window TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (profile_id, allocation_id, workflow_version_id, weekly_window)
        );
        CREATE INDEX IF NOT EXISTS idx_communication_interaction_runs_profile
            ON communication_interaction_runs(profile_id);
        CREATE INDEX IF NOT EXISTS idx_communication_interaction_runs_endpoint_status
            ON communication_interaction_runs(endpoint_id, status, expires_at);
        CREATE INDEX IF NOT EXISTS idx_communication_interaction_runs_allocation
            ON communication_interaction_runs(allocation_id);
        CREATE INDEX IF NOT EXISTS idx_communication_interaction_runs_work_item
            ON communication_interaction_runs(work_item_id);
        CREATE INDEX IF NOT EXISTS idx_communication_interaction_runs_field_request
            ON communication_interaction_runs(field_information_request_id);
        CREATE INDEX IF NOT EXISTS idx_communication_interaction_dispatches_message
            ON communication_interaction_dispatches(provider, provider_message_id);
        CREATE INDEX IF NOT EXISTS idx_communication_workflow_versions_workflow_status
            ON communication_workflow_versions(workflow_id, status, version);
        CREATE INDEX IF NOT EXISTS idx_communication_workflow_runs_version_window
            ON communication_workflow_runs(workflow_version_id, weekly_window);
        CREATE TRIGGER IF NOT EXISTS communication_interaction_runs_capture_immutable
        BEFORE UPDATE OF id, profile_id, endpoint_id, allocation_id, work_item_id,
                         field_information_request_id, workflow_version_id,
                         campaign_snapshot_id, legacy_prompt_id, context_token_hash,
                         expected_intents_json, created_at, expires_at
        ON communication_interaction_runs
        BEGIN
            SELECT RAISE(ABORT, 'communication interaction run capture is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_interaction_runs_no_delete
        BEFORE DELETE ON communication_interaction_runs
        BEGIN
            SELECT RAISE(ABORT, 'communication interaction runs are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_interaction_dispatches_capture_immutable
        BEFORE UPDATE OF id, interaction_run_id, provider, provider_message_id, created_at
        ON communication_interaction_dispatches
        BEGIN
            SELECT RAISE(ABORT, 'communication interaction dispatch capture is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_interaction_dispatches_no_delete
        BEFORE DELETE ON communication_interaction_dispatches
        BEGIN
            SELECT RAISE(ABORT, 'communication interaction dispatches are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_workflow_versions_capture_immutable
        BEFORE UPDATE OF id, workflow_id, version, purpose, owner_id, trigger_json,
                         audience_json, template_id, expected_intents_json,
                         response_deadline_hours, quiet_hours_json, frequency_cap,
                         escalation_owner_id, created_at
        ON communication_workflow_versions
        BEGIN
            SELECT RAISE(ABORT, 'communication workflow version capture is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_workflow_versions_no_delete
        BEFORE DELETE ON communication_workflow_versions
        BEGIN
            SELECT RAISE(ABORT, 'communication workflow versions are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_workflow_versions_lifecycle_guard
        BEFORE UPDATE OF status, published_at ON communication_workflow_versions
        WHEN NOT (
            OLD.status = 'draft' AND NEW.status = 'published'
            AND OLD.published_at IS NULL AND NEW.published_at IS NOT NULL
        ) AND NOT (
            OLD.status = 'published' AND NEW.status = 'paused'
            AND NEW.published_at IS OLD.published_at
        )
        BEGIN
            SELECT RAISE(ABORT, 'communication workflow version lifecycle is invalid');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_workflow_runs_no_update
        BEFORE UPDATE ON communication_workflow_runs
        BEGIN
            SELECT RAISE(ABORT, 'communication workflow runs are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS communication_workflow_runs_no_delete
        BEFORE DELETE ON communication_workflow_runs
        BEGIN
            SELECT RAISE(ABORT, 'communication workflow runs are append-only');
        END;

        -- Private TrackWick CRM and spatial evidence.  This is a typed source
        -- lane, not a shortcut into Fortune's canonical farm graph.  SQLite
        -- mirrors the PostgreSQL shape for tests; production additionally
        -- derives a PostGIS geography point from each coordinate pair.
        CREATE TABLE IF NOT EXISTS trackwick_parties (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            party_kind TEXT NOT NULL CHECK (party_kind IN ('farmer', 'field_worker')),
            provider_identifier TEXT NOT NULL,
            display_name TEXT NOT NULL,
            crm_status TEXT,
            provider_owner_identifier TEXT,
            provider_tag TEXT,
            provider_created_at TEXT,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (source_id, party_kind, provider_identifier)
        );

        CREATE TABLE IF NOT EXISTS trackwick_contact_points (
            id TEXT PRIMARY KEY,
            party_id TEXT NOT NULL REFERENCES trackwick_parties(id),
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            contact_kind TEXT NOT NULL CHECK (contact_kind = 'mobile'),
            contact_value TEXT NOT NULL,
            value_fingerprint TEXT NOT NULL CHECK (length(value_fingerprint) = 64 AND value_fingerprint = lower(value_fingerprint)),
            consent_status TEXT NOT NULL CHECK (consent_status IN ('unknown', 'granted', 'revoked')),
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (party_id, contact_kind, value_fingerprint)
        );

        CREATE TABLE IF NOT EXISTS trackwick_tasks (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            provider_task_id TEXT NOT NULL,
            farmer_party_id TEXT REFERENCES trackwick_parties(id),
            field_worker_party_id TEXT REFERENCES trackwick_parties(id),
            provider_customer_identifier TEXT,
            task_type TEXT NOT NULL,
            task_status TEXT NOT NULL CHECK (task_status IN ('completed', 'in_progress', 'pending', 'unknown')),
            provider_created_at TEXT,
            provider_started_at TEXT,
            provider_completed_at TEXT,
            provider_follow_up_at TEXT,
            provider_plot_reference TEXT,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (source_id, provider_task_id)
        );

        CREATE TABLE IF NOT EXISTS trackwick_visits (
            task_id TEXT PRIMARY KEY REFERENCES trackwick_tasks(id),
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            observed_at TEXT NOT NULL,
            transplanted_on TEXT,
            crop_stage TEXT,
            water_condition TEXT,
            crop_condition_score REAL CHECK (crop_condition_score IS NULL OR (crop_condition_score >= 1 AND crop_condition_score <= 10)),
            kit_status TEXT NOT NULL CHECK (kit_status IN ('taken', 'not_taken', 'unknown')),
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trackwick_visit_findings (
            id TEXT PRIMARY KEY,
            visit_task_id TEXT NOT NULL REFERENCES trackwick_visits(task_id),
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            finding_kind TEXT NOT NULL CHECK (finding_kind IN ('pest', 'disease')),
            reported_value TEXT NOT NULL,
            source_field TEXT NOT NULL,
            declared_severity TEXT NOT NULL CHECK (declared_severity IN ('unknown', 'low', 'moderate', 'high', 'critical')),
            observed_at TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (visit_task_id, finding_kind, source_field, reported_value)
        );

        CREATE TABLE IF NOT EXISTS trackwick_crop_inputs (
            id TEXT PRIMARY KEY,
            visit_task_id TEXT NOT NULL REFERENCES trackwick_visits(task_id),
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            input_kind TEXT NOT NULL CHECK (input_kind IN ('pesticide', 'fertilizer')),
            event_kind TEXT NOT NULL CHECK (event_kind IN ('applied', 'recommended')),
            reported_product TEXT NOT NULL,
            source_field TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (visit_task_id, input_kind, event_kind, source_field, reported_product)
        );

        CREATE TABLE IF NOT EXISTS trackwick_registrations (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL UNIQUE REFERENCES trackwick_tasks(id),
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            farmer_party_id TEXT REFERENCES trackwick_parties(id),
            registration_status TEXT NOT NULL CHECK (registration_status IN ('completed', 'in_progress', 'pending', 'unknown')),
            village_name TEXT,
            block_name TEXT,
            district_name TEXT,
            reported_total_area_acres REAL,
            reported_plot_count INTEGER CHECK (reported_plot_count IS NULL OR reported_plot_count >= 0),
            reported_pb1_area_acres REAL,
            reported_1718_area_acres REAL,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trackwick_registration_plots (
            id TEXT PRIMARY KEY,
            registration_id TEXT NOT NULL REFERENCES trackwick_registrations(id),
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            ordinal INTEGER NOT NULL CHECK (ordinal > 0),
            gata_number TEXT,
            reported_area_bigha REAL,
            plot_type TEXT,
            village_name TEXT,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (registration_id, ordinal)
        );

        -- A task may support a registration plot only when the private source
        -- graph carries an explicit exact association.  Farmer-wide task
        -- history is never promoted into a per-plot claim.
        CREATE TABLE IF NOT EXISTS trackwick_task_plot_links (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            task_id TEXT NOT NULL REFERENCES trackwick_tasks(id),
            registration_id TEXT NOT NULL REFERENCES trackwick_registrations(id),
            plot_id TEXT NOT NULL REFERENCES trackwick_registration_plots(id),
            association_kind TEXT NOT NULL CHECK (association_kind = 'source_explicit'),
            source_fingerprint TEXT NOT NULL CHECK (
                length(source_fingerprint) = 64
                AND source_fingerprint = lower(source_fingerprint)
                AND source_fingerprint NOT GLOB '*[^0-9a-f]*'
            ),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (
                data_quality_status IN ('valid', 'incomplete', 'quarantined')
            ),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (task_id)
        );

        CREATE TABLE IF NOT EXISTS trackwick_media_references (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            task_id TEXT NOT NULL REFERENCES trackwick_tasks(id),
            provider_media_key TEXT NOT NULL,
            media_kind TEXT NOT NULL CHECK (media_kind IN ('crop_photo', 'plot_photo')),
            remote_url TEXT NOT NULL CHECK (remote_url GLOB 'https://trackolap-images-prod.s3.amazonaws.com/*'),
            provider_created_at TEXT,
            source_access_state TEXT NOT NULL CHECK (source_access_state IN ('available', 'unavailable', 'blocked')),
            content_state TEXT NOT NULL CHECK (content_state IN ('remote_only', 'retained', 'failed')),
            exif_state TEXT NOT NULL CHECK (exif_state IN ('not_checked', 'extracted', 'absent', 'unreadable')),
            content_hash TEXT CHECK (content_hash IS NULL OR (length(content_hash) = 64 AND content_hash = lower(content_hash))),
            content_type TEXT,
            size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (source_id, provider_media_key)
        );

        CREATE TABLE IF NOT EXISTS trackwick_location_observations (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            party_id TEXT REFERENCES trackwick_parties(id),
            task_id TEXT REFERENCES trackwick_tasks(id),
            registration_id TEXT REFERENCES trackwick_registrations(id),
            media_reference_id TEXT REFERENCES trackwick_media_references(id),
            provider_location_key TEXT NOT NULL,
            location_kind TEXT NOT NULL CHECK (location_kind IN (
                'task_completion', 'visit_location', 'registration', 'media_capture', 'crm', 'soil'
            )),
            location_confidence TEXT NOT NULL CHECK (location_confidence IN ('declared', 'observed', 'verified')),
            latitude REAL NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
            longitude REAL NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
            provider_address TEXT,
            provider_geo_address TEXT,
            provider_accuracy_m REAL CHECK (provider_accuracy_m IS NULL OR provider_accuracy_m >= 0),
            observed_at TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (party_id IS NOT NULL OR task_id IS NOT NULL OR registration_id IS NOT NULL OR media_reference_id IS NOT NULL),
            UNIQUE (source_id, provider_location_key)
        );

        CREATE TABLE IF NOT EXISTS trackwick_worker_days (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            field_worker_party_id TEXT NOT NULL REFERENCES trackwick_parties(id),
            observed_on TEXT NOT NULL,
            attendance_status TEXT NOT NULL CHECK (attendance_status IN ('present', 'not_punched', 'unknown')),
            reported_start_time TEXT,
            reported_total_time TEXT,
            source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64 AND source_fingerprint = lower(source_fingerprint)),
            mapping_version TEXT NOT NULL,
            data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('valid', 'incomplete', 'quarantined')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (field_worker_party_id, observed_on)
        );

        -- One safe, deterministic operating snapshot per reported entity.
        -- It stores counts and timestamps only; provider fields, contact data,
        -- coordinates, diagnosis values, and raw source payloads stay private.
        CREATE TABLE IF NOT EXISTS entity_operating_snapshots (
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_run_id TEXT REFERENCES source_runs(id),
            entity_kind TEXT NOT NULL CHECK (entity_kind IN ('reported_farm', 'farmer', 'field_worker')),
            entity_id TEXT NOT NULL,
            place_key TEXT,
            linked_place_count INTEGER NOT NULL DEFAULT 0 CHECK (linked_place_count >= 0),
            crop_profile TEXT NOT NULL DEFAULT 'not_recorded' CHECK (crop_profile IN ('pb1', '1718', 'mixed', 'not_recorded')),
            farm_count INTEGER NOT NULL DEFAULT 0 CHECK (farm_count >= 0),
            farmer_count INTEGER NOT NULL DEFAULT 0 CHECK (farmer_count >= 0),
            open_task_count INTEGER NOT NULL DEFAULT 0 CHECK (open_task_count >= 0),
            completed_work_count INTEGER NOT NULL DEFAULT 0 CHECK (completed_work_count >= 0),
            visit_count INTEGER NOT NULL DEFAULT 0 CHECK (visit_count >= 0),
            disease_report_count INTEGER NOT NULL DEFAULT 0 CHECK (disease_report_count >= 0),
            pest_report_count INTEGER NOT NULL DEFAULT 0 CHECK (pest_report_count >= 0),
            location_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (location_evidence_count >= 0),
            photo_reference_count INTEGER NOT NULL DEFAULT 0 CHECK (photo_reference_count >= 0),
            attendance_present_days INTEGER NOT NULL DEFAULT 0 CHECK (attendance_present_days >= 0),
            reported_area_acres REAL CHECK (reported_area_acres IS NULL OR reported_area_acres >= 0),
            latest_activity_at TEXT,
            latest_activity_kind TEXT NOT NULL DEFAULT 'unknown' CHECK (latest_activity_kind IN ('registration', 'visit', 'issue', 'work', 'location', 'photo', 'attendance', 'unknown')),
            enrichment_version TEXT NOT NULL CHECK (length(enrichment_version) BETWEEN 1 AND 32),
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, entity_kind, entity_id)
        );

        -- A private, source-scoped location dictionary and task vocabulary.
        -- They make future imports consistent without turning place aliases or
        -- task labels into public identity, field-boundary, or diagnosis data.
        CREATE TABLE IF NOT EXISTS place_catalog (
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            place_key TEXT NOT NULL CHECK (length(place_key) BETWEEN 3 AND 320),
            village_name TEXT,
            block_name TEXT,
            district_name TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            enrichment_version TEXT NOT NULL CHECK (length(enrichment_version) BETWEEN 1 AND 32),
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, place_key),
            CHECK (village_name IS NOT NULL OR block_name IS NOT NULL OR district_name IS NOT NULL)
        );

        CREATE TABLE IF NOT EXISTS task_type_taxonomy (
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            task_type_key TEXT NOT NULL CHECK (length(task_type_key) BETWEEN 1 AND 160),
            task_kind TEXT NOT NULL CHECK (task_kind IN ('visit', 'registration', 'soil', 'query', 'team_work', 'other')),
            classification_state TEXT NOT NULL DEFAULT 'automatic' CHECK (classification_state IN ('automatic', 'reviewed')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            enrichment_version TEXT NOT NULL CHECK (length(enrichment_version) BETWEEN 1 AND 32),
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, task_type_key)
        );

        -- Private vocabulary registry.  New imports add source terms here,
        -- but never invoke a model.  A separate, deliberate maintenance pass
        -- may add reviewable semantic suggestions without replacing the raw
        -- source wording or making a diagnosis.
        CREATE TABLE IF NOT EXISTS operating_vocabulary_terms (
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            vocabulary_kind TEXT NOT NULL CHECK (vocabulary_kind IN ('task_type', 'reported_issue', 'crop_product')),
            source_context TEXT NOT NULL CHECK (length(source_context) BETWEEN 1 AND 160),
            raw_value TEXT NOT NULL CHECK (length(raw_value) BETWEEN 1 AND 600),
            raw_fingerprint TEXT NOT NULL CHECK (length(raw_fingerprint) = 64 AND raw_fingerprint = lower(raw_fingerprint)),
            occurrence_count INTEGER NOT NULL DEFAULT 0 CHECK (occurrence_count >= 0),
            normalized_key TEXT CHECK (normalized_key IS NULL OR normalized_key GLOB '[a-z0-9]*'),
            display_label TEXT CHECK (display_label IS NULL OR length(display_label) BETWEEN 1 AND 160),
            mapping_state TEXT NOT NULL DEFAULT 'pending' CHECK (mapping_state IN ('pending', 'suggested', 'reviewed', 'rejected', 'unmapped', 'automatic')),
            mapping_method TEXT NOT NULL DEFAULT 'deterministic' CHECK (mapping_method IN ('deterministic', 'ai', 'manual')),
            confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            classifier_model TEXT CHECK (classifier_model IS NULL OR length(classifier_model) BETWEEN 1 AND 120),
            mapping_version TEXT NOT NULL CHECK (length(mapping_version) BETWEEN 1 AND 32),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            classified_at TEXT,
            reviewed_at TEXT,
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, vocabulary_kind, source_context, raw_fingerprint)
        );

        -- Suggested Hindi labels and search aliases are a private companion to
        -- the vocabulary record.  They never replace the source term or become
        -- browser-visible until a manager reviews them.
        CREATE TABLE IF NOT EXISTS operating_vocabulary_localizations (
            source_id TEXT NOT NULL,
            vocabulary_kind TEXT NOT NULL,
            source_context TEXT NOT NULL,
            raw_fingerprint TEXT NOT NULL,
            locale_code TEXT NOT NULL CHECK (locale_code IN ('hi')),
            display_label TEXT,
            search_aliases_json TEXT NOT NULL DEFAULT '[]',
            mapping_state TEXT NOT NULL CHECK (mapping_state IN ('suggested', 'reviewed', 'rejected', 'unmapped')),
            mapping_method TEXT NOT NULL CHECK (mapping_method IN ('ai', 'manual')),
            confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            classifier_model TEXT CHECK (classifier_model IS NULL OR length(classifier_model) BETWEEN 1 AND 120),
            mapping_version TEXT NOT NULL CHECK (length(mapping_version) BETWEEN 1 AND 32),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            classified_at TEXT,
            reviewed_at TEXT,
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, vocabulary_kind, source_context, raw_fingerprint, locale_code),
            FOREIGN KEY (source_id, vocabulary_kind, source_context, raw_fingerprint)
                REFERENCES operating_vocabulary_terms(source_id, vocabulary_kind, source_context, raw_fingerprint),
            CHECK (
                (mapping_state IN ('suggested', 'reviewed') AND display_label IS NOT NULL)
                OR (mapping_state IN ('rejected', 'unmapped') AND display_label IS NULL)
            )
        );

        -- A manager reviews only the small deterministic candidates created
        -- when two issue values share the same proposed normalized key.
        CREATE TABLE IF NOT EXISTS operating_issue_group_proposals (
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            source_context TEXT NOT NULL CHECK (source_context IN ('reported_disease', 'reported_pest')),
            normalized_key TEXT NOT NULL CHECK (length(normalized_key) BETWEEN 1 AND 80),
            display_label TEXT NOT NULL CHECK (length(display_label) BETWEEN 1 AND 160),
            member_count INTEGER NOT NULL CHECK (member_count >= 2),
            occurrence_count INTEGER NOT NULL CHECK (occurrence_count >= 0),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            mapping_state TEXT NOT NULL CHECK (mapping_state IN ('suggested', 'reviewed', 'rejected')),
            mapping_method TEXT NOT NULL CHECK (mapping_method IN ('deterministic', 'manual')),
            mapping_version TEXT NOT NULL CHECK (length(mapping_version) BETWEEN 1 AND 32),
            reviewed_at TEXT,
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, source_context, normalized_key)
        );

        -- Localized place labels and aliases sit beside the immutable place
        -- catalogue.  They cannot redefine its village/block/district fields
        -- or make two reported places into one.
        CREATE TABLE IF NOT EXISTS place_localizations (
            source_id TEXT NOT NULL,
            place_key TEXT NOT NULL,
            locale_code TEXT NOT NULL CHECK (locale_code IN ('hi')),
            village_label TEXT,
            block_label TEXT,
            district_label TEXT,
            search_aliases_json TEXT NOT NULL DEFAULT '[]',
            mapping_state TEXT NOT NULL CHECK (mapping_state IN ('suggested', 'reviewed', 'rejected', 'unmapped')),
            mapping_method TEXT NOT NULL CHECK (mapping_method IN ('ai', 'manual')),
            confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            classifier_model TEXT CHECK (classifier_model IS NULL OR length(classifier_model) BETWEEN 1 AND 120),
            mapping_version TEXT NOT NULL CHECK (length(mapping_version) BETWEEN 1 AND 32),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            classified_at TEXT,
            reviewed_at TEXT,
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, place_key, locale_code),
            FOREIGN KEY (source_id, place_key) REFERENCES place_catalog(source_id, place_key),
            CHECK (
                (mapping_state IN ('suggested', 'reviewed')
                 AND (village_label IS NOT NULL OR block_label IS NOT NULL OR district_label IS NOT NULL))
                OR (mapping_state IN ('rejected', 'unmapped')
                    AND village_label IS NULL AND block_label IS NULL AND district_label IS NULL)
            )
        );

        -- A place-level read model for maps and directories.  It is derived
        -- from reported records only and does not turn a place into a Field.
        CREATE TABLE IF NOT EXISTS place_operating_summaries (
            source_id TEXT NOT NULL,
            place_key TEXT NOT NULL,
            reported_farm_count INTEGER NOT NULL DEFAULT 0 CHECK (reported_farm_count >= 0),
            farmer_count INTEGER NOT NULL DEFAULT 0 CHECK (farmer_count >= 0),
            field_worker_count INTEGER NOT NULL DEFAULT 0 CHECK (field_worker_count >= 0),
            open_task_count INTEGER NOT NULL DEFAULT 0 CHECK (open_task_count >= 0),
            visit_count INTEGER NOT NULL DEFAULT 0 CHECK (visit_count >= 0),
            issue_report_count INTEGER NOT NULL DEFAULT 0 CHECK (issue_report_count >= 0),
            location_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (location_evidence_count >= 0),
            photo_reference_count INTEGER NOT NULL DEFAULT 0 CHECK (photo_reference_count >= 0),
            latest_activity_at TEXT,
            enrichment_version TEXT NOT NULL CHECK (length(enrichment_version) BETWEEN 1 AND 32),
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (source_id, place_key),
            FOREIGN KEY (source_id, place_key) REFERENCES place_catalog(source_id, place_key)
        );

        CREATE TABLE IF NOT EXISTS trackwick_party_person_links (
            id TEXT PRIMARY KEY,
            party_id TEXT NOT NULL REFERENCES trackwick_parties(id),
            person_id TEXT NOT NULL REFERENCES people(id),
            link_status TEXT NOT NULL CHECK (link_status IN ('proposed', 'reviewed', 'rejected')),
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (party_id, person_id)
        );

        CREATE TABLE IF NOT EXISTS trackwick_plot_operating_links (
            id TEXT PRIMARY KEY,
            plot_id TEXT NOT NULL REFERENCES trackwick_registration_plots(id),
            land_parcel_id TEXT REFERENCES land_parcels(id),
            operational_block_id TEXT REFERENCES operational_blocks(id),
            link_status TEXT NOT NULL CHECK (link_status IN ('proposed', 'reviewed', 'rejected')),
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            CHECK (land_parcel_id IS NOT NULL OR operational_block_id IS NOT NULL),
            UNIQUE (plot_id, land_parcel_id, operational_block_id)
        );

        CREATE TABLE IF NOT EXISTS trackwick_task_allocation_links (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES trackwick_tasks(id),
            crop_allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            link_status TEXT NOT NULL CHECK (link_status IN ('proposed', 'reviewed', 'rejected')),
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (task_id, crop_allocation_id)
        );

        -- A reviewed Farm + Grower relationship can be established from a
        -- completed source registration before a precise Field/boundary exists.
        -- It never implies area, crop, land ownership, or right-to-operate.
        CREATE TABLE IF NOT EXISTS farm_grower_relationships (
            id TEXT PRIMARY KEY,
            farm_id TEXT NOT NULL REFERENCES farms(id),
            person_id TEXT NOT NULL REFERENCES people(id),
            starts_on TEXT NOT NULL,
            ends_on TEXT,
            status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
            provenance TEXT NOT NULL,
            reviewed_by_person_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL,
            CHECK ((status = 'active' AND ends_on IS NULL) OR (status = 'ended' AND ends_on IS NOT NULL))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_farm_growers_one_active
            ON farm_grower_relationships (farm_id, person_id) WHERE status = 'active';

        CREATE TABLE IF NOT EXISTS farm_candidate_review_cases (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            registration_id TEXT NOT NULL REFERENCES trackwick_registrations(id),
            candidate_fingerprint TEXT NOT NULL CHECK (
                length(candidate_fingerprint) = 64
                AND candidate_fingerprint = lower(candidate_fingerprint)
                AND candidate_fingerprint NOT GLOB '*[^0-9a-f]*'
            ),
            status TEXT NOT NULL CHECK (status IN ('open', 'accepting', 'held', 'accepted', 'rejected')),
            evidence_summary_json TEXT NOT NULL CHECK (
                json_valid(evidence_summary_json) AND json_type(evidence_summary_json) = 'object'
            ),
            review_reason TEXT,
            owner_person_id TEXT REFERENCES people(id),
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            accepted_farm_id TEXT REFERENCES farms(id),
            accepted_grower_person_id TEXT REFERENCES people(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (registration_id, candidate_fingerprint),
            CHECK (
                (status IN ('open', 'accepting') AND review_reason IS NULL AND owner_person_id IS NULL
                    AND reviewed_by_person_id IS NULL AND reviewed_at IS NULL
                    AND accepted_farm_id IS NULL AND accepted_grower_person_id IS NULL)
                OR (status = 'held' AND review_reason IS NOT NULL AND owner_person_id IS NOT NULL
                    AND reviewed_by_person_id IS NOT NULL AND reviewed_at IS NOT NULL
                    AND accepted_farm_id IS NULL AND accepted_grower_person_id IS NULL)
                OR (status = 'rejected' AND review_reason IS NOT NULL AND owner_person_id IS NULL
                    AND reviewed_by_person_id IS NOT NULL AND reviewed_at IS NOT NULL
                    AND accepted_farm_id IS NULL AND accepted_grower_person_id IS NULL)
                OR (status = 'accepted' AND review_reason IS NOT NULL AND owner_person_id IS NULL
                    AND reviewed_by_person_id IS NOT NULL AND reviewed_at IS NOT NULL
                    AND accepted_farm_id IS NOT NULL AND accepted_grower_person_id IS NOT NULL)
            )
        );
        CREATE TRIGGER IF NOT EXISTS farm_candidate_review_cases_valid_transition
        BEFORE UPDATE ON farm_candidate_review_cases
        WHEN NOT (
            (OLD.status = 'open' AND NEW.status IN ('open', 'accepting', 'held', 'rejected'))
            OR (OLD.status = 'accepting' AND NEW.status = 'accepted')
        )
        BEGIN SELECT RAISE(ABORT, 'invalid farm candidate review case transition'); END;
        CREATE TRIGGER IF NOT EXISTS farm_candidate_review_cases_source_immutable
        BEFORE UPDATE OF id, source_id, registration_id, candidate_fingerprint, created_at
        ON farm_candidate_review_cases
        BEGIN SELECT RAISE(ABORT, 'farm candidate review case source is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS farm_candidate_review_cases_no_delete
        BEFORE DELETE ON farm_candidate_review_cases
        BEGIN SELECT RAISE(ABORT, 'farm candidate review cases are append-only'); END;

        -- Private manager review state.  This relation records only a safe,
        -- server-generated evidence summary and durable source/canonical IDs;
        -- raw TrackWick contacts, locations, media, and provider identifiers
        -- remain in their typed source tables.
        CREATE TABLE IF NOT EXISTS farm_truth_review_cases (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source_registry(id),
            registration_id TEXT NOT NULL REFERENCES trackwick_registrations(id),
            plot_id TEXT NOT NULL REFERENCES trackwick_registration_plots(id),
            candidate_fingerprint TEXT NOT NULL CHECK (
                length(candidate_fingerprint) = 64
                AND candidate_fingerprint = lower(candidate_fingerprint)
                AND candidate_fingerprint NOT GLOB '*[^0-9a-f]*'
            ),
            status TEXT NOT NULL CHECK (status IN (
                'open', 'accepting', 'needs_evidence', 'accepted', 'rejected'
            )),
            evidence_summary_json TEXT NOT NULL CHECK (
                json_valid(evidence_summary_json) AND json_type(evidence_summary_json) = 'object'
            ),
            review_reason TEXT,
            missing_evidence_kind TEXT CHECK (missing_evidence_kind IS NULL OR missing_evidence_kind IN (
                'plot_area', 'crop_season', 'right_to_operate', 'farmer_identity',
                'field_worker_assignment'
            )),
            owner_person_id TEXT REFERENCES people(id),
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            accepted_land_parcel_id TEXT REFERENCES land_parcels(id),
            accepted_operational_block_id TEXT REFERENCES operational_blocks(id),
            accepted_crop_allocation_id TEXT REFERENCES crop_allocations(id),
            accepted_grower_person_id TEXT REFERENCES people(id),
            accepted_field_worker_person_id TEXT REFERENCES people(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (plot_id, candidate_fingerprint),
            CHECK (
                (status IN ('open', 'accepting')
                    AND review_reason IS NULL AND missing_evidence_kind IS NULL
                    AND owner_person_id IS NULL AND reviewed_by_person_id IS NULL
                    AND reviewed_at IS NULL AND accepted_land_parcel_id IS NULL
                    AND accepted_operational_block_id IS NULL
                    AND accepted_crop_allocation_id IS NULL
                    AND accepted_grower_person_id IS NULL
                    AND accepted_field_worker_person_id IS NULL)
                OR (status = 'needs_evidence'
                    AND review_reason IS NOT NULL AND missing_evidence_kind IS NOT NULL
                    AND owner_person_id IS NOT NULL AND reviewed_by_person_id IS NOT NULL
                    AND reviewed_at IS NOT NULL AND accepted_land_parcel_id IS NULL
                    AND accepted_operational_block_id IS NULL
                    AND accepted_crop_allocation_id IS NULL
                    AND accepted_grower_person_id IS NULL
                    AND accepted_field_worker_person_id IS NULL)
                OR (status = 'rejected'
                    AND review_reason IS NOT NULL AND missing_evidence_kind IS NULL
                    AND owner_person_id IS NULL AND reviewed_by_person_id IS NOT NULL
                    AND reviewed_at IS NOT NULL AND accepted_land_parcel_id IS NULL
                    AND accepted_operational_block_id IS NULL
                    AND accepted_crop_allocation_id IS NULL
                    AND accepted_grower_person_id IS NULL
                    AND accepted_field_worker_person_id IS NULL)
                OR (status = 'accepted'
                    AND review_reason IS NOT NULL AND missing_evidence_kind IS NULL
                    AND owner_person_id IS NULL AND reviewed_by_person_id IS NOT NULL
                    AND reviewed_at IS NOT NULL AND accepted_land_parcel_id IS NOT NULL
                    AND accepted_operational_block_id IS NOT NULL
                    AND accepted_crop_allocation_id IS NOT NULL
                    AND accepted_grower_person_id IS NOT NULL)
            )
        );

        CREATE TRIGGER IF NOT EXISTS farm_truth_review_cases_valid_transition
        BEFORE UPDATE ON farm_truth_review_cases
        WHEN NOT (
            (OLD.status = 'open' AND NEW.status IN (
                'accepting', 'needs_evidence', 'rejected'
            ))
            OR (OLD.status = 'accepting' AND NEW.status = 'accepted')
            OR (OLD.status = 'open' AND NEW.status = 'open'
                AND OLD.review_reason IS NEW.review_reason
                AND OLD.missing_evidence_kind IS NEW.missing_evidence_kind
                AND OLD.owner_person_id IS NEW.owner_person_id
                AND OLD.reviewed_by_person_id IS NEW.reviewed_by_person_id
                AND OLD.reviewed_at IS NEW.reviewed_at
                AND OLD.accepted_land_parcel_id IS NEW.accepted_land_parcel_id
                AND OLD.accepted_operational_block_id IS NEW.accepted_operational_block_id
                AND OLD.accepted_crop_allocation_id IS NEW.accepted_crop_allocation_id
                AND OLD.accepted_grower_person_id IS NEW.accepted_grower_person_id
                AND OLD.accepted_field_worker_person_id IS NEW.accepted_field_worker_person_id)
        )
        BEGIN
            SELECT RAISE(ABORT, 'invalid farm truth review case transition');
        END;

        CREATE TRIGGER IF NOT EXISTS farm_truth_review_cases_source_immutable
        BEFORE UPDATE OF id, source_id, registration_id, plot_id, candidate_fingerprint, created_at
        ON farm_truth_review_cases
        BEGIN
            SELECT RAISE(ABORT, 'farm truth review case source is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS farm_truth_review_cases_no_delete
        BEFORE DELETE ON farm_truth_review_cases
        BEGIN
            SELECT RAISE(ABORT, 'farm truth review cases are append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS trackwick_party_person_links_reviewed_update_guard
        BEFORE UPDATE ON trackwick_party_person_links
        WHEN OLD.link_status = 'reviewed'
        BEGIN
            SELECT RAISE(ABORT, 'reviewed TrackWick links are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trackwick_party_person_links_reviewed_delete_guard
        BEFORE DELETE ON trackwick_party_person_links
        WHEN OLD.link_status = 'reviewed'
        BEGIN
            SELECT RAISE(ABORT, 'reviewed TrackWick links are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trackwick_plot_operating_links_reviewed_update_guard
        BEFORE UPDATE ON trackwick_plot_operating_links
        WHEN OLD.link_status = 'reviewed'
        BEGIN
            SELECT RAISE(ABORT, 'reviewed TrackWick links are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trackwick_plot_operating_links_reviewed_delete_guard
        BEFORE DELETE ON trackwick_plot_operating_links
        WHEN OLD.link_status = 'reviewed'
        BEGIN
            SELECT RAISE(ABORT, 'reviewed TrackWick links are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trackwick_task_allocation_links_reviewed_update_guard
        BEFORE UPDATE ON trackwick_task_allocation_links
        WHEN OLD.link_status = 'reviewed'
        BEGIN
            SELECT RAISE(ABORT, 'reviewed TrackWick links are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trackwick_task_allocation_links_reviewed_delete_guard
        BEFORE DELETE ON trackwick_task_allocation_links
        WHEN OLD.link_status = 'reviewed'
        BEGIN
            SELECT RAISE(ABORT, 'reviewed TrackWick links are immutable');
        END;

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
        CREATE INDEX IF NOT EXISTS idx_operating_unit_locations_operating_unit
            ON operating_unit_locations (operating_unit_id, verified_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_operating_unit_locations_one_active
            ON operating_unit_locations (operating_unit_id) WHERE status = 'active';
        CREATE INDEX IF NOT EXISTS idx_soil_baselines_operating_unit_sampled
            ON soil_baselines (operating_unit_id, sampled_on, created_at);
        CREATE INDEX IF NOT EXISTS idx_crop_stage_checkpoints_allocation_planned
            ON crop_stage_checkpoints (allocation_id, planned_for);
        CREATE INDEX IF NOT EXISTS idx_field_information_requests_allocation_status_due
            ON field_information_requests (allocation_id, status, due_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_field_information_requests_target_status_due
            ON field_information_requests (target_person_id, status, due_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_field_information_requests_work_item
            ON field_information_requests (work_item_id);
        CREATE INDEX IF NOT EXISTS idx_field_information_requests_initiated_by_person
            ON field_information_requests (initiated_by_person_id);
        CREATE INDEX IF NOT EXISTS idx_field_information_request_events_request_created
            ON field_information_request_events (field_information_request_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_field_capture_passes_request_status_expiry
            ON field_capture_passes (field_information_request_id, status, expires_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_field_capture_candidates_request_status_created
            ON field_capture_candidates (field_information_request_id, status, created_at);
        CREATE INDEX IF NOT EXISTS idx_field_capture_candidates_allocation_created
            ON field_capture_candidates (allocation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_field_information_request_events_actor_person
            ON field_information_request_events (actor_person_id);
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
        CREATE INDEX IF NOT EXISTS idx_trackolap_records_source_status_feed
            ON trackolap_records (source_id, status, feed, source_updated_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_access_memberships_email
            ON access_memberships (lower(identity_email))
            WHERE identity_email IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_access_memberships_phone
            ON access_memberships (identity_phone)
            WHERE identity_phone IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_access_memberships_role_status
            ON access_memberships (access_role, identity_status);
        CREATE INDEX IF NOT EXISTS idx_password_identities_role_status
            ON password_identities (access_role, identity_status);
        CREATE INDEX IF NOT EXISTS idx_portal_memberships_portal_role_status
            ON portal_memberships (portal_id, portal_role, membership_status);
        CREATE INDEX IF NOT EXISTS idx_portal_memberships_identity
            ON portal_memberships (identity_id, membership_status)
            WHERE identity_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_trackwick_parties_source_kind
            ON trackwick_parties (source_id, party_kind, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_contacts_party
            ON trackwick_contact_points (party_id, contact_kind);
        CREATE INDEX IF NOT EXISTS idx_trackwick_tasks_farmer_created
            ON trackwick_tasks (farmer_party_id, provider_created_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_tasks_worker_created
            ON trackwick_tasks (field_worker_party_id, provider_created_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_tasks_open
            ON trackwick_tasks (source_id, provider_created_at)
            WHERE task_status IN ('pending', 'in_progress');
        CREATE INDEX IF NOT EXISTS idx_trackwick_visits_observed
            ON trackwick_visits (observed_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_findings_visit
            ON trackwick_visit_findings (visit_task_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_inputs_visit
            ON trackwick_crop_inputs (visit_task_id, occurred_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_registrations_farmer
            ON trackwick_registrations (farmer_party_id, registration_status);
        CREATE INDEX IF NOT EXISTS idx_trackwick_plots_registration
            ON trackwick_registration_plots (registration_id, ordinal);
        CREATE INDEX IF NOT EXISTS idx_trackwick_task_plot_links_plot
            ON trackwick_task_plot_links (plot_id, registration_id, data_quality_status);
        CREATE INDEX IF NOT EXISTS idx_trackwick_task_plot_links_task
            ON trackwick_task_plot_links (task_id, data_quality_status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trackwick_task_plot_links_one_plot_per_task
            ON trackwick_task_plot_links (task_id);
        CREATE INDEX IF NOT EXISTS idx_trackwick_media_task
            ON trackwick_media_references (task_id, provider_created_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_locations_source_time
            ON trackwick_location_observations (source_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_locations_task
            ON trackwick_location_observations (task_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_locations_party
            ON trackwick_location_observations (party_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_locations_coordinates
            ON trackwick_location_observations (latitude, longitude);
        CREATE INDEX IF NOT EXISTS idx_trackwick_worker_days_worker_date
            ON trackwick_worker_days (field_worker_party_id, observed_on);
        CREATE INDEX IF NOT EXISTS idx_entity_operating_snapshot_activity
            ON entity_operating_snapshots (source_id, entity_kind, latest_activity_at);
        CREATE INDEX IF NOT EXISTS idx_entity_operating_snapshot_open_work
            ON entity_operating_snapshots (source_id, entity_kind, open_task_count, latest_activity_at);
        CREATE INDEX IF NOT EXISTS idx_entity_operating_snapshot_crop
            ON entity_operating_snapshots (source_id, entity_kind, crop_profile, latest_activity_at);
        CREATE INDEX IF NOT EXISTS idx_place_catalog_hierarchy
            ON place_catalog (source_id, district_name, block_name, village_name);
        CREATE INDEX IF NOT EXISTS idx_task_type_taxonomy_kind
            ON task_type_taxonomy (source_id, task_kind, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_operating_vocabulary_pending
            ON operating_vocabulary_terms (source_id, vocabulary_kind, mapping_state, occurrence_count, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_operating_vocabulary_normalized
            ON operating_vocabulary_terms (source_id, vocabulary_kind, normalized_key)
            WHERE normalized_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_operating_vocabulary_localizations_state
            ON operating_vocabulary_localizations (source_id, locale_code, mapping_state);
        CREATE INDEX IF NOT EXISTS idx_operating_issue_group_proposals_state
            ON operating_issue_group_proposals (source_id, mapping_state, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_place_localizations_state
            ON place_localizations (source_id, locale_code, mapping_state);
        CREATE INDEX IF NOT EXISTS idx_place_operating_summaries_activity
            ON place_operating_summaries (source_id, latest_activity_at);
        CREATE INDEX IF NOT EXISTS idx_place_operating_summaries_open_work
            ON place_operating_summaries (source_id, open_task_count, latest_activity_at);
        CREATE INDEX IF NOT EXISTS idx_trackwick_party_links_person
            ON trackwick_party_person_links (person_id, link_status);
        CREATE INDEX IF NOT EXISTS idx_trackwick_plot_links_parcel
            ON trackwick_plot_operating_links (land_parcel_id, link_status);
        CREATE INDEX IF NOT EXISTS idx_trackwick_plot_links_block
            ON trackwick_plot_operating_links (operational_block_id, link_status);
        CREATE INDEX IF NOT EXISTS idx_trackwick_task_links_allocation
            ON trackwick_task_allocation_links (crop_allocation_id, link_status);
        CREATE INDEX IF NOT EXISTS idx_farm_truth_review_cases_status_updated
            ON farm_truth_review_cases (status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_farm_truth_review_cases_registration_plot
            ON farm_truth_review_cases (registration_id, plot_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trackwick_plot_links_one_reviewed
            ON trackwick_plot_operating_links (plot_id) WHERE link_status = 'reviewed';
        CREATE INDEX IF NOT EXISTS idx_trial_allocations_trial
            ON trial_allocations (trial_id);
        CREATE INDEX IF NOT EXISTS idx_trials_owner_created
            ON trials (owner_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_trial_confounders_trial
            ON trial_confounders (trial_id);
        CREATE INDEX IF NOT EXISTS idx_trial_conclusions_trial
            ON trial_conclusions (trial_id);
        CREATE INDEX IF NOT EXISTS idx_pilot_setup_acceptances_manager_created
            ON pilot_setup_acceptances (manager_person_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_person_operating_relationships_person_starts
            ON person_operating_relationships (person_id, starts_on, created_at);
        CREATE INDEX IF NOT EXISTS idx_person_operating_relationships_scope_starts
            ON person_operating_relationships (scope_type, operating_unit_id, land_parcel_id,
                operational_block_id, crop_allocation_id, starts_on, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_person_operating_relationships_active_operating_unit
            ON person_operating_relationships (person_id, operating_unit_id, role)
            WHERE status = 'active' AND scope_type = 'operating_unit';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_person_operating_relationships_active_land_parcel
            ON person_operating_relationships (person_id, land_parcel_id, role)
            WHERE status = 'active' AND scope_type = 'land_parcel';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_person_operating_relationships_active_operational_block
            ON person_operating_relationships (person_id, operational_block_id, role)
            WHERE status = 'active' AND scope_type = 'operational_block';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_person_operating_relationships_active_crop_allocation
            ON person_operating_relationships (person_id, crop_allocation_id, role)
            WHERE status = 'active' AND scope_type = 'crop_allocation';
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
                   SELECT id, trial_id, allocation_id, arm, status,
                          CASE WHEN status = 'eligible' THEN NULL ELSE enrolled_at END,
                          withdrawn_at, reason, created_at
                   FROM trial_allocations_legacy"""
            )
            conn.execute("DROP TABLE trial_allocations_legacy")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trial_allocations_trial ON trial_allocations (trial_id)"
            )
    conn.commit()
