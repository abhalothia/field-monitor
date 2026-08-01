import pytest

from ffl.persistence.repository import (
    create_crop_allocation,
    create_land_parcel,
    create_operating_unit,
    create_operational_block,
    link_block_parcel,
    create_right_to_operate,
    create_season,
)


def test_partial_crop_allocation_preserves_block_history(ffl_db):
    unit = create_operating_unit(ffl_db, "Fortune Pilot")
    parcel = create_land_parcel(ffl_db, unit.id, "Parcel A", 10.0)
    block = create_operational_block(ffl_db, unit.id, "North Block", 10.0)
    link_block_parcel(ffl_db, block.id, parcel.id)
    create_right_to_operate(ffl_db, parcel.id, "leased", "2026-01-01", "2027-01-01")
    season = create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")

    allocation = create_crop_allocation(
        ffl_db, unit.id, block.id, season.id, "Rice", "Pusa 1121", 4.0
    )

    assert allocation.area_hectares == 4.0
    assert allocation.operational_block_id == block.id


def test_overlapping_active_allocations_are_rejected(ffl_db):
    unit = create_operating_unit(ffl_db, "Fortune Pilot")
    block = create_operational_block(ffl_db, unit.id, "North Block", 5.0)
    season = create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    create_crop_allocation(ffl_db, unit.id, block.id, season.id, "Rice", "Pusa 1121", 4.0)

    with pytest.raises(ValueError, match="exceeds available block area"):
        create_crop_allocation(ffl_db, unit.id, block.id, season.id, "Mint", None, 2.0)
