import json
import hashlib
import sqlite3

import pytest

from ffl.persistence.repository import (
    accept_farm_truth_case,
    claim_farm_truth_case,
    create_operating_unit,
    create_or_refresh_farm_truth_case,
    create_person,
    create_season,
    get_farm_truth_case,
    list_farm_truth_cases,
    mark_farm_truth_case_needs_evidence,
    mark_farm_truth_case_rejected,
)


def _candidate_fingerprint() -> str:
    material = {
        "registration_source_fingerprint": "d" * 64,
        "plot_source_fingerprint": "e" * 64,
        "eligible_tasks": [
            {
                "id": "task-registration",
                "source_fingerprint": "c" * 64,
                "status": "completed",
            },
            {
                "association_source_fingerprint": "8" * 64,
                "id": "task-visit",
                "source_fingerprint": "6" * 64,
                "status": "completed",
                "visit_source_fingerprint": "7" * 64,
            },
        ],
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


FINGERPRINT = _candidate_fingerprint()


def _seed_trackwick_candidate(conn):
    owner = create_person(conn, "Source owner", "operations_lead")
    conn.execute(
        """INSERT INTO source_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "source-1", "trackwick", "TrackWick", "partner", "farm context", "source",
            owner.id, None, None, "[]", None, None, "v1", "v1", "{}", 1,
            "2026-08-04T12:00:00+00:00",
        ),
    )
    now = "2026-08-04T12:00:00+00:00"
    conn.execute(
        """INSERT INTO trackwick_parties (
            id, source_id, party_kind, provider_identifier, display_name,
            source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, 'farmer', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        ("party-farmer", "source-1", "provider-farmer", "Source grower", "b" * 64, now, now, now),
    )
    conn.execute(
        """INSERT INTO trackwick_tasks (
            id, source_id, provider_task_id, farmer_party_id, task_type, task_status,
            provider_created_at, provider_completed_at, source_fingerprint, mapping_version,
            data_quality_status, first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, ?, 'Registration', 'completed', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        ("task-registration", "source-1", "provider-task", "party-farmer", now, now,
         "c" * 64, now, now, now),
    )
    conn.execute(
        """INSERT INTO trackwick_registrations (
            id, task_id, source_id, farmer_party_id, registration_status, village_name,
            block_name, district_name, reported_total_area_acres, reported_plot_count,
            source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, ?, 'completed', 'Village', 'Block', 'District', 2.5, 1,
                  ?, 'v1', 'valid', ?, ?, ?)""",
        ("registration-1", "task-registration", "source-1", "party-farmer",
         "d" * 64, now, now, now),
    )
    conn.execute(
        """INSERT INTO trackwick_registration_plots (
            id, registration_id, source_id, ordinal, gata_number, reported_area_bigha,
            plot_type, village_name, source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, 1, 'Gata 1', 2.5, 'field', 'Village',
                  ?, 'v1', 'valid', ?, ?, ?)""",
        ("plot-1", "registration-1", "source-1", "e" * 64, now, now, now),
    )
    conn.execute(
        """INSERT INTO trackwick_tasks (
            id, source_id, provider_task_id, farmer_party_id, task_type, task_status,
            provider_created_at, provider_completed_at, source_fingerprint, mapping_version,
            data_quality_status, first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, ?, 'Farmer Visit', 'completed', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (
            "task-visit", "source-1", "provider-visit", "party-farmer", now, now,
            "6" * 64, now, now, now,
        ),
    )
    conn.execute(
        """INSERT INTO trackwick_visits (
            task_id, source_id, observed_at, kit_status, source_fingerprint,
            mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, '2026-08-01T12:00:00+00:00', 'taken', ?, 'v1', 'valid', ?, ?, ?)""",
        ("task-visit", "source-1", "7" * 64, now, now, now),
    )
    conn.execute(
        """INSERT INTO trackwick_task_plot_links (
            id, source_id, task_id, registration_id, plot_id, association_kind,
            source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES ('task-plot-link', 'source-1', 'task-visit', 'registration-1',
                  'plot-1', 'source_explicit', ?, 'v1', 'valid', ?, ?, ?)""",
        ("8" * 64, now, now, now),
    )
    conn.commit()
    return owner


def _create_case(conn, fingerprint=FINGERPRINT):
    return create_or_refresh_farm_truth_case(
        conn,
        source_id="source-1",
        registration_id="registration-1",
        plot_id="plot-1",
        candidate_fingerprint=fingerprint,
        evidence_summary={"reason_chips": ["Registration", "Recent visit"]},
    )


def _acceptance_values(conn, reviewer):
    unit = create_operating_unit(conn, "Fortune Farm")
    season = create_season(conn, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    return {
        "reviewer_id": reviewer.id,
        "operating_unit_id": unit.id,
        "season_id": season.id,
        "field_name": "Village field 1",
        "managed_area_hectares": 1.0,
        "crop_name": "Rice",
        "cultivar": "PB1",
        "grower_effective_on": "2026-06-01",
        "right_type": "managed",
        "right_starts_on": "2026-06-01",
        "right_ends_on": "2026-11-30",
    }


def test_create_open_case_and_refresh_without_duplicate(ffl_db):
    _seed_trackwick_candidate(ffl_db)

    created = _create_case(ffl_db)
    replayed = create_or_refresh_farm_truth_case(
        ffl_db,
        source_id="source-1",
        registration_id="registration-1",
        plot_id="plot-1",
        candidate_fingerprint=FINGERPRINT,
        evidence_summary={"reason_chips": ["Registration", "Two recent visits"]},
    )

    assert created.status == "open"
    assert created.registration_id == "registration-1"
    assert replayed.id == created.id
    assert replayed.evidence_summary == {"reason_chips": ["Registration", "Two recent visits"]}
    assert list_farm_truth_cases(ffl_db, status="open") == [replayed]
    assert ffl_db.execute("SELECT COUNT(*) FROM farm_truth_review_cases").fetchone()[0] == 1


def test_one_case_per_plot_fingerprint_is_database_enforced(ffl_db):
    _seed_trackwick_candidate(ffl_db)
    created = _create_case(ffl_db)

    with pytest.raises(sqlite3.IntegrityError):
        ffl_db.execute(
            """INSERT INTO farm_truth_review_cases (
                id, source_id, registration_id, plot_id, candidate_fingerprint, status,
                evidence_summary_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'open', '{}', ?, ?)""",
            ("duplicate", "source-1", "registration-1", "plot-1", FINGERPRINT,
             created.created_at, created.updated_at),
        )


def test_allowed_lifecycle_transitions_and_terminal_decisions(ffl_db):
    reviewer = _seed_trackwick_candidate(ffl_db)
    open_case = _create_case(ffl_db)

    claimed = claim_farm_truth_case(ffl_db, open_case.id)
    assert claimed is not None and claimed.status == "accepting"
    with pytest.raises(sqlite3.IntegrityError, match="invalid farm truth review case transition"):
        ffl_db.execute(
            "UPDATE farm_truth_review_cases SET status = 'rejected' WHERE id = ?",
            (open_case.id,),
        )
    ffl_db.rollback()

    needs_case = create_or_refresh_farm_truth_case(
        ffl_db, "source-1", "registration-1", "plot-1", "f" * 64, {"reason_chips": []}
    )
    needs_case = mark_farm_truth_case_needs_evidence(
        ffl_db, needs_case.id, reviewer.id, "plot_area", "Confirm the managed area"
    )
    assert needs_case.status == "needs_evidence"
    assert needs_case.owner_person_id == reviewer.id
    assert needs_case.missing_evidence_kind == "plot_area"
    with pytest.raises(sqlite3.IntegrityError, match="invalid farm truth review case transition"):
        ffl_db.execute(
            "UPDATE farm_truth_review_cases SET evidence_summary_json = '{}' WHERE id = ?",
            (needs_case.id,),
        )
    ffl_db.rollback()

    rejected_case = create_or_refresh_farm_truth_case(
        ffl_db, "source-1", "registration-1", "plot-1", "1" * 64, {"reason_chips": []}
    )
    rejected_case = mark_farm_truth_case_rejected(
        ffl_db, rejected_case.id, reviewer.id, "Outside the programme"
    )
    assert rejected_case.status == "rejected"
    assert rejected_case.reviewed_by_person_id == reviewer.id
    with pytest.raises(sqlite3.IntegrityError, match="invalid farm truth review case transition"):
        ffl_db.execute(
            "UPDATE farm_truth_review_cases SET evidence_summary_json = '{}' WHERE id = ?",
            (rejected_case.id,),
        )
    ffl_db.rollback()
    assert ffl_db.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0] == 0


def test_acceptance_is_idempotent_and_creates_one_complete_canonical_set(ffl_db):
    reviewer = _seed_trackwick_candidate(ffl_db)
    case = _create_case(ffl_db)
    values = _acceptance_values(ffl_db, reviewer)

    accepted = accept_farm_truth_case(ffl_db, case.id, **values)
    replayed = accept_farm_truth_case(ffl_db, case.id, **values)

    assert accepted == replayed
    assert accepted.status == "accepted"
    with pytest.raises(sqlite3.IntegrityError, match="invalid farm truth review case transition"):
        ffl_db.execute(
            "UPDATE farm_truth_review_cases SET evidence_summary_json = '{}' WHERE id = ?",
            (accepted.id,),
        )
    ffl_db.rollback()
    assert all((accepted.accepted_land_parcel_id, accepted.accepted_operational_block_id,
                accepted.accepted_crop_allocation_id, accepted.accepted_grower_person_id))
    assert ffl_db.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0] == 1
    assert ffl_db.execute("SELECT COUNT(*) FROM operational_blocks").fetchone()[0] == 1
    assert ffl_db.execute("SELECT COUNT(*) FROM farms").fetchone()[0] == 1
    membership = ffl_db.execute("SELECT * FROM farm_fields").fetchone()
    assert membership["operational_block_id"] == accepted.accepted_operational_block_id
    assert membership["status"] == "active"
    assert ffl_db.execute("SELECT COUNT(*) FROM rights_to_operate").fetchone()[0] == 1
    assert ffl_db.execute("SELECT COUNT(*) FROM crop_allocations").fetchone()[0] == 1
    assert ffl_db.execute("SELECT COUNT(*) FROM trackwick_party_person_links").fetchone()[0] == 1
    assert ffl_db.execute("SELECT COUNT(*) FROM trackwick_plot_operating_links").fetchone()[0] == 1
    audit = ffl_db.execute("SELECT * FROM audit_events").fetchone()
    metadata = json.loads(audit["reason"])
    assert metadata["case_id"] == case.id
    assert metadata["source_id"] == "source-1"
    assert metadata["registration_id"] == "registration-1"
    assert metadata["plot_id"] == "plot-1"


def test_acceptance_rolls_back_claim_and_every_canonical_write_on_failure(ffl_db):
    reviewer = _seed_trackwick_candidate(ffl_db)
    case = _create_case(ffl_db)
    values = _acceptance_values(ffl_db, reviewer)
    ffl_db.execute(
        """CREATE TRIGGER fail_farm_truth_crop_insert
           BEFORE INSERT ON crop_allocations
           BEGIN
               SELECT RAISE(ABORT, 'required canonical write failed');
           END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="required canonical write failed"):
        accept_farm_truth_case(ffl_db, case.id, **values)

    assert get_farm_truth_case(ffl_db, case.id).status == "open"
    for table in (
        "land_parcels", "operational_blocks", "farms", "farm_fields", "block_parcels", "rights_to_operate",
        "crop_allocations", "person_operating_relationships", "trackwick_party_person_links",
        "trackwick_plot_operating_links", "audit_events",
    ):
        assert ffl_db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0


def test_acceptance_rejects_a_plot_with_an_existing_reviewed_operating_link(ffl_db):
    reviewer = _seed_trackwick_candidate(ffl_db)
    first_case = _create_case(ffl_db)
    values = _acceptance_values(ffl_db, reviewer)
    accept_farm_truth_case(ffl_db, first_case.id, **values)
    changed_case = create_or_refresh_farm_truth_case(
        ffl_db, "source-1", "registration-1", "plot-1", "2" * 64, {"reason_chips": []}
    )

    with pytest.raises(ValueError, match="already has a reviewed operating link"):
        accept_farm_truth_case(ffl_db, changed_case.id, **values)

    assert get_farm_truth_case(ffl_db, changed_case.id).status == "open"
    assert ffl_db.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0] == 1
    assert ffl_db.execute("SELECT COUNT(*) FROM trackwick_plot_operating_links").fetchone()[0] == 1


def test_repository_replay_requires_the_same_acceptance_fingerprint(ffl_db):
    reviewer = _seed_trackwick_candidate(ffl_db)
    case = _create_case(ffl_db)
    values = _acceptance_values(ffl_db, reviewer)
    accepted = accept_farm_truth_case(ffl_db, case.id, **values)

    with pytest.raises(ValueError, match="does not match"):
        accept_farm_truth_case(
            ffl_db, case.id, **{**values, "field_name": "Different field"}
        )

    assert get_farm_truth_case(ffl_db, case.id) == accepted
    assert ffl_db.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0] == 1


def test_repository_replay_normalizes_an_omitted_season_right_end(ffl_db):
    reviewer = _seed_trackwick_candidate(ffl_db)
    case = _create_case(ffl_db)
    values = {**_acceptance_values(ffl_db, reviewer), "right_ends_on": None}

    accepted = accept_farm_truth_case(ffl_db, case.id, **values)
    ffl_db.execute(
        """UPDATE seasons
           SET starts_on = '2025-01-01', ends_on = '2025-12-15'
           WHERE id = ?""",
        (values["season_id"],),
    )
    ffl_db.commit()
    replayed_with_omitted_default = accept_farm_truth_case(ffl_db, case.id, **values)
    replayed_with_explicit_original_default = accept_farm_truth_case(
        ffl_db, case.id, **{**values, "right_ends_on": "2026-11-30"}
    )

    assert replayed_with_omitted_default == accepted
    assert replayed_with_explicit_original_default == accepted
    stored_contract = accepted.evidence_summary["_acceptance_contract"]
    assert stored_contract["right_ends_on"] == "2026-11-30"
    assert accepted.evidence_summary["_acceptance_fingerprint"]


@pytest.mark.parametrize(
    "table",
    [
        "trackwick_party_person_links",
        "trackwick_plot_operating_links",
        "trackwick_task_allocation_links",
    ],
)
def test_reviewed_trackwick_links_cannot_be_updated_or_deleted(ffl_db, table):
    reviewer = _seed_trackwick_candidate(ffl_db)
    case = _create_case(ffl_db)
    values = _acceptance_values(ffl_db, reviewer)
    accept_farm_truth_case(ffl_db, case.id, **values)

    with pytest.raises(sqlite3.IntegrityError, match="reviewed TrackWick links are immutable"):
        ffl_db.execute("UPDATE " + table + " SET link_status = 'rejected'")
    ffl_db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="reviewed TrackWick links are immutable"):
        ffl_db.execute("DELETE FROM " + table)
    ffl_db.rollback()

    assert ffl_db.execute("SELECT link_status FROM " + table).fetchone()[0] == "reviewed"
