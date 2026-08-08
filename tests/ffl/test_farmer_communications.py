from __future__ import annotations

from datetime import date

from ffl.persistence import repository
from ffl.services.farmer_communications import board_for_source


def _source(conn, owner):
    return repository.create_source_registry(
        conn,
        source_key="trackwick-fortune-paddy",
        display_name="Fortune paddy visits (TrackWick)",
        source_type="trackwick",
        purpose="operational_campaign",
        authority_level="partner",
        owner_id=owner.id,
        permitted_data_classes=["farm_candidate_context"],
        schema_version="trackwick-v3",
        mapping_version="trackwick-live-v4",
        default_coverage={},
        enabled=True,
    )


def _farmer(conn, source_id: str, farmer_id: str, name: str):
    now = "2026-08-08T10:00:00+05:30"
    conn.execute(
        """INSERT INTO trackwick_parties (
               id, source_id, party_kind, provider_identifier, display_name,
               source_fingerprint, mapping_version, data_quality_status,
               first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, 'farmer', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (farmer_id, source_id, farmer_id, name, "a" * 64, now, now, now),
    )


def _visit(conn, source_id: str, task_id: str, farmer_id: str, transplanted_on: str, *, product: str | None = None):
    now = "2026-08-08T10:00:00+05:30"
    conn.execute(
        """INSERT INTO trackwick_tasks (
               id, source_id, provider_task_id, farmer_party_id, task_type, task_status,
               source_fingerprint, mapping_version, data_quality_status,
               first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, ?, ?, 'Farmer Visit', 'completed', ?, 'v1', 'valid', ?, ?, ?)""",
        (task_id, source_id, task_id, farmer_id, "b" * 64, now, now, now),
    )
    conn.execute(
        """INSERT INTO trackwick_visits (
               task_id, source_id, observed_at, transplanted_on, crop_stage, kit_status,
               source_fingerprint, mapping_version, data_quality_status,
               first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, ?, ?, 'Vegetative', 'taken', ?, 'v1', 'valid', ?, ?, ?)""",
        (task_id, source_id, now, transplanted_on, "c" * 64, now, now, now),
    )
    if product:
        conn.execute(
            """INSERT INTO trackwick_crop_inputs (
                   id, visit_task_id, source_id, input_kind, event_kind, reported_product,
                   source_field, occurred_at, source_fingerprint, mapping_version,
                   data_quality_status, first_seen_at, last_seen_at, created_at
               ) VALUES (?, ?, ?, 'pesticide', 'applied', ?, 'reported input', ?, ?, 'v1', 'valid', ?, ?, ?)""",
            ("input-" + task_id, task_id, source_id, product, now, "d" * 64, now, now, now),
        )


def _disease(conn, source_id: str, task_id: str):
    now = "2026-08-08T10:00:00+05:30"
    conn.execute(
        """INSERT INTO trackwick_visit_findings (
               id, visit_task_id, source_id, finding_kind, reported_value, source_field,
               declared_severity, observed_at, source_fingerprint, mapping_version,
               data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, ?, 'disease', 'reported disease', 'field finding', 'moderate', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        ("finding-" + task_id, task_id, source_id, now, "e" * 64, now, now, now),
    )


def test_farmer_communication_keeps_timing_and_reported_vayego_separate(ffl_db, owner):
    source = _source(ffl_db, owner)
    _farmer(ffl_db, source.id, "first", "First Farmer")
    _farmer(ffl_db, source.id, "second-vayego", "Second Vayego")
    _farmer(ffl_db, source.id, "second", "Second Farmer")
    _farmer(ffl_db, source.id, "ambiguous", "Ambiguous Farmer")
    _farmer(ffl_db, source.id, "missing", "Missing Farmer")
    _farmer(ffl_db, source.id, "disease", "Disease Farmer")
    _visit(ffl_db, source.id, "visit-first", "first", "2026-06-24")
    _visit(ffl_db, source.id, "visit-second-vayego", "second-vayego", "2026-06-10", product="Vayego 50 SC")
    _visit(ffl_db, source.id, "visit-second", "second", "2026-06-12", product="Other product")
    _visit(ffl_db, source.id, "visit-ambiguous-a", "ambiguous", "2026-06-24")
    _visit(ffl_db, source.id, "visit-ambiguous-b", "ambiguous", "2026-06-28")
    _visit(ffl_db, source.id, "visit-disease", "disease", "2026-05-01")
    _disease(ffl_db, source.id, "visit-disease")

    first = board_for_source(ffl_db, cohort="first_spray", evaluated_on=date(2026, 8, 8))
    second_vayego = board_for_source(
        ffl_db, cohort="second_spray_vayego", evaluated_on=date(2026, 8, 8),
    )

    assert first["summary"] == {
        "reported_farmers": 6,
        "all_reported_farmers": 6,
        "timing_available": 4,
        "missing_transplant_date": 1,
        "ambiguous_transplant_dates": 1,
        "first_timing": 1,
        "second_timing": 2,
        "second_timing_vayego": 1,
        "disease_reported": 1,
        "no_reported_visit": 1,
    }
    assert first["records"] == [{
        "id": "first", "name": "First Farmer", "state": "timed",
        "transplanted_on": "2026-06-24", "days_since_transplant": 45,
        "latest_field_record_at": "2026-08-08T10:00:00+05:30",
        "latest_field_record_on": "2026-08-08", "crop_stage": "Vegetative",
        "kit_status": "taken", "reported_vayego_applied": False,
        "reported_issue_since_transplant": False, "open_work": 0,
        "reported_disease": False, "latest_disease_reported_on": None,
        "place": None, "place_status": "not_reported",
    }]
    assert [row["name"] for row in second_vayego["records"]] == ["Second Vayego"]
    assert second_vayego["records"][0]["reported_vayego_applied"] is True
    assert second_vayego["delivery"]["state"] == "audience_ready"
    assert "Other product" not in repr(second_vayego)

    disease = board_for_source(ffl_db, cohort="disease_reported", evaluated_on=date(2026, 8, 8))
    missing_visit = board_for_source(ffl_db, cohort="no_reported_visit", evaluated_on=date(2026, 8, 8))
    everyone = board_for_source(ffl_db, cohort="all_reported_farmers", evaluated_on=date(2026, 8, 8))
    assert [row["name"] for row in disease["records"]] == ["Disease Farmer"]
    assert [row["name"] for row in missing_visit["records"]] == ["Missing Farmer"]
    assert everyone["page"]["total"] == 6


def test_farmer_communication_rejects_unknown_cohort(ffl_db, owner):
    _source(ffl_db, owner)
    try:
        board_for_source(ffl_db, cohort="anything")
    except ValueError as error:
        assert str(error) == "unknown campaign audience"
    else:  # pragma: no cover - makes the safety boundary explicit
        raise AssertionError("unknown cohort must not be accepted")
