from __future__ import annotations

import hashlib
import json

import pytest

from ffl.persistence import repository
from ffl.services.farm_truth import (
    get_farm_truth_case_detail,
    list_farm_truth_case_summaries,
    list_farm_truth_inbox_items,
    refresh_farm_truth_cases,
)


NOW = "2026-08-04T12:00:00+00:00"


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
def farm_truth_context(ffl_db):
    actor = repository.create_person(ffl_db, "Fortune reviewer", "operations_lead")
    unit = repository.create_operating_unit(ffl_db, "Fortune Farm")
    season = repository.create_season(
        ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30"
    )
    source = repository.create_source_registry(
        ffl_db,
        source_key="trackwick-fortune-paddy",
        display_name="TrackWick",
        source_type="trackwick",
        purpose="Private typed farm evidence",
        authority_level="partner",
        owner_id=actor.id,
        permitted_data_classes=["farm_candidate_context"],
        schema_version="trackwick-v3",
        mapping_version="trackwick-live-v4",
        default_coverage={},
        enabled=True,
    )
    return actor, unit, season, source


def _seed_party(conn, source_id: str, party_id: str, kind: str, display_name: str) -> None:
    conn.execute(
        """INSERT INTO trackwick_parties (
               id, source_id, party_kind, provider_identifier, display_name,
               source_fingerprint, mapping_version, data_quality_status,
               first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (
            party_id,
            source_id,
            kind,
            "provider:" + party_id,
            display_name,
            _fingerprint("party:" + party_id),
            NOW,
            NOW,
            NOW,
        ),
    )


def _seed_task(
    conn,
    source_id: str,
    task_id: str,
    farmer_id: str | None,
    *,
    task_type: str,
    status: str,
    completed_at: str | None,
    created_at: str,
    worker_id: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO trackwick_tasks (
               id, source_id, provider_task_id, farmer_party_id, field_worker_party_id,
               task_type, task_status, provider_created_at, provider_completed_at,
               source_fingerprint, mapping_version, data_quality_status,
               first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (
            task_id,
            source_id,
            "provider:" + task_id,
            farmer_id,
            worker_id,
            task_type,
            status,
            created_at,
            completed_at,
            _fingerprint("task:" + task_id),
            NOW,
            NOW,
            NOW,
        ),
    )


def _seed_candidate(
    conn,
    source_id: str,
    suffix: str,
    *,
    plot_area: float | None = 2.0,
    registration_area: float | None = 1.25,
    registration_status: str = "completed",
    registration_at: str = "2026-06-10T09:00:00+00:00",
    visit_times: tuple[str, ...] = ("2026-07-20T10:00:00+00:00",),
    open_work: int = 0,
    linked_farmer: bool = True,
) -> tuple[str, str, str | None]:
    farmer_id = "farmer-" + suffix if linked_farmer else None
    if farmer_id:
        _seed_party(conn, source_id, farmer_id, "farmer", "Farmer " + suffix)
    worker_id = "worker-" + suffix
    _seed_party(conn, source_id, worker_id, "field_worker", "Worker " + suffix)
    registration_task_id = "registration-task-" + suffix
    _seed_task(
        conn,
        source_id,
        registration_task_id,
        farmer_id,
        task_type="New Farmer Registration",
        status=registration_status,
        completed_at=registration_at,
        created_at=registration_at,
    )
    registration_id = "registration-" + suffix
    conn.execute(
        """INSERT INTO trackwick_registrations (
               id, task_id, source_id, farmer_party_id, registration_status,
               village_name, block_name, district_name, reported_total_area_acres,
               reported_plot_count, reported_pb1_area_acres, reported_1718_area_acres,
               source_fingerprint, mapping_version, data_quality_status,
               first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, 'Gabhana', 'Aligarh', ?, 1, 0.75, 0.5,
                     ?, 'v1', 'valid', ?, ?, ?)""",
        (
            registration_id,
            registration_task_id,
            source_id,
            farmer_id,
            registration_status,
            "Village " + suffix,
            registration_area,
            _fingerprint("registration:" + suffix),
            NOW,
            NOW,
            NOW,
        ),
    )
    plot_id = "plot-" + suffix
    conn.execute(
        """INSERT INTO trackwick_registration_plots (
               id, registration_id, source_id, ordinal, gata_number,
               reported_area_bigha, plot_type, village_name, source_fingerprint,
               mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES (?, ?, ?, 1, ?, ?, 'field', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (
            plot_id,
            registration_id,
            source_id,
            "Gata " + suffix,
            plot_area,
            "Village " + suffix,
            _fingerprint("plot:" + suffix),
            NOW,
            NOW,
            NOW,
        ),
    )
    for index, visit_at in enumerate(visit_times):
        task_id = f"visit-{suffix}-{index}"
        _seed_task(
            conn,
            source_id,
            task_id,
            farmer_id,
            task_type="Farmer Visit",
            status="completed",
            completed_at=visit_at,
            created_at=visit_at,
            worker_id=worker_id,
        )
        conn.execute(
            """INSERT INTO trackwick_visits (
                   task_id, source_id, observed_at, transplanted_on, crop_stage,
                   crop_condition_score, kit_status, source_fingerprint,
                   mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
               ) VALUES (?, ?, ?, '2026-06-15', 'Tillering', 8, 'taken', ?,
                         'v1', 'valid', ?, ?, ?)""",
            (
                task_id,
                source_id,
                visit_at,
                _fingerprint("visit:" + task_id),
                NOW,
                NOW,
                NOW,
            ),
        )
    for index in range(open_work):
        _seed_task(
            conn,
            source_id,
            f"open-{suffix}-{index}",
            farmer_id,
            task_type="CALL 9999999999 — raw provider follow-up",
            status="pending",
            completed_at=None,
            created_at="2026-07-25T10:00:00+00:00",
            worker_id=worker_id,
        )
    conn.commit()
    return registration_id, plot_id, farmer_id


def _seed_sensitive_private_rows(conn, source_id: str, farmer_id: str, visit_task_id: str) -> None:
    conn.execute(
        """INSERT INTO trackwick_contact_points (
               id, party_id, source_id, contact_kind, contact_value, value_fingerprint,
               consent_status, source_fingerprint, mapping_version, data_quality_status,
               first_seen_at, last_seen_at, created_at
           ) VALUES ('contact-secret', ?, ?, 'mobile', '9999999999', ?, 'unknown', ?,
                     'v1', 'valid', ?, ?, ?)""",
        (
            farmer_id,
            source_id,
            _fingerprint("mobile"),
            _fingerprint("contact"),
            NOW,
            NOW,
            NOW,
        ),
    )
    conn.execute(
        """INSERT INTO trackwick_location_observations (
               id, source_id, party_id, provider_location_key, location_kind,
               location_confidence, latitude, longitude, provider_address,
               provider_geo_address, observed_at, source_fingerprint, mapping_version,
               data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES ('location-secret', ?, ?, 'provider-location-secret', 'crm',
                     'declared', 27.951234, 78.271234, 'Secret raw address',
                     'Secret geo text', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (source_id, farmer_id, NOW, _fingerprint("location"), NOW, NOW, NOW),
    )
    conn.execute(
        """INSERT INTO trackwick_media_references (
               id, source_id, task_id, provider_media_key, media_kind, remote_url,
               source_access_state, content_state, exif_state, source_fingerprint,
               mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES ('media-secret', ?, ?, 'provider-media-secret', 'crop_photo',
                     'https://trackolap-images-prod.s3.amazonaws.com/secret.jpg',
                     'available', 'remote_only', 'not_checked', ?, 'v1', 'valid', ?, ?, ?)""",
        (source_id, visit_task_id, _fingerprint("media"), NOW, NOW, NOW),
    )
    conn.execute(
        """INSERT INTO trackwick_visit_findings (
               id, visit_task_id, source_id, finding_kind, reported_value, source_field,
               declared_severity, observed_at, source_fingerprint, mapping_version,
               data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES ('finding-secret', ?, ?, 'pest', 'AADHAAR 111122223333 raw answer',
                     'unsafe raw form field', 'unknown', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (visit_task_id, source_id, NOW, _fingerprint("finding"), NOW, NOW, NOW),
    )
    conn.commit()


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_keys(nested)


def test_refresh_discovers_one_safe_registration_plot_candidate(ffl_db, farm_truth_context):
    actor, unit, season, source = farm_truth_context
    _, _, farmer_id = _seed_candidate(
        ffl_db,
        source.id,
        "safe",
        visit_times=(
            "2026-05-30T10:00:00+00:00",
            "2026-07-20T10:00:00+00:00",
            "2026-08-01T11:00:00+00:00",
        ),
        open_work=1,
    )
    _seed_sensitive_private_rows(ffl_db, source.id, farmer_id, "visit-safe-1")
    source_rows_before = {
        table: [tuple(row) for row in ffl_db.execute("SELECT * FROM " + table).fetchall()]
        for table in (
            "trackwick_contact_points",
            "trackwick_location_observations",
            "trackwick_media_references",
            "trackwick_visit_findings",
        )
    }

    queue = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)
    listed = list_farm_truth_case_summaries(ffl_db)
    detail = get_farm_truth_case_detail(ffl_db, queue[0]["id"])
    serialized = json.dumps([queue, listed, detail], sort_keys=True)

    assert queue == listed
    assert detail == queue[0]
    assert queue[0]["status"] == "open"
    assert queue[0]["place"] == {
        "village": "Village safe",
        "block": "Gabhana",
        "district": "Aligarh",
    }
    assert queue[0]["area"] == {
        "gata_number": "Gata safe",
        "plot_bigha": 2.0,
        "registration_acres": 1.25,
        "registration_plot_count": 1,
    }
    assert queue[0]["registration"] == {
        "completed_at": "2026-06-10T09:00:00+00:00",
        "pb1_acres": 0.75,
        "variety_1718_acres": 0.5,
    }
    assert queue[0]["crop_timing"] == {
        "latest_visit_at": "2026-08-01T11:00:00+00:00",
        "transplanted_on": "2026-06-15",
        "crop_stage": "Tillering",
    }
    assert queue[0]["people"] == {
        "farmer_display_name": "Farmer safe",
        "field_worker_display_names": ["Worker safe"],
    }
    assert queue[0]["evidence"] == {
        "recent_visit_count": 2,
        "open_work_count": 1,
        "safe_task_labels": ["Farmer visit", "Open follow-up"],
        "reason_chips": ["Registration", "2 recent visits", "Open follow-up"],
    }
    assert set(_all_keys(queue)) & {
        "source_id",
        "registration_id",
        "plot_id",
        "candidate_fingerprint",
        "provider_identifier",
        "provider_task_id",
        "latitude",
        "longitude",
        "remote_url",
        "raw_payload",
        "form_details",
    } == set()
    for secret in (
        "9999999999",
        "111122223333",
        "27.951234",
        "78.271234",
        "secret.jpg",
        "Secret raw address",
        "unsafe raw form field",
        "raw provider follow-up",
    ):
        assert secret not in serialized
    assert source_rows_before == {
        table: [tuple(row) for row in ffl_db.execute("SELECT * FROM " + table).fetchall()]
        for table in source_rows_before
    }


def test_refresh_rejects_ineligible_evidence_and_accepts_registration_area_fallback(
    ffl_db, farm_truth_context
):
    actor, unit, season, source = farm_truth_context
    _seed_candidate(ffl_db, source.id, "missing-area", plot_area=None, registration_area=None)
    _seed_candidate(ffl_db, source.id, "zero-area", plot_area=0, registration_area=0)
    _seed_candidate(ffl_db, source.id, "no-farmer", linked_farmer=False)
    _seed_candidate(ffl_db, source.id, "pending", registration_status="pending")
    _seed_candidate(
        ffl_db,
        source.id,
        "old-visit",
        visit_times=("2026-05-31T23:59:59+00:00",),
    )
    _seed_candidate(ffl_db, source.id, "fallback", plot_area=0, registration_area=1.5)

    queue = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)

    assert [row["place"]["village"] for row in queue] == ["Village fallback"]
    assert ffl_db.execute("SELECT COUNT(*) FROM farm_truth_review_cases").fetchone()[0] == 1


def test_refresh_uses_transparent_priority_and_retains_candidates_beyond_queue_limit(
    ffl_db, farm_truth_context
):
    actor, unit, season, source = farm_truth_context
    _seed_candidate(
        ffl_db,
        source.id,
        "open-old",
        visit_times=("2026-07-01T10:00:00+00:00",),
        open_work=1,
    )
    _seed_candidate(
        ffl_db,
        source.id,
        "closed-new",
        visit_times=("2026-08-03T10:00:00+00:00",),
    )
    _seed_candidate(
        ffl_db,
        source.id,
        "closed-newer-registration",
        registration_at="2026-07-10T09:00:00+00:00",
        visit_times=("2026-08-03T10:00:00+00:00",),
    )
    _seed_candidate(
        ffl_db,
        source.id,
        "open-new",
        visit_times=("2026-08-02T10:00:00+00:00",),
        open_work=1,
    )
    for index in range(49):
        _seed_candidate(
            ffl_db,
            source.id,
            f"bulk-{index:02d}",
            visit_times=(f"2026-06-{(index % 28) + 1:02d}T10:00:00+00:00",),
        )

    queue = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)

    assert len(queue) == 50
    assert [row["place"]["village"] for row in queue[:4]] == [
        "Village open-new",
        "Village open-old",
        "Village closed-newer-registration",
        "Village closed-new",
    ]
    assert ffl_db.execute("SELECT COUNT(*) FROM farm_truth_review_cases").fetchone()[0] == 53


def test_candidate_fingerprint_is_stable_and_changes_with_supporting_receipt(
    ffl_db, farm_truth_context
):
    actor, unit, season, source = farm_truth_context
    _seed_candidate(ffl_db, source.id, "fingerprint")

    first = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)
    replay = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)
    ffl_db.execute(
        "UPDATE trackwick_tasks SET source_fingerprint = ? WHERE id = 'visit-fingerprint-0'",
        (_fingerprint("changed source receipt"),),
    )
    ffl_db.commit()
    changed = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)
    ffl_db.execute(
        "UPDATE trackwick_tasks SET source_fingerprint = ? WHERE id = 'visit-fingerprint-0'",
        (_fingerprint("task:visit-fingerprint-0"),),
    )
    ffl_db.commit()
    reverted = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)

    assert replay == first
    assert changed[0]["id"] != first[0]["id"]
    assert len(changed) == 1
    assert reverted == first
    assert list_farm_truth_case_summaries(ffl_db) == reverted
    assert ffl_db.execute("SELECT COUNT(*) FROM farm_truth_review_cases").fetchone()[0] == 2


