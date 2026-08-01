from ffl.persistence.repository import list_work_items
from ffl.seed import seed_pilot


def test_seed_creates_active_work_for_the_pilot(ffl_db):
    seeded = seed_pilot(ffl_db)

    work = list_work_items(ffl_db, seeded["allocation_id"])

    assert len(work) == 1
    assert work[0].title == "Inspect irrigation readiness"
    assert work[0].status == "planned"


def test_seed_returns_the_pilot_roles(ffl_db):
    seeded = seed_pilot(ffl_db)

    assert set(seeded) == {
        "operating_unit_id",
        "allocation_id",
        "manager_id",
        "operator_id",
        "lead_id",
    }


def test_seed_is_repeatable_without_duplicate_pilot_work(ffl_db):
    first = seed_pilot(ffl_db)
    second = seed_pilot(ffl_db)

    assert second == first
    assert len(list_work_items(ffl_db, first["allocation_id"])) == 1
