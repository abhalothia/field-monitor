import re
from pathlib import Path

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.seed import seed_pilot


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0013_agro_vc_runtime_operating_reads.sql"
FARM_TRUTH_HARDENING = ROOT / "db" / "postgres" / "0015_agro_farm_truth_hardening.sql"
PROFILE_RUNTIME_GRANTS = ROOT / "db" / "postgres" / "0017_agro_profile_runtime_read_grants.sql"


def test_profile_runtime_grant_exposes_only_safe_summary_columns():
    sql = PROFILE_RUNTIME_GRANTS.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    assert (
        "GRANT SELECT (id, allocation_id, title, status) "
        "ON TABLE agro_work_items TO agro_vc_runtime;"
    ) in compact
    assert (
        "GRANT SELECT (allocation_id, observed_at, received_at, actor_id, status, created_at) "
        "ON TABLE agro_field_signals TO agro_vc_runtime;"
    ) in compact
    assert compact.count("GRANT SELECT (") == 2
    for forbidden in (
        "values_json",
        "evidence_artifact_id",
        "owner_id",
        "template_id",
        "due_at",
        "GRANT ALL",
        "GRANT SELECT ON TABLE",
        "GRANT INSERT",
        "GRANT UPDATE",
        "GRANT DELETE",
        "GRANT USAGE",
        "GRANT CREATE",
        " TO PUBLIC",
        " TO anon",
        " TO authenticated",
    ):
        assert forbidden not in sql


def test_runtime_work_summary_uses_only_granted_columns(tmp_path):
    app = create_app(str(tmp_path / "runtime-grants.db"))
    with TestClient(app) as client:
        seed_pilot(app.state.conn)

        response = client.get("/api/v1/runtime")

    assert response.status_code == 200
    assert response.json()["work_items"]
    assert all(
        set(item) == {"id", "allocation_id", "title", "status"}
        for item in response.json()["work_items"]
    )


def test_vc_runtime_migration_repairs_only_the_existing_server_operating_lane():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "GRANT SELECT, INSERT, UPDATE ON TABLE" in sql
    assert "agro_field_information_requests" in sql
    assert "agro_trackwick_parties" in sql
    assert "TO agro_vc_runtime" in sql
    assert "DELETE" in sql  # documented as intentionally absent authority
    assert "GRANT DELETE" not in sql
    assert "GRANT ALL" not in sql


def test_farm_truth_runtime_grants_are_exact_and_reviewed_links_are_immutable():
    sql = FARM_TRUTH_HARDENING.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    for source_table in (
        "agro_source_registry",
        "agro_trackwick_parties",
        "agro_trackwick_tasks",
        "agro_trackwick_visits",
        "agro_trackwick_registrations",
        "agro_trackwick_registration_plots",
        "agro_trackwick_task_plot_links",
    ):
        assert source_table in sql
    for canonical_table in (
        "agro_land_parcels",
        "agro_operational_blocks",
        "agro_block_parcels",
        "agro_rights_to_operate",
        "agro_crop_allocations",
        "agro_people",
        "agro_person_operating_relationships",
        "agro_trackwick_party_person_links",
        "agro_trackwick_plot_operating_links",
        "agro_trackwick_task_allocation_links",
        "agro_audit_events",
        "agro_farm_truth_review_cases",
    ):
        assert canonical_table in sql

    assert "GRANT SELECT ON TABLE" in compact
    assert "GRANT INSERT ON TABLE" in compact
    assert (
        "GRANT INSERT, UPDATE ON TABLE agro_trackwick_task_plot_links "
        "TO agro_vc_runtime;"
    ) in compact
    assert "provider_plot_reference TEXT" in compact
    assert "UNIQUE (task_id)" in compact
    assert "GRANT UPDATE (" in compact
    assert "TO agro_vc_runtime" in compact
    assert "GRANT ALL" not in compact
    assert "GRANT DELETE" not in compact
    assert "GRANT USAGE ON SCHEMA" not in compact
    assert "GRANT CREATE ON SCHEMA" not in compact
    assert " TO PUBLIC" not in compact
    assert " TO anon" not in compact
    assert " TO authenticated" not in compact
    assert "REVOKE UPDATE ON TABLE agro_trackwick_party_person_links" in compact
    assert "OLD.link_status = 'reviewed'" in sql
    for link_table in (
        "agro_trackwick_party_person_links",
        "agro_trackwick_plot_operating_links",
        "agro_trackwick_task_allocation_links",
    ):
        assert "ON " + link_table in sql

    table_grants: dict[str, set[str]] = {}
    for privilege, table_list in re.findall(
        r"GRANT\s+(SELECT|INSERT)\s+ON\s+TABLE\s+(.*?)\s+TO\s+agro_vc_runtime\s*;",
        sql,
        flags=re.DOTALL,
    ):
        table_grants.setdefault(privilege, set()).update(
            item.strip() for item in table_list.split(",")
        )
    assert table_grants["SELECT"] == {
        "agro_operating_units",
        "agro_seasons",
        "agro_source_registry",
        "agro_trackwick_parties",
        "agro_trackwick_tasks",
        "agro_trackwick_visits",
        "agro_trackwick_registrations",
        "agro_trackwick_registration_plots",
        "agro_trackwick_task_plot_links",
        "agro_land_parcels",
        "agro_operational_blocks",
        "agro_block_parcels",
        "agro_rights_to_operate",
        "agro_crop_allocations",
        "agro_people",
        "agro_person_operating_relationships",
        "agro_trackwick_party_person_links",
        "agro_trackwick_plot_operating_links",
        "agro_trackwick_task_allocation_links",
        "agro_audit_events",
        "agro_farm_truth_review_cases",
    }
    assert table_grants["INSERT"] == {
        "agro_land_parcels",
        "agro_operational_blocks",
        "agro_block_parcels",
        "agro_rights_to_operate",
        "agro_crop_allocations",
        "agro_people",
        "agro_person_operating_relationships",
        "agro_trackwick_party_person_links",
        "agro_trackwick_plot_operating_links",
        "agro_trackwick_task_allocation_links",
        "agro_audit_events",
        "agro_farm_truth_review_cases",
    }
    source_writes = re.findall(
        r"GRANT\s+INSERT,\s*UPDATE\s+ON\s+TABLE\s+(.*?)\s+TO\s+agro_vc_runtime\s*;",
        sql,
        flags=re.DOTALL,
    )
    assert [item.strip() for item in source_writes] == [
        "agro_trackwick_task_plot_links"
    ]
    update = re.search(
        r"GRANT\s+UPDATE\s*\((.*?)\)\s+ON\s+agro_farm_truth_review_cases",
        sql,
        flags=re.DOTALL,
    )
    assert update is not None
    assert {item.strip() for item in update.group(1).split(",")} == {
        "status",
        "evidence_summary_json",
        "review_reason",
        "missing_evidence_kind",
        "owner_person_id",
        "reviewed_by_person_id",
        "reviewed_at",
        "accepted_land_parcel_id",
        "accepted_operational_block_id",
        "accepted_crop_allocation_id",
        "accepted_grower_person_id",
        "accepted_field_worker_person_id",
        "updated_at",
    }
