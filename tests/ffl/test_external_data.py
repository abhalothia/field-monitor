import hashlib

import pytest

from ffl.external_data.catalog import external_data_sources
from ffl.external_data.geography import (
    GeographyDataset,
    fetch_village_finder_csv,
    parse_village_finder_csv,
    village_finder_raw_url,
)
from pathlib import Path


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "db" / "postgres" / "0100_ffl_external_data.sql"


CSV = """State,District,District Code,Mandal,Mandal Code,Village,Village (Native),Native Source,Village Code,Pincode,Category,Status
Andhra Pradesh,Demo District,0506,Demo Mandal,05070,Demo Village,డెమో గ్రామం,authoritative,000123,500001,,
Andhra Pradesh,Demo District,0506,Demo Mandal,05070,Second Village,,,000124,,,
""".encode("utf-8")


def _dataset(content=CSV):
    return GeographyDataset(
        "andhra_pradesh", "Andhra Pradesh", "28", "eddc9c373d79af0f162aaaddfe27e6f2227f99bb",
        hashlib.sha256(content).hexdigest(), "https://raw.githubusercontent.com/mchittineni/india-village-finder/eddc9c373d79af0f162aaaddfe27e6f2227f99bb/andhra_pradesh/data/andhra_pradesh_villages.csv",
        "attribution",
    )


def test_village_finder_parser_builds_a_strict_hierarchy_and_preserves_codes():
    imported = parse_village_finder_csv(_dataset(), CSV)

    assert [(place.kind, place.code) for place in imported.places] == [
        ("district", "0506"), ("subdistrict", "05070"), ("village", "000123"), ("village", "000124"),
    ]
    assert imported.village("000123").parent_code == "05070"
    assert imported.village("000123").native_name_source == "authoritative"
    assert imported.village("000124").native_name is None
    assert imported.village("000123").pincode == "500001"


def test_village_finder_parser_rejects_ambiguous_codes_and_bad_state():
    conflicting = CSV + b"Andhra Pradesh,Other District,0999,Demo Mandal,05070,Third Village,,,000125,500001,,\n"
    with pytest.raises(ValueError, match="conflicting parent"):
        parse_village_finder_csv(_dataset(conflicting), conflicting)

    wrong_state = CSV.replace(b"Andhra Pradesh", b"Telangana", 1)
    with pytest.raises(ValueError, match="state does not match"):
        parse_village_finder_csv(_dataset(wrong_state), wrong_state)


def test_pinned_fetch_refuses_mutable_revision_or_changed_content():
    with pytest.raises(ValueError, match="immutable git SHA"):
        village_finder_raw_url("andhra_pradesh", "main")

    with pytest.raises(ValueError, match="content hash does not match"):
        fetch_village_finder_csv(
            "andhra_pradesh", "eddc9c373d79af0f162aaaddfe27e6f2227f99bb", "0" * 64,
            opener=lambda _url: CSV,
        )

    dataset, content = fetch_village_finder_csv(
        "andhra_pradesh", "eddc9c373d79af0f162aaaddfe27e6f2227f99bb", hashlib.sha256(CSV).hexdigest(),
        opener=lambda _url: CSV,
    )
    assert content == CSV
    assert dataset.source_url.startswith("https://raw.githubusercontent.com/")


def test_three_phase_catalog_keeps_every_provider_disabled_until_its_admission_gate():
    assert [source.source_key for source in external_data_sources(1)] == [
        "village-finder-lgd", "soil-lab-first-party",
    ]
    assert [source.source_key for source in external_data_sources(2)] == ["imd-weather"]
    assert all(source.enabled_by_default is False for source in external_data_sources())


def test_postgres_extension_depends_on_private_canonical_source_contract():
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "apply after 0001_ffl_private_schema.sql" in migration.lower()
    assert "references ffl.source_registry(id)" in migration
    assert "references ffl.operating_units(id)" in migration
    assert "revoke all on all tables in schema ffl from anon" in migration
    assert "create table if not exists ffl.ext_sources" not in migration
    assert "create table if not exists ffl.ext_source_runs" not in migration
    assert "public.ext_" not in migration