@pytest.mark.parametrize("ineligibility", ["outside_season", "invalid_visit"])
def test_refresh_removes_open_case_from_current_queue_when_visit_becomes_ineligible(
    ffl_db, farm_truth_context, ineligibility
):
    actor, unit, season, source = farm_truth_context
    _seed_candidate(ffl_db, source.id, "stale")
    case_id = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)[0]["id"]
    if ineligibility == "outside_season":
        ffl_db.execute(
            "UPDATE trackwick_visits SET observed_at = '2026-05-31T10:00:00+00:00' "
            "WHERE task_id = 'visit-stale-0'"
        )
    else:
        ffl_db.execute(
            "UPDATE trackwick_visits SET data_quality_status = 'incomplete' "
            "WHERE task_id = 'visit-stale-0'"
        )
    ffl_db.commit()

    refreshed = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)

    assert refreshed == []
    assert list_farm_truth_case_summaries(ffl_db) == []
    assert get_farm_truth_case_detail(ffl_db, case_id) is None
    stored = repository.get_farm_truth_case(ffl_db, case_id)
    assert stored is not None and stored.status == "open"
    assert ffl_db.execute("SELECT COUNT(*) FROM farm_truth_review_cases").fetchone()[0] == 1


def test_refresh_validates_selected_season_and_actor(ffl_db, farm_truth_context):
    actor, unit, season, source = farm_truth_context
    other_unit = repository.create_operating_unit(ffl_db, "Other unit")
    _seed_candidate(ffl_db, source.id, "valid")

    with pytest.raises(ValueError, match="season does not belong to operating unit"):
        refresh_farm_truth_cases(ffl_db, other_unit.id, season.id, actor.id)
    with pytest.raises(ValueError, match="actor does not exist"):
        refresh_farm_truth_cases(ffl_db, unit.id, season.id, "missing-actor")


