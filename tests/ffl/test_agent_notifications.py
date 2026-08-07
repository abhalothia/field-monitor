from ffl.persistence import repository
from ffl.services import agent_notifications
from fastapi.testclient import TestClient
from ffl.app import create_app


def _seed_source(conn):
    owner = repository.create_person(conn, "Manager", "operations_lead")
    now = "2026-08-01T12:00:00+00:00"
    conn.execute("""INSERT INTO source_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
        "source-1", "trackwick-fortune-paddy", "Private field data", "partner", "farm context", "source", owner.id,
        None, None, "[]", None, None, "v1", "v1", "{}", 1, now,
    ))
    for party_id, name in (("farmer-visit", "Visited farmer"), ("farmer-new", "New farmer"), ("farmer-stale", "Stale farmer")):
        conn.execute("""INSERT INTO trackwick_parties (id, source_id, party_kind, provider_identifier,
            display_name, source_fingerprint, mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
            VALUES (?, 'source-1', 'farmer', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
            (party_id, party_id, name, "a" * 64, now, now, now))
    conn.execute("""INSERT INTO trackwick_tasks (id, source_id, provider_task_id, farmer_party_id, task_type, task_status,
        provider_created_at, provider_completed_at, source_fingerprint, mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('visit-task', 'source-1', 'visit-1', 'farmer-visit', 'Visit', 'completed', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (now, now, "b" * 64, now, now, now))
    conn.execute("""INSERT INTO trackwick_visits (task_id, source_id, observed_at, kit_status, source_fingerprint,
        mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('visit-task', 'source-1', ?, 'unknown', ?, 'v1', 'valid', ?, ?, ?)""", (now, "c" * 64, now, now, now))
    conn.execute("""INSERT INTO trackwick_visit_findings (id, visit_task_id, source_id, finding_kind, reported_value,
        source_field, declared_severity, observed_at, source_fingerprint, mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('disease-1', 'visit-task', 'source-1', 'disease', 'blast', 'disease', 'high', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (now, "d" * 64, now, now, now))
    conn.execute("""INSERT INTO trackwick_tasks (id, source_id, provider_task_id, farmer_party_id, task_type, task_status,
        provider_created_at, provider_completed_at, source_fingerprint, mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('registration-task', 'source-1', 'registration-1', 'farmer-new', 'Registration', 'completed', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (now, now, "e" * 64, now, now, now))
    conn.execute("""INSERT INTO trackwick_registrations (id, task_id, source_id, farmer_party_id, registration_status,
        source_fingerprint, mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at)
        VALUES ('registration-1', 'registration-task', 'source-1', 'farmer-new', 'completed', ?, 'v1', 'valid', ?, ?, ?)""",
        ("f" * 64, now, now, now))
    conn.commit()
    return owner


def test_agents_return_four_plain_checks_and_save_custom_rule(ffl_db):
    owner = _seed_source(ffl_db)
    checks = agent_notifications.default_agents(ffl_db)
    assert [item["name"] for item in checks] == [
        "Paddy — no visits", "Farmer — no visits", "Farmer — no update", "Disease watch",
    ]
    assert checks[0]["count"] == 1
    assert checks[1]["count"] == 2
    assert checks[3]["count"] == 1

    created = repository.create_agent_notification(
        ffl_db, owner.id, "Priority farmers", "Tell me when a farmer has repeated disease reports.",
    )
    changed = repository.update_agent_notification(ffl_db, created.id, enabled=False)
    assert changed.enabled is False
    assert agent_notifications.board(ffl_db)["custom_agents"] == [{
        "id": created.id, "name": "Priority farmers",
        "instruction": "Tell me when a farmer has repeated disease reports.",
        "enabled": False, "updated_at": changed.updated_at,
    }]


def test_agent_routes_are_manager_only_and_allow_a_saved_rule(tmp_path):
    app = create_app(str(tmp_path / "agents.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Manager", "operations_lead")
        app.state.manager_person_id = manager.id
        assert client.get("/api/v1/agents").status_code == 403
        created = client.post("/api/v1/agents", headers={"X-FFL-Manager-Token": "manager-secret"}, json={
            "name": "Priority farmers", "instruction": "Tell me when disease reports repeat.",
        })
        assert created.status_code == 201
        agent_id = created.json()["id"]
        updated = client.patch(f"/api/v1/agents/{agent_id}", headers={"X-FFL-Manager-Token": "manager-secret"}, json={"enabled": False})
        board = client.get("/api/v1/agents", headers={"X-FFL-Manager-Token": "manager-secret"})

    assert updated.json()["enabled"] is False
    assert board.json()["custom_agents"][0]["name"] == "Priority farmers"
