from pathlib import Path

from ffl.services.access import provision_initial_fortune_team


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0010_agro_named_access.sql"


def test_named_access_migration_keeps_app_access_separate_from_operational_roles():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS agro_access_memberships" in sql
    assert "access_role IN ('owner', 'admin')" in sql
    assert "identity_status IN ('identity_pending', 'invited', 'active', 'suspended')" in sql
    assert "REVOKE ALL ON TABLE agro_access_memberships FROM PUBLIC" in sql


def test_initial_fortune_team_is_provisioned_once_without_a_login_identity(ffl_db):
    created = provision_initial_fortune_team(ffl_db, observed_at="2026-08-04T12:00:00+00:00")
    replay = provision_initial_fortune_team(ffl_db, observed_at="2026-08-04T13:00:00+00:00")
    rows = ffl_db.execute(
        """SELECT p.name, p.role, m.access_role, m.identity_status
           FROM access_memberships m JOIN people p ON p.id = m.person_id
           ORDER BY p.name"""
    ).fetchall()

    assert len(created) == len(replay) == 3
    assert [dict(row) for row in rows] == [
        {
            "name": "Aakash Bhalothia",
            "role": "operations_lead",
            "access_role": "owner",
            "identity_status": "identity_pending",
        },
        {
            "name": "Ajay Bhalothia",
            "role": "operations_lead",
            "access_role": "owner",
            "identity_status": "identity_pending",
        },
        {
            "name": "Daksh Bhatia",
            "role": "operations_lead",
            "access_role": "admin",
            "identity_status": "identity_pending",
        },
    ]
