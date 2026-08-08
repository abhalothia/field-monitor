import os

import pytest

from ffl.persistence.database import open_connection
from ffl.persistence.repository import (
    create_crop_allocation,
    create_operating_unit,
    create_operational_block,
    create_person,
    create_season,
)
from ffl.persistence.schema import create_schema


os.environ.setdefault(
    "FFL_COMMUNICATION_CONTEXT_TOKEN_KEY",
    "test-only-communications-context-key-32b",
)


@pytest.fixture
def ffl_db():
    conn = open_connection(":memory:")
    create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def users(ffl_db):
    return type("Users", (), {
        "manager": create_person(ffl_db, "Farm Manager", "farm_manager"),
        "operator": create_person(ffl_db, "Field Operator", "field_operator"),
        "lead": create_person(ffl_db, "Operations Lead", "operations_lead"),
    })()


@pytest.fixture
def crop_allocation(ffl_db):
    unit = create_operating_unit(ffl_db, "FFL Pilot Farm")
    block = create_operational_block(ffl_db, unit.id, "North Block", 5.0)
    season = create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    return create_crop_allocation(ffl_db, unit.id, block.id, season.id, "Rice", "Pusa 1121", 5.0)


@pytest.fixture
def owner(ffl_db):
    return create_person(ffl_db, "Template Owner", "agronomist")