def test_owner_inbox_serializer_returns_only_owned_safe_needs_evidence_cases(
    ffl_db, farm_truth_context
):
    actor, unit, season, source = farm_truth_context
    _seed_candidate(ffl_db, source.id, "inbox")
    case_id = refresh_farm_truth_cases(ffl_db, unit.id, season.id, actor.id)[0]["id"]
    repository.mark_farm_truth_case_needs_evidence(
        ffl_db,
        case_id,
        actor.id,
        "plot_area",
        "Call farmer at 9999999999 to confirm the raw source answer",
    )
    other_owner = repository.create_person(ffl_db, "Other owner", "operations_lead")

    inbox = list_farm_truth_inbox_items(ffl_db, actor.id)

    assert inbox == [{
        "id": case_id,
        "status": "needs_evidence",
        "title": "Farm Truth evidence needed",
        "missing_evidence_kind": "plot_area",
        "reason": "Confirm plot area",
        "place": {
            "village": "Village inbox",
            "block": "Gabhana",
            "district": "Aligarh",
        },
        "farmer_display_name": "Farmer inbox",
    }]
    assert "9999999999" not in json.dumps(inbox)
    assert "raw source answer" not in json.dumps(inbox)
    assert list_farm_truth_inbox_items(ffl_db, other_owner.id) == []
