from ffl.persistence.repository import create_operating_unit, create_person
from ffl.services import farm_candidate_reviews
from ffl.persistence import repository


def _seed_registration(conn):
    owner = create_person(conn, "Source owner", "operations_lead")
    conn.execute("""INSERT INTO source_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
        "source-1", "trackwick", "TrackWick", "partner", "farm context", "source", owner.id,
        None, None, "[]", None, None, "v1", "v1", "{}", 1, "2026-08-04T12:00:00+00:00",
    ))
    now = "2026-08-04T12:00:00+00:00"
    conn.execute("""INSERT INTO trackwick_parties (id, source_id, party_kind, provider_identifier,
        display_name, source_fingerprint, mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('farmer-1', 'source-1', 'farmer', 'provider-farmer', 'Source grower', ?, 'v1', 'valid', ?, ?, ?)""",
        ("b" * 64, now, now, now))
    conn.execute("""INSERT INTO trackwick_tasks (id, source_id, provider_task_id, farmer_party_id,
        task_type, task_status, provider_created_at, provider_completed_at, source_fingerprint, mapping_version,
        data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('task-1', 'source-1', 'provider-task', 'farmer-1', 'Registration', 'completed', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (now, now, "c" * 64, now, now, now))
    conn.execute("""INSERT INTO trackwick_registrations (id, task_id, source_id, farmer_party_id,
        registration_status, village_name, block_name, district_name, reported_total_area_acres, reported_plot_count,
        source_fingerprint, mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('registration-1', 'task-1', 'source-1', 'farmer-1', 'completed', 'Village', 'Block', 'District', 2.5, 1, ?, 'v1', 'valid', ?, ?, ?)""",
        ("d" * 64, now, now, now))
    conn.commit()
    return owner


def test_registration_review_creates_only_farm_and_grower(ffl_db):
    reviewer = _seed_registration(ffl_db)
    unit = create_operating_unit(ffl_db, "Fortune Farms")
    cases = farm_candidate_reviews.refresh_cases(ffl_db)
    assert len(cases) == 1
    case = repository.accept_farm_candidate_review_case(
        ffl_db, cases[0]["id"], reviewer.id, unit.id, "Village, Block, District", "2026-08-01", cases[0]["updated_at"],
    )
    assert case.status == "accepted"
    assert ffl_db.execute("SELECT count(*) FROM farms").fetchone()[0] == 1
    assert ffl_db.execute("SELECT count(*) FROM farm_grower_relationships").fetchone()[0] == 1
    assert ffl_db.execute("SELECT count(*) FROM operational_blocks").fetchone()[0] == 0
    assert ffl_db.execute("SELECT count(*) FROM land_parcels").fetchone()[0] == 0
    assert ffl_db.execute("SELECT count(*) FROM crop_allocations").fetchone()[0] == 0
