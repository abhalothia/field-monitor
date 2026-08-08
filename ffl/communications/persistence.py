import json
import hashlib
import sqlite3
import uuid
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


COMMUNICATION_PURPOSES = frozenset({
    "work_prompt",
    "weekly_farmer_checkin",
    "field_evidence_request",
    "local_weather_observation",
    "problem_report",
    "callback_coordination",
    "safety_escalation",
    "operational_campaign",
})
COMMUNICATION_CHANNELS = frozenset({"whatsapp"})
COMMUNICATION_SCOPES = frozenset({
    "operating_unit", "land_parcel", "operational_block", "crop_allocation",
})
_SCOPE_RELATIONS = {
    "operating_unit": ("operating_units", "operating_unit_id"),
    "land_parcel": ("land_parcels", "land_parcel_id"),
    "operational_block": ("operational_blocks", "operational_block_id"),
    "crop_allocation": ("crop_allocations", "crop_allocation_id"),
}


def _identity() -> Tuple[str, str]:
    return str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def create_communications_schema(conn: sqlite3.Connection) -> None:
    _migrate_legacy_events(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS communication_endpoints (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL REFERENCES people(id),
            provider TEXT NOT NULL,
            address TEXT NOT NULL,
            locale TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
            created_at TEXT NOT NULL,
            UNIQUE(provider, address)
        );
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
        CREATE TABLE IF NOT EXISTS communication_consents (
            id TEXT PRIMARY KEY,
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            purpose TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
            granted_at TEXT NOT NULL,
            revoked_at TEXT,
            evidence TEXT NOT NULL,
            UNIQUE(endpoint_id, purpose)
        );
        CREATE TABLE IF NOT EXISTS communication_consent_events (
            id TEXT PRIMARY KEY,
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            purpose TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
            actor_id TEXT,
            provenance TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_templates (
            id TEXT PRIMARY KEY,
            template_key TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version > 0),
            locale TEXT NOT NULL,
            purpose TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'retired')),
            owner_id TEXT NOT NULL REFERENCES people(id),
            provider_template_id TEXT,
            provider_approval_state TEXT NOT NULL DEFAULT 'not_required',
            created_at TEXT NOT NULL,
            UNIQUE(template_key, version, locale)
        );
        CREATE TABLE IF NOT EXISTS communication_prompts (
            id TEXT PRIMARY KEY,
            work_item_id TEXT NOT NULL REFERENCES work_items(id),
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            template_id TEXT NOT NULL REFERENCES communication_templates(id),
            initiated_by_person_id TEXT NOT NULL REFERENCES people(id),
            idempotency_key TEXT NOT NULL UNIQUE,
            logical_action_key TEXT,
            provider_message_id TEXT UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'scheduled', 'delivered', 'failed', 'unknown', 'responded', 'no_response')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
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
        CREATE TABLE IF NOT EXISTS communication_outbox (
            id TEXT PRIMARY KEY,
            interaction_run_id TEXT NOT NULL UNIQUE REFERENCES communication_interaction_runs(id),
            legacy_prompt_id TEXT REFERENCES communication_prompts(id),
            provider_message_id TEXT UNIQUE,
            status TEXT NOT NULL CHECK (status IN (
                'pending', 'dispatching', 'dispatched', 'suppressed', 'failed', 'unknown'
            )),
            policy_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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
        CREATE TABLE IF NOT EXISTS communication_events (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            provider_event_id TEXT NOT NULL,
            provider_message_id TEXT,
            event_type TEXT NOT NULL,
            contact_fingerprint TEXT NOT NULL,
            endpoint_id TEXT REFERENCES communication_endpoints(id),
            envelope_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('received', 'processed', 'review_required', 'quarantined')),
            received_at TEXT NOT NULL,
            UNIQUE(provider, provider_event_id)
        );
        CREATE TABLE IF NOT EXISTS communication_attachments (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES communication_events(id),
            source_reference TEXT NOT NULL,
            media_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('unavailable', 'retained', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_evidence_links (
            attachment_id TEXT PRIMARY KEY REFERENCES communication_attachments(id),
            evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id),
            retained_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_candidates (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE REFERENCES communication_events(id),
            prompt_id TEXT REFERENCES communication_prompts(id),
            allocation_id TEXT REFERENCES crop_allocations(id),
            work_item_id TEXT REFERENCES work_items(id),
            endpoint_id TEXT REFERENCES communication_endpoints(id),
            kind TEXT NOT NULL CHECK (kind IN ('signal', 'exception')),
            status TEXT NOT NULL CHECK (status IN ('review', 'accepted', 'rejected')),
            draft_json TEXT NOT NULL,
            accepted_record_type TEXT,
            accepted_record_id TEXT,
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_communication_prompts_endpoint_status
            ON communication_prompts(endpoint_id, status);
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
        CREATE INDEX IF NOT EXISTS idx_communication_outbox_status
            ON communication_outbox(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_communication_workflow_versions_workflow_status
            ON communication_workflow_versions(workflow_id, status, version);
        CREATE INDEX IF NOT EXISTS idx_communication_workflow_runs_version_window
            ON communication_workflow_runs(workflow_version_id, weekly_window);
        CREATE INDEX IF NOT EXISTS idx_communication_events_contact ON communication_events(provider, contact_fingerprint);
        CREATE TABLE IF NOT EXISTS communication_deliveries (
            id TEXT PRIMARY KEY,
            prompt_id TEXT NOT NULL REFERENCES communication_prompts(id),
            attempt INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('attempting', 'accepted', 'unknown', 'failed')),
            provider_message_id TEXT,
            error_summary TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(prompt_id, attempt)
        );
        CREATE TABLE IF NOT EXISTS communication_schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_quarantines (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            reason TEXT NOT NULL,
            payload_fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_receipts (
            event_id TEXT PRIMARY KEY REFERENCES communication_events(id),
            ciphertext TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'processed', 'retryable', 'quarantined')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            claim_token TEXT,
            lease_expires_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_reconciliations (
            id TEXT PRIMARY KEY,
            prompt_id TEXT NOT NULL REFERENCES communication_prompts(id),
            provider_message_id TEXT,
            provider_status TEXT,
            provider_error_code INTEGER,
            outcome TEXT NOT NULL CHECK (outcome IN ('awaiting_webhook', 'reconciled', 'lookup_unavailable')),
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_communication_reconciliations_prompt
            ON communication_reconciliations(prompt_id, created_at);
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
        """
    )
    _add_column(conn, "communication_templates", "provider_template_id TEXT")
    _add_column(conn, "communication_templates", "provider_approval_state TEXT NOT NULL DEFAULT 'not_required'")
    _add_column(conn, "communication_prompts", "logical_action_key TEXT")
    _add_column(conn, "communication_attachments", "attempts INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "communication_attachments", "last_attempt_at TEXT")
    _add_column(conn, "communication_attachments", "last_error TEXT")
    _add_column(conn, "communication_receipts", "claim_token TEXT")
    _add_column(conn, "communication_receipts", "lease_expires_at TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_communication_prompts_logical_action ON communication_prompts(logical_action_key) WHERE logical_action_key IS NOT NULL")
    conn.execute("INSERT OR IGNORE INTO communication_schema_migrations VALUES (?, ?)", ("communications-v2-security", datetime.now(timezone.utc).isoformat()))
    conn.commit()


def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    column = definition.split()[0]
    columns = {row["name"] for row in conn.execute("PRAGMA table_info({0})".format(table))}
    if column not in columns:
        conn.execute("ALTER TABLE {0} ADD COLUMN {1}".format(table, definition))


def _migrate_legacy_events(conn: sqlite3.Connection) -> None:
    """Atomically replace the raw c5-preview event family with redacted v2 rows.

    The earliest preview used ``contact_address``, ``payload_json``, and public
    attachment URLs.  We cannot leave those columns in place, but must not lose
    the operational audit trail.  Child tables are rebuilt with their foreign
    keys pointing at the replacement parent before the legacy family is dropped.
    """
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "communication_events" not in tables:
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(communication_events)")}
    if "payload_json" not in columns:
        return
    conn.execute("""CREATE TABLE IF NOT EXISTS communication_quarantines (
        id TEXT PRIMARY KEY, provider TEXT NOT NULL, reason TEXT NOT NULL,
        payload_fingerprint TEXT NOT NULL, created_at TEXT NOT NULL)""")
    foreign_keys_enabled = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    # SQLite does not permit changing FK enforcement inside a transaction.
    # Nothing is acknowledged to a provider while app startup performs this
    # migration, and all subsequent DDL/data conversion is one transaction.
    conn.commit()
    if foreign_keys_enabled:
        conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        legacy_children = [
            table for table in ("communication_attachments", "communication_evidence_links", "communication_candidates", "communication_receipts")
            if table in tables
        ]
        for table in legacy_children:
            conn.execute("ALTER TABLE {0} RENAME TO {0}_legacy".format(table))
        conn.execute("ALTER TABLE communication_events RENAME TO communication_events_legacy")
        conn.execute("""CREATE TABLE communication_events (
            id TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_event_id TEXT NOT NULL,
            provider_message_id TEXT, event_type TEXT NOT NULL, contact_fingerprint TEXT NOT NULL,
            endpoint_id TEXT, envelope_json TEXT NOT NULL, status TEXT NOT NULL,
            received_at TEXT NOT NULL, UNIQUE(provider, provider_event_id))""")
        conn.execute("""CREATE TABLE communication_attachments (
            id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES communication_events(id),
            source_reference TEXT NOT NULL, media_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('unavailable', 'retained', 'failed')),
            created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE communication_evidence_links (
            attachment_id TEXT PRIMARY KEY REFERENCES communication_attachments(id),
            evidence_artifact_id TEXT NOT NULL REFERENCES evidence_artifacts(id), retained_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE communication_candidates (
            id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE REFERENCES communication_events(id),
            prompt_id TEXT REFERENCES communication_prompts(id), allocation_id TEXT REFERENCES crop_allocations(id),
            work_item_id TEXT REFERENCES work_items(id), endpoint_id TEXT REFERENCES communication_endpoints(id),
            kind TEXT NOT NULL CHECK (kind IN ('signal', 'exception')),
            status TEXT NOT NULL CHECK (status IN ('review', 'accepted', 'rejected')),
            draft_json TEXT NOT NULL, accepted_record_type TEXT, accepted_record_id TEXT,
            reviewed_by_person_id TEXT REFERENCES people(id), reviewed_at TEXT, created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE communication_receipts (
            event_id TEXT PRIMARY KEY REFERENCES communication_events(id), ciphertext TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'processed', 'retryable', 'quarantined')),
            attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, updated_at TEXT NOT NULL)""")
        rows = conn.execute("SELECT * FROM communication_events_legacy").fetchall()
        for row in rows:
            contact = row["contact_address"] if "contact_address" in columns else ""
            fingerprint = hashlib.sha256((row["provider"] + ":" + contact).encode("utf-8")).hexdigest()
            envelope = _json({"migrated_from": "c5", "payload_redacted": True})
            prior_status = row["status"]
            converted_status = prior_status if prior_status in ("processed", "review_required", "quarantined") else "quarantined"
            conn.execute("INSERT INTO communication_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (row["id"], row["provider"], row["provider_event_id"], row["provider_message_id"], row["event_type"], fingerprint, row["endpoint_id"], envelope, converted_status, row["received_at"]))
            if prior_status == "received":
                identifier, created = _identity()
                conn.execute("INSERT INTO communication_quarantines VALUES (?, ?, ?, ?, ?)", (identifier, row["provider"], "legacy raw receipt requires re-ingestion", hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest(), created))
        if "communication_attachments" in legacy_children:
            attachment_columns = {row["name"] for row in conn.execute("PRAGMA table_info(communication_attachments_legacy)")}
            for row in conn.execute("SELECT * FROM communication_attachments_legacy").fetchall():
                raw_reference = row["source_reference"] if "source_reference" in attachment_columns else row["source_url"]
                reference = hashlib.sha256((row["event_id"] + ":" + raw_reference).encode("utf-8")).hexdigest()
                prior_status = row["status"]
                converted_status = "retained" if prior_status == "retained" else "failed" if prior_status == "failed" else "unavailable"
                conn.execute("INSERT INTO communication_attachments VALUES (?, ?, ?, ?, ?, ?)", (row["id"], row["event_id"], reference, row["media_type"], converted_status, row["created_at"]))
        if "communication_candidates" in legacy_children:
            for row in conn.execute("SELECT * FROM communication_candidates_legacy").fetchall():
                # Candidate text can have been copied from payload_json.  Keep its
                # review/audit identity but force a new reviewed submission.
                draft = _json({"migrated_from": "c5", "content_redacted": True, "requires_reingestion": True, "attachment_ids": []})
                conn.execute("""INSERT INTO communication_candidates
                    (id, event_id, prompt_id, allocation_id, work_item_id, endpoint_id, kind, status,
                     draft_json, accepted_record_type, accepted_record_id, reviewed_by_person_id, reviewed_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                    row["id"], row["event_id"], row["prompt_id"], row["allocation_id"], row["work_item_id"],
                    row["endpoint_id"], row["kind"], row["status"], draft, row["accepted_record_type"],
                    row["accepted_record_id"], row["reviewed_by_person_id"], row["reviewed_at"], row["created_at"],
                ))
        if "communication_evidence_links" in legacy_children:
            for row in conn.execute("SELECT * FROM communication_evidence_links_legacy").fetchall():
                conn.execute("INSERT INTO communication_evidence_links VALUES (?, ?, ?)", (row["attachment_id"], row["evidence_artifact_id"], row["retained_at"]))
        if "communication_receipts" in legacy_children:
            for row in conn.execute("SELECT * FROM communication_receipts_legacy").fetchall():
                identifier, created = _identity()
                conn.execute("INSERT INTO communication_receipts VALUES (?, ?, 'quarantined', ?, ?, ?)", (row["event_id"], row["ciphertext"], row["attempts"], "legacy receipt requires re-ingestion", row["updated_at"]))
                conn.execute("INSERT INTO communication_quarantines VALUES (?, ?, ?, ?, ?)", (identifier, "loopmessage", "legacy receipt requires re-ingestion", hashlib.sha256(row["ciphertext"].encode("utf-8")).hexdigest(), created))
        for table in legacy_children:
            conn.execute("DROP TABLE {0}_legacy".format(table))
        conn.execute("DROP TABLE communication_events_legacy")
        # SQLite keeps an index name when its table is renamed.  Recreate the
        # current-table index explicitly rather than letting IF NOT EXISTS mask
        # an index that is about to be dropped with the legacy table.
        conn.execute("DROP INDEX IF EXISTS idx_communication_events_contact")
        conn.execute("CREATE INDEX idx_communication_events_contact ON communication_events(provider, contact_fingerprint)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if foreign_keys_enabled:
            conn.execute("PRAGMA foreign_keys = ON")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError("communication migration left foreign-key violations")


def _normalize_e164(address: str) -> str:
    normalized = re.sub(r"[\s\-()]+", "", address)
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized):
        raise ValueError("communication endpoint must be E.164")
    return normalized


def create_endpoint(conn: sqlite3.Connection, person_id: str, provider: str, address: str, locale: str) -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone() is None:
        raise ValueError("endpoint person does not exist")
    address = _normalize_e164(address)
    existing = conn.execute("SELECT * FROM communication_endpoints WHERE provider = ? AND address = ?", (provider, address)).fetchone()
    if existing is not None:
        return dict(existing)
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_endpoints VALUES (?, ?, ?, ?, ?, 'active', ?)", (identifier, person_id, provider, address, locale, created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_endpoints WHERE id = ?", (identifier,)).fetchone())


def create_communication_profile(
    conn: sqlite3.Connection, portal_id: str, person_id: str, locale: str, time_zone: str,
) -> Dict[str, Any]:
    """Create an explicit portal/person communications identity.

    The caller supplies both canonical identifiers. Contact data is never used
    to infer the person or their portal role.
    """
    membership = conn.execute(
        """SELECT portal.status AS portal_status, membership.membership_status
           FROM customer_portals portal
           JOIN portal_memberships membership ON membership.portal_id = portal.id
           WHERE portal.id = ? AND membership.person_id = ?""",
        (portal_id, person_id),
    ).fetchone()
    if membership is None:
        raise ValueError("communication profile requires an explicit portal membership")
    if membership["portal_status"] != "active" or membership["membership_status"] != "active":
        raise ValueError("communication profile requires an active portal membership")
    if not locale or len(locale) > 35:
        raise ValueError("communication profile locale is invalid")
    try:
        ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("communication profile time zone is invalid") from None

    existing = conn.execute(
        "SELECT * FROM communication_profiles WHERE portal_id = ? AND person_id = ?",
        (portal_id, person_id),
    ).fetchone()
    if existing is not None:
        return dict(existing)
    identifier, created_at = _identity()
    conn.execute(
        """INSERT INTO communication_profiles
           (id, portal_id, person_id, status, locale, time_zone, created_at)
           VALUES (?, ?, ?, 'active', ?, ?, ?)""",
        (identifier, portal_id, person_id, locale, time_zone, created_at),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM communication_profiles WHERE id = ?", (identifier,),
    ).fetchone())


def verify_endpoint(
    conn: sqlite3.Connection, profile_id: str, provider: str, address: str,
    verification_method: str, verified_by_person_id: str,
) -> Dict[str, Any]:
    """Bind a provider endpoint to one explicit profile person."""
    profile = conn.execute(
        "SELECT * FROM communication_profiles WHERE id = ? AND status = 'active'",
        (profile_id,),
    ).fetchone()
    if profile is None:
        raise ValueError("active communication profile does not exist")
    if conn.execute(
        "SELECT 1 FROM people WHERE id = ?", (verified_by_person_id,),
    ).fetchone() is None:
        raise ValueError("endpoint verifier does not exist")
    if not verification_method or len(verification_method) > 80:
        raise ValueError("endpoint verification method is invalid")

    normalized_address = _normalize_e164(address)
    endpoint = conn.execute(
        "SELECT * FROM communication_endpoints WHERE provider = ? AND address = ?",
        (provider, normalized_address),
    ).fetchone()
    if endpoint is None:
        endpoint = create_endpoint(
            conn, profile["person_id"], provider, normalized_address, profile["locale"],
        )
    else:
        endpoint = dict(endpoint)
        if endpoint["person_id"] != profile["person_id"]:
            raise ValueError("endpoint person does not match communication profile person")
        if endpoint["status"] != "active":
            raise ValueError("communication endpoint is not active")

    existing = conn.execute(
        """SELECT 1 FROM communication_endpoint_verifications
           WHERE profile_id = ? AND endpoint_id = ? AND status = 'active'""",
        (profile_id, endpoint["id"]),
    ).fetchone()
    if existing is None:
        identifier, verified_at = _identity()
        conn.execute(
            """INSERT INTO communication_endpoint_verifications
               (id, profile_id, endpoint_id, verification_method, verified_by_person_id,
                verified_at, status, revoked_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', NULL)""",
            (
                identifier, profile_id, endpoint["id"], verification_method,
                verified_by_person_id, verified_at,
            ),
        )
        conn.commit()
    return endpoint


def _active_profile_scope(
    conn: sqlite3.Connection, profile: sqlite3.Row, scope_type: str, scope_id: str,
) -> sqlite3.Row:
    relation, relationship_column = _SCOPE_RELATIONS[scope_type]
    if conn.execute(
        "SELECT 1 FROM {0} WHERE id = ?".format(relation), (scope_id,),
    ).fetchone() is None:
        raise ValueError("communication scope record does not exist")
    relationship = conn.execute(
        """SELECT * FROM person_operating_relationships
           WHERE person_id = ? AND scope_type = ? AND {0} = ? AND status = 'active'""".format(
            relationship_column
        ),
        (profile["person_id"], scope_type, scope_id),
    ).fetchone()
    if relationship is None:
        raise ValueError("communication profile has no active relationship for scope")
    return relationship


def set_scoped_consent(
    conn: sqlite3.Connection, profile_id: str, endpoint_id: str, purpose: str,
    scope_type: str, scope_id: str, active: bool, evidence: str,
    actor_person_id: str, channel: str = "whatsapp",
) -> Dict[str, Any]:
    """Append a scoped consent transition while retaining capture evidence."""
    if purpose not in COMMUNICATION_PURPOSES:
        raise ValueError("unknown communication purpose")
    if scope_type not in COMMUNICATION_SCOPES:
        raise ValueError("unknown communication scope")
    if channel not in COMMUNICATION_CHANNELS:
        raise ValueError("unknown communication channel")
    if not scope_id:
        raise ValueError("communication scope id is required")
    if not evidence or not evidence.strip():
        raise ValueError("communication consent evidence is required")
    if conn.execute(
        "SELECT 1 FROM people WHERE id = ?", (actor_person_id,),
    ).fetchone() is None:
        raise ValueError("communication consent actor does not exist")

    profile = conn.execute(
        "SELECT * FROM communication_profiles WHERE id = ? AND status = 'active'",
        (profile_id,),
    ).fetchone()
    if profile is None:
        raise ValueError("active communication profile does not exist")
    endpoint = conn.execute(
        "SELECT * FROM communication_endpoints WHERE id = ? AND status = 'active'",
        (endpoint_id,),
    ).fetchone()
    if endpoint is None:
        raise ValueError("active communication endpoint does not exist")
    if endpoint["person_id"] != profile["person_id"]:
        raise ValueError("endpoint person does not match communication profile person")
    if conn.execute(
        """SELECT 1 FROM communication_endpoint_verifications
           WHERE profile_id = ? AND endpoint_id = ? AND status = 'active'""",
        (profile_id, endpoint_id),
    ).fetchone() is None:
        raise ValueError("communication endpoint is not verified for profile")
    relationship = _active_profile_scope(conn, profile, scope_type, scope_id)

    now = datetime.now(timezone.utc).isoformat()
    status = "active" if active else "revoked"
    try:
        scope = conn.execute(
            """SELECT * FROM communication_endpoint_scopes
               WHERE profile_id = ? AND relationship_id = ? AND scope_type = ? AND scope_id = ?""",
            (profile_id, relationship["id"], scope_type, scope_id),
        ).fetchone()
        if scope is None:
            scope_identifier, _ = _identity()
            conn.execute(
                """INSERT INTO communication_endpoint_scopes
                   (id, profile_id, relationship_id, scope_type, scope_id, starts_on, ends_on, status)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, 'active')""",
                (
                    scope_identifier, profile_id, relationship["id"], scope_type,
                    scope_id, relationship["starts_on"],
                ),
            )

        consent = conn.execute(
            """SELECT * FROM communication_scoped_consents
               WHERE endpoint_id = ? AND purpose = ? AND scope_type = ?
                 AND scope_id = ? AND channel = ?""",
            (endpoint_id, purpose, scope_type, scope_id, channel),
        ).fetchone()
        if consent is None:
            if not active:
                raise ValueError("cannot revoke scoped consent before grant")
            consent_id, granted_at = _identity()
            conn.execute(
                """INSERT INTO communication_scoped_consents
                   (id, profile_id, endpoint_id, purpose, scope_type, scope_id, channel,
                    status, evidence, granted_at, revoked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    consent_id, profile_id, endpoint_id, purpose, scope_type, scope_id,
                    channel, status, evidence, granted_at, None if active else now,
                ),
            )
        else:
            if consent["profile_id"] != profile_id:
                raise ValueError("scoped consent belongs to another communication profile")
            consent_id = consent["id"]
            conn.execute(
                """UPDATE communication_scoped_consents
                   SET status = ?, revoked_at = ? WHERE id = ?""",
                (status, None if active else now, consent_id),
            )

        event_id, created_at = _identity()
        conn.execute(
            """INSERT INTO communication_scoped_consent_events
               (id, consent_id, profile_id, endpoint_id, purpose, scope_type, scope_id,
                channel, status, evidence, actor_person_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, consent_id, profile_id, endpoint_id, purpose, scope_type,
                scope_id, channel, status, evidence, actor_person_id, created_at,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return dict(conn.execute(
        "SELECT * FROM communication_scoped_consents WHERE id = ?", (consent_id,),
    ).fetchone())


def has_scoped_consent(
    conn: sqlite3.Connection, profile_id: str, endpoint_id: str, purpose: str,
    scope_type: str, scope_id: str, channel: str = "whatsapp",
) -> bool:
    """Return consent only through its active tenant authority chain."""
    if purpose not in COMMUNICATION_PURPOSES or scope_type not in COMMUNICATION_SCOPES:
        return False
    if channel not in COMMUNICATION_CHANNELS:
        return False
    _relation, relationship_column = _SCOPE_RELATIONS[scope_type]
    return conn.execute(
        """SELECT 1
           FROM communication_scoped_consents consent
           JOIN communication_profiles profile
             ON profile.id = consent.profile_id AND profile.status = 'active'
           JOIN customer_portals portal
             ON portal.id = profile.portal_id AND portal.status = 'active'
           JOIN portal_memberships membership
             ON membership.portal_id = profile.portal_id
            AND membership.person_id = profile.person_id
            AND membership.membership_status = 'active'
           JOIN communication_endpoints endpoint
             ON endpoint.id = consent.endpoint_id
            AND endpoint.person_id = profile.person_id
            AND endpoint.status = 'active'
           JOIN communication_endpoint_verifications verification
             ON verification.profile_id = profile.id
            AND verification.endpoint_id = endpoint.id
            AND verification.status = 'active'
           JOIN communication_endpoint_scopes scope
             ON scope.profile_id = profile.id
            AND scope.scope_type = consent.scope_type
            AND scope.scope_id = consent.scope_id
            AND scope.status = 'active'
           JOIN person_operating_relationships relationship
             ON relationship.id = scope.relationship_id
            AND relationship.person_id = profile.person_id
            AND relationship.scope_type = scope.scope_type
            AND relationship.{0} = scope.scope_id
            AND relationship.status = 'active'
           WHERE consent.profile_id = ? AND consent.endpoint_id = ?
             AND consent.purpose = ? AND consent.scope_type = ? AND consent.scope_id = ?
             AND consent.channel = ? AND consent.status = 'active'""".format(
            relationship_column
        ),
        (profile_id, endpoint_id, purpose, scope_type, scope_id, channel),
    ).fetchone() is not None


def profile_for_endpoint(
    conn: sqlite3.Connection, provider: str, address: str, portal_id: str,
) -> Optional[Dict[str, Any]]:
    normalized_address = _normalize_e164(address)
    row = conn.execute(
        """SELECT profile.*
           FROM communication_profiles profile
           JOIN communication_endpoint_verifications verification
             ON verification.profile_id = profile.id AND verification.status = 'active'
           JOIN communication_endpoints endpoint
             ON endpoint.id = verification.endpoint_id AND endpoint.status = 'active'
           WHERE endpoint.provider = ? AND endpoint.address = ?
             AND profile.portal_id = ? AND profile.status = 'active'""",
        (provider, normalized_address, portal_id),
    ).fetchone()
    return dict(row) if row is not None else None


def set_consent(conn: sqlite3.Connection, endpoint_id: str, purpose: str, active: bool, evidence: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM communication_endpoints WHERE id = ?", (endpoint_id,)).fetchone() is None:
        raise ValueError("communication endpoint does not exist")
    row = conn.execute("SELECT * FROM communication_consents WHERE endpoint_id = ? AND purpose = ?", (endpoint_id, purpose)).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    if actor_id is not None and conn.execute("SELECT 1 FROM people WHERE id = ?", (actor_id,)).fetchone() is None:
        raise ValueError("consent actor does not exist")
    if row is None:
        identifier, _ = _identity()
        conn.execute("INSERT INTO communication_consents VALUES (?, ?, ?, ?, ?, ?, ?)", (identifier, endpoint_id, purpose, 'active' if active else 'revoked', now, None if active else now, evidence))
    else:
        conn.execute("UPDATE communication_consents SET status = ?, granted_at = ?, revoked_at = ?, evidence = ? WHERE id = ?", ('active' if active else 'revoked', now if active else row['granted_at'], None if active else now, evidence, row['id']))
    conn.commit()
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_consent_events VALUES (?, ?, ?, ?, ?, ?, ?)", (identifier, endpoint_id, purpose, 'active' if active else 'revoked', actor_id, evidence, created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_consents WHERE endpoint_id = ? AND purpose = ?", (endpoint_id, purpose)).fetchone())


def has_active_consent(conn: sqlite3.Connection, endpoint_id: str, purpose: str) -> bool:
    return conn.execute("SELECT 1 FROM communication_consents WHERE endpoint_id = ? AND purpose = ? AND status = 'active'", (endpoint_id, purpose)).fetchone() is not None


def create_template(conn: sqlite3.Connection, template_key: str, version: int, locale: str, purpose: str, body: str, owner_id: str, provider_template_id: Optional[str] = None, provider_approval_state: str = "not_required", status: str = 'draft') -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("template owner does not exist")
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_templates (id, template_key, version, locale, purpose, body, status, owner_id, provider_template_id, provider_approval_state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (identifier, template_key, version, locale, purpose, body, status, owner_id, provider_template_id, provider_approval_state, created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_templates WHERE id = ?", (identifier,)).fetchone())


def publish_template(conn: sqlite3.Connection, template_id: str, publisher_id: str) -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (publisher_id,)).fetchone() is None:
        raise ValueError("template publisher does not exist")
    row = conn.execute("SELECT * FROM communication_templates WHERE id = ?", (template_id,)).fetchone()
    if row is None or row["status"] != "draft":
        raise ValueError("draft communication template not found")
    conn.execute("UPDATE communication_templates SET status = 'published' WHERE id = ?", (template_id,))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_templates WHERE id = ?", (template_id,)).fetchone())


def create_prompt(conn: sqlite3.Connection, work_item_id: str, allocation_id: str, endpoint_id: str, template_id: str, initiated_by: str, idempotency_key: str) -> Tuple[Dict[str, Any], bool]:
    existing = conn.execute("SELECT * FROM communication_prompts WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
    if existing is not None:
        return dict(existing), False
    logical_action_key = "work_prompt:{0}:{1}:{2}".format(work_item_id, endpoint_id, template_id)
    logical = conn.execute("SELECT * FROM communication_prompts WHERE logical_action_key = ?", (logical_action_key,)).fetchone()
    if logical is not None:
        return dict(logical), False
    identifier, now = _identity()
    conn.execute("INSERT INTO communication_prompts (id, work_item_id, allocation_id, endpoint_id, template_id, initiated_by_person_id, idempotency_key, logical_action_key, provider_message_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?, ?)", (identifier, work_item_id, allocation_id, endpoint_id, template_id, initiated_by, idempotency_key, logical_action_key, now, now))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_prompts WHERE id = ?", (identifier,)).fetchone()), True


def update_prompt(conn: sqlite3.Connection, prompt_id: str, status: str, provider_message_id: Optional[str] = None) -> Dict[str, Any]:
    row = conn.execute("SELECT status FROM communication_prompts WHERE id = ?", (prompt_id,)).fetchone()
    allowed = {
        "pending": {"accepted", "scheduled", "delivered", "failed", "unknown"},
        "accepted": {"scheduled", "delivered", "failed", "unknown", "responded", "no_response"},
        "scheduled": {"delivered", "failed", "unknown", "responded", "no_response"},
        "delivered": {"failed", "unknown", "responded", "no_response"},
        # Unknown means an API response was interrupted or the provider could
        # not currently identify the message; a later webhook/status lookup can
        # safely resolve it without sending another message.
        "unknown": {"accepted", "scheduled", "delivered", "failed", "responded", "no_response"},
    }
    if row is None or status not in allowed.get(row["status"], set()):
        raise ValueError("invalid communication prompt transition")
    now = datetime.now(timezone.utc).isoformat()
    if provider_message_id is None:
        conn.execute("UPDATE communication_prompts SET status = ?, updated_at = ? WHERE id = ?", (status, now, prompt_id))
    else:
        conn.execute("UPDATE communication_prompts SET status = ?, provider_message_id = ?, updated_at = ? WHERE id = ?", (status, provider_message_id, now, prompt_id))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_prompts WHERE id = ?", (prompt_id,)).fetchone())


def create_delivery_attempt(conn: sqlite3.Connection, prompt_id: str, status: str, provider_message_id: Optional[str] = None, error_summary: Optional[str] = None) -> None:
    attempt = conn.execute("SELECT count(*) FROM communication_deliveries WHERE prompt_id = ?", (prompt_id,)).fetchone()[0] + 1
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_deliveries VALUES (?, ?, ?, ?, ?, ?, ?)", (identifier, prompt_id, attempt, status, provider_message_id, error_summary, created_at))
    conn.commit()


def create_reconciliation(
    conn: sqlite3.Connection, prompt_id: str, outcome: str, provider_message_id: Optional[str] = None,
    provider_status: Optional[str] = None, provider_error_code: Optional[int] = None,
) -> None:
    latest = conn.execute(
        "SELECT provider_message_id, provider_status, provider_error_code, outcome FROM communication_reconciliations "
        "WHERE prompt_id = ? ORDER BY created_at DESC LIMIT 1",
        (prompt_id,),
    ).fetchone()
    if latest is not None and (
        latest["provider_message_id"], latest["provider_status"], latest["provider_error_code"], latest["outcome"]
    ) == (provider_message_id, provider_status, provider_error_code, outcome):
        return
    identifier, created_at = _identity()
    conn.execute(
        "INSERT INTO communication_reconciliations VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identifier, prompt_id, provider_message_id, provider_status, provider_error_code, outcome, created_at),
    )
    conn.commit()


def prompts_requiring_reconciliation(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT prompt.*, (
                SELECT delivery.status FROM communication_deliveries delivery
                WHERE delivery.prompt_id = prompt.id ORDER BY delivery.attempt DESC LIMIT 1
            ) AS latest_delivery_status
            FROM communication_prompts prompt
            WHERE prompt.status = 'unknown'
               OR (prompt.status = 'pending' AND EXISTS (
                   SELECT 1 FROM communication_deliveries delivery
                   WHERE delivery.prompt_id = prompt.id AND delivery.status = 'attempting'
               ))
            ORDER BY prompt.updated_at"""
    ).fetchall()
    return [dict(row) for row in rows]


def has_unknown_delivery_attempt(conn: sqlite3.Connection, prompt_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM communication_deliveries WHERE prompt_id = ? AND status = 'unknown'", (prompt_id,)
    ).fetchone() is not None


def create_outbox_entry(
    conn: sqlite3.Connection, interaction_run_id: str, legacy_prompt_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    """Durably reserve one logical interaction before any provider call.

    The outbox deliberately contains correlation IDs and lifecycle state only.
    Contacts, provider request bodies, template parameters, and raw context
    tokens are assembled transiently at dispatch time and are never retained
    here.
    """
    existing = conn.execute(
        "SELECT * FROM communication_outbox WHERE interaction_run_id = ?", (interaction_run_id,),
    ).fetchone()
    if existing is not None:
        return dict(existing), False
    identifier, now = _identity()
    conn.execute(
        """INSERT INTO communication_outbox
           (id, interaction_run_id, legacy_prompt_id, provider_message_id, status, policy_code, created_at, updated_at)
           VALUES (?, ?, ?, NULL, 'pending', NULL, ?, ?)""",
        (identifier, interaction_run_id, legacy_prompt_id, now, now),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM communication_outbox WHERE id = ?", (identifier,),
    ).fetchone()), True


def outbox_entry(conn: sqlite3.Connection, interaction_run_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM communication_outbox WHERE interaction_run_id = ?", (interaction_run_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def update_outbox_entry(
    conn: sqlite3.Connection,
    interaction_run_id: str,
    status: str,
    *,
    provider_message_id: Optional[str] = None,
    policy_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Advance an outbox entry without allowing a second send lifecycle."""
    row = conn.execute(
        "SELECT * FROM communication_outbox WHERE interaction_run_id = ?", (interaction_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError("communication outbox entry does not exist")
    allowed = {
        "pending": {"dispatching", "suppressed"},
        "dispatching": {"dispatched", "failed", "unknown", "suppressed"},
        "unknown": {"dispatched", "failed"},
        "dispatched": {"dispatched"},
        "failed": {"failed"},
        "suppressed": {"suppressed"},
    }
    if status not in allowed.get(row["status"], set()):
        raise ValueError("invalid communication outbox transition")
    if provider_message_id is not None and row["provider_message_id"] not in (None, provider_message_id):
        raise ValueError("outbox interaction is already bound to another provider message")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE communication_outbox
           SET status = ?, provider_message_id = COALESCE(?, provider_message_id),
               policy_code = COALESCE(?, policy_code), updated_at = ?
           WHERE interaction_run_id = ?""",
        (status, provider_message_id, policy_code, now, interaction_run_id),
    )
    conn.commit()
    updated = outbox_entry(conn, interaction_run_id)
    if updated is None:
        raise RuntimeError("communication outbox entry disappeared")
    return updated


def outbox_requiring_reconciliation(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM communication_outbox
           WHERE status IN ('dispatching', 'unknown')
           ORDER BY updated_at""",
    ).fetchall()
    return [dict(row) for row in rows]


def workflow_dispatch_count(
    conn: sqlite3.Connection, profile_id: str, workflow_version_id: str, weekly_window: str,
) -> int:
    row = conn.execute(
        """SELECT COUNT(*) AS count
           FROM communication_outbox outbox
           JOIN communication_interaction_runs interaction
             ON interaction.id = outbox.interaction_run_id
           JOIN communication_workflow_runs run
             ON run.interaction_run_id = interaction.id
           WHERE run.profile_id = ? AND run.workflow_version_id = ? AND run.weekly_window = ?
             AND outbox.status = 'dispatched'""",
        (profile_id, workflow_version_id, weekly_window),
    ).fetchone()
    return int(row["count"])


def quarantine(conn: sqlite3.Connection, provider: str, reason: str, payload: bytes) -> None:
    identifier, created_at = _identity()
    fingerprint = hashlib.sha256(payload).hexdigest()
    conn.execute("INSERT INTO communication_quarantines VALUES (?, ?, ?, ?, ?)", (identifier, provider, reason[:200], fingerprint, created_at))
    conn.commit()


def pending_receipts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    return [dict(row) for row in conn.execute("SELECT * FROM communication_receipts WHERE status IN ('queued', 'retryable') ORDER BY updated_at").fetchall()]


def release_expired_receipt_claims(conn: sqlite3.Connection, now: str) -> None:
    """Make work from a crashed worker recoverable after its bounded lease."""
    conn.execute(
        "UPDATE communication_receipts SET status = 'retryable', claim_token = NULL, lease_expires_at = NULL, "
        "last_error = 'processing lease expired', updated_at = ? "
        "WHERE status = 'processing' AND (lease_expires_at IS NULL OR lease_expires_at <= ?)",
        (now, now),
    )
    conn.commit()


def claim_receipt(conn: sqlite3.Connection, event_id: str, lease_expires_at: str) -> Optional[str]:
    """Atomically claim a queued receipt so concurrent workers cannot replay it."""
    token = str(uuid.uuid4())
    cursor = conn.execute(
        "UPDATE communication_receipts SET status = 'processing', attempts = attempts + 1, last_error = NULL, "
        "claim_token = ?, lease_expires_at = ?, updated_at = ? "
        "WHERE event_id = ? AND status IN ('queued', 'retryable')",
        (token, lease_expires_at, datetime.now(timezone.utc).isoformat(), event_id),
    )
    conn.commit()
    return token if cursor.rowcount == 1 else None


def complete_receipt(conn: sqlite3.Connection, event_id: str, claim_token: str) -> bool:
    cursor = conn.execute(
        "UPDATE communication_receipts SET status = 'processed', last_error = NULL, claim_token = NULL, lease_expires_at = NULL, updated_at = ? "
        "WHERE event_id = ? AND status = 'processing' AND claim_token = ?",
        (datetime.now(timezone.utc).isoformat(), event_id, claim_token),
    )
    conn.commit()
    return cursor.rowcount == 1


def retry_receipt(conn: sqlite3.Connection, event_id: str, claim_token: str, error: str) -> bool:
    cursor = conn.execute(
        "UPDATE communication_receipts SET status = 'retryable', last_error = ?, claim_token = NULL, lease_expires_at = NULL, updated_at = ? "
        "WHERE event_id = ? AND status = 'processing' AND claim_token = ?",
        (error[:200], datetime.now(timezone.utc).isoformat(), event_id, claim_token),
    )
    conn.commit()
    return cursor.rowcount == 1


def quarantine_receipt(conn: sqlite3.Connection, event_id: str, claim_token: str, ciphertext: str, error: str) -> bool:
    """Stop replay of an unreadable protected receipt without exposing it."""
    now = datetime.now(timezone.utc).isoformat()
    identifier, created_at = _identity()
    cursor = conn.execute(
        "UPDATE communication_receipts SET status = 'quarantined', last_error = ?, claim_token = NULL, lease_expires_at = NULL, updated_at = ? "
        "WHERE event_id = ? AND status = 'processing' AND claim_token = ?",
        (error[:200], now, event_id, claim_token),
    )
    if cursor.rowcount != 1:
        conn.commit()
        return False
    conn.execute("UPDATE communication_events SET status = 'quarantined' WHERE id = ?", (event_id,))
    conn.execute(
        "INSERT INTO communication_quarantines VALUES (?, ?, ?, ?, ?)",
        (identifier, "loopmessage", error[:200], hashlib.sha256(ciphertext.encode("utf-8")).hexdigest(), created_at),
    )
    conn.commit()
    return True


def find_endpoint(conn: sqlite3.Connection, provider: str, address: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM communication_endpoints WHERE provider = ? AND address = ? AND status = 'active'", (provider, address)).fetchone()
    return dict(row) if row is not None else None


def record_event_with_receipt(
    conn: sqlite3.Connection, provider: str, event_id: str, message_id: str, event_type: str,
    contact: str, endpoint_id: Optional[str], envelope: Dict[str, Any], ciphertext: str,
) -> Tuple[Dict[str, Any], bool]:
    """Persist the redacted event and protected replay receipt before an HTTP ACK."""
    identifier, received_at = _identity()
    fingerprint = hashlib.sha256((provider + ":" + contact).encode("utf-8")).hexdigest()
    encoded_envelope = _json(envelope)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        try:
            conn.execute(
                "INSERT INTO communication_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'received', ?)",
                (identifier, provider, event_id, message_id or None, event_type, fingerprint, endpoint_id, encoded_envelope, received_at),
            )
            stored = dict(conn.execute("SELECT * FROM communication_events WHERE id = ?", (identifier,)).fetchone())
            created = True
        except sqlite3.IntegrityError:
            stored_row = conn.execute(
                "SELECT * FROM communication_events WHERE provider = ? AND provider_event_id = ?", (provider, event_id)
            ).fetchone()
            if stored_row is None:
                raise
            stored = dict(stored_row)
            created = False
        conn.execute(
            "INSERT OR IGNORE INTO communication_receipts "
            "(event_id, ciphertext, status, attempts, last_error, claim_token, lease_expires_at, updated_at) "
            "VALUES (?, ?, 'queued', 0, NULL, NULL, NULL, ?)",
            (stored["id"], ciphertext, now),
        )
        # Replays wake retryable work, or a demonstrably expired lease.  They
        # must not steal a healthy worker's active claim.
        conn.execute(
            "UPDATE communication_receipts SET status = 'queued', claim_token = NULL, lease_expires_at = NULL, updated_at = ? "
            "WHERE event_id = ? AND (status = 'retryable' OR (status = 'processing' AND (lease_expires_at IS NULL OR lease_expires_at <= ?)))",
            (now, stored["id"], now),
        )
        conn.commit()
        return stored, created
    except Exception:
        conn.rollback()
        raise


def update_event_status(conn: sqlite3.Connection, event_id: str, status: str) -> None:
    conn.execute("UPDATE communication_events SET status = ? WHERE id = ?", (status, event_id))
    conn.commit()


def find_prompt_for_message(conn: sqlite3.Connection, provider_message_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM communication_prompts WHERE provider_message_id = ?", (provider_message_id,)).fetchone()
    return dict(row) if row is not None else None


def find_prompt_for_passthrough(conn: sqlite3.Connection, passthrough: Optional[str], provider: str, contact: str) -> Optional[Dict[str, Any]]:
    if not passthrough:
        return None
    row = conn.execute(
        """SELECT prompt.* FROM communication_prompts prompt
            JOIN communication_endpoints endpoint ON endpoint.id = prompt.endpoint_id
            WHERE prompt.id = ? AND endpoint.provider = ? AND endpoint.address = ?""",
        (passthrough, provider, contact),
    ).fetchone()
    return dict(row) if row is not None else None


def single_open_prompt(conn: sqlite3.Connection, endpoint_id: str) -> Optional[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM communication_prompts WHERE endpoint_id = ? AND status IN ('accepted', 'delivered') ORDER BY created_at", (endpoint_id,)).fetchall()
    return dict(rows[0]) if len(rows) == 1 else None


def attachment_reference(event_id: str, source_url: str) -> str:
    return hashlib.sha256((event_id + ":" + source_url).encode("utf-8")).hexdigest()


def add_attachment(conn: sqlite3.Connection, event_id: str, source_url: str, media_type: str) -> Dict[str, Any]:
    reference = attachment_reference(event_id, source_url)
    existing = conn.execute("SELECT * FROM communication_attachments WHERE event_id = ? AND source_reference = ?", (event_id, reference)).fetchone()
    if existing is not None:
        return dict(existing)
    identifier, created_at = _identity()
    conn.execute(
        "INSERT INTO communication_attachments (id, event_id, source_reference, media_type, status, attempts, last_attempt_at, last_error, created_at) "
        "VALUES (?, ?, ?, ?, 'unavailable', 0, NULL, NULL, ?)",
        (identifier, event_id, reference, media_type, created_at),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_attachments WHERE id = ?", (identifier,)).fetchone())


def attachments_needing_retention(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT attachment.*, receipt.ciphertext
            FROM communication_attachments attachment
            JOIN communication_receipts receipt ON receipt.event_id = attachment.event_id
            WHERE attachment.status = 'unavailable' AND receipt.status = 'processed'
            ORDER BY attachment.created_at"""
    ).fetchall()
    return [dict(row) for row in rows]


def record_attachment_attempt(conn: sqlite3.Connection, attachment_id: str, error: Optional[str] = None, failed: bool = False) -> None:
    conn.execute(
        "UPDATE communication_attachments SET attempts = attempts + 1, last_attempt_at = ?, last_error = ?, status = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), error[:200] if error else None, "failed" if failed else "unavailable", attachment_id),
    )
    conn.commit()


def link_retained_evidence(conn: sqlite3.Connection, attachment_id: str, evidence_artifact_id: str) -> None:
    attachment = conn.execute("SELECT 1 FROM communication_attachments WHERE id = ?", (attachment_id,)).fetchone()
    artifact = conn.execute("SELECT 1 FROM evidence_artifacts WHERE id = ?", (evidence_artifact_id,)).fetchone()
    if attachment is None or artifact is None:
        raise ValueError("communication attachment and retained evidence are required")
    conn.execute("INSERT OR IGNORE INTO communication_evidence_links VALUES (?, ?, ?)", (attachment_id, evidence_artifact_id, datetime.now(timezone.utc).isoformat()))
    conn.execute("UPDATE communication_attachments SET status = 'retained' WHERE id = ?", (attachment_id,))
    conn.commit()


def evidence_is_linked_to_event(conn: sqlite3.Connection, event_id: str, evidence_artifact_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM communication_evidence_links link "
        "JOIN communication_attachments attachment ON attachment.id = link.attachment_id "
        "WHERE attachment.event_id = ? AND link.evidence_artifact_id = ? AND attachment.status = 'retained'",
        (event_id, evidence_artifact_id),
    ).fetchone() is not None


def create_candidate(conn: sqlite3.Connection, event_id: str, prompt_id: Optional[str], allocation_id: Optional[str], work_item_id: Optional[str], endpoint_id: Optional[str], kind: str, draft: Dict[str, Any]) -> Dict[str, Any]:
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_candidates VALUES (?, ?, ?, ?, ?, ?, ?, 'review', ?, NULL, NULL, NULL, NULL, ?)", (identifier, event_id, prompt_id, allocation_id, work_item_id, endpoint_id, kind, _json(draft), created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_candidates WHERE id = ?", (identifier,)).fetchone())


def get_candidate(conn: sqlite3.Connection, candidate_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM communication_candidates WHERE id = ?", (candidate_id,)).fetchone()
    return dict(row) if row is not None else None


def get_candidate_for_event(conn: sqlite3.Connection, event_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM communication_candidates WHERE event_id = ?", (event_id,)).fetchone()
    return dict(row) if row is not None else None


def candidate_detail(conn: sqlite3.Connection, candidate_id: str) -> Optional[Dict[str, Any]]:
    candidate = get_candidate(conn, candidate_id)
    if candidate is None:
        return None
    event = conn.execute(
        "SELECT provider, received_at FROM communication_events WHERE id = ?", (candidate["event_id"],)
    ).fetchone()
    if event is None:
        return None
    endpoint = None
    if candidate["endpoint_id"]:
        endpoint_row = conn.execute(
            "SELECT id, person_id, provider, address, locale, status FROM communication_endpoints WHERE id = ?",
            (candidate["endpoint_id"],),
        ).fetchone()
        if endpoint_row is not None:
            endpoint = dict(endpoint_row)
    attachments = [
        dict(row) for row in conn.execute(
            """SELECT attachment.id, attachment.media_type, attachment.status, attachment.attempts,
                      attachment.last_attempt_at, attachment.created_at,
                      artifact.id AS evidence_artifact_id, artifact.media_type AS evidence_media_type,
                      artifact.size_bytes AS evidence_size_bytes, artifact.created_at AS evidence_created_at
               FROM communication_attachments attachment
               LEFT JOIN communication_evidence_links link ON link.attachment_id = attachment.id
               LEFT JOIN evidence_artifacts artifact ON artifact.id = link.evidence_artifact_id
               WHERE attachment.event_id = ? ORDER BY attachment.created_at""",
            (candidate["event_id"],),
        ).fetchall()
    ]
    return {"candidate": candidate, "event": dict(event), "endpoint": endpoint, "attachments": attachments}


def review_candidate(conn: sqlite3.Connection, candidate_id: str, status: str, reviewer_id: str, record_type: Optional[str] = None, record_id: Optional[str] = None) -> Dict[str, Any]:
    if status not in ("accepted", "rejected") or conn.execute("SELECT 1 FROM people WHERE id = ?", (reviewer_id,)).fetchone() is None:
        raise ValueError("invalid communication candidate review")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE communication_candidates SET status = ?, accepted_record_type = ?, accepted_record_id = ?, reviewed_by_person_id = ?, reviewed_at = ? WHERE id = ?", (status, record_type, record_id, reviewer_id, now, candidate_id))
    conn.commit()
    return get_candidate(conn, candidate_id)  # type: ignore[return-value]


def inbox(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT id, kind, status, allocation_id, work_item_id, created_at FROM communication_candidates WHERE status = 'review' ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def health(conn: sqlite3.Connection) -> Dict[str, int]:
    failed = conn.execute("SELECT count(*) FROM communication_prompts WHERE status = 'failed'").fetchone()[0]
    awaiting = conn.execute("SELECT count(*) FROM communication_prompts WHERE status IN ('accepted', 'delivered')").fetchone()[0]
    review = conn.execute("SELECT count(*) FROM communication_candidates WHERE status = 'review'").fetchone()[0]
    unknown = conn.execute("SELECT count(*) FROM communication_prompts WHERE status = 'unknown'").fetchone()[0]
    retryable_receipts = conn.execute("SELECT count(*) FROM communication_receipts WHERE status = 'retryable'").fetchone()[0]
    unavailable_media = conn.execute("SELECT count(*) FROM communication_attachments WHERE status = 'unavailable'").fetchone()[0]
    failed_media = conn.execute("SELECT count(*) FROM communication_attachments WHERE status = 'failed'").fetchone()[0]
    return {
        "failed_delivery_count": failed,
        "unknown_delivery_count": unknown,
        "awaiting_response_count": awaiting,
        "review_required_count": review,
        "retryable_receipt_count": retryable_receipts,
        "unavailable_media_count": unavailable_media,
        "failed_media_count": failed_media,
    }
