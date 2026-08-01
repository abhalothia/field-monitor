import hashlib
from datetime import datetime, timezone

import pytest

from ffl.external_data.geography import (
    ReviewedVillageFinderRelease,
    fetch_reviewed_village_finder_csv,
    parse_village_finder_csv,
)
from ffl.external_data.imd import IMDAccessReview, IMDDryRunAdapter
from ffl.services import sources


CSV = """State,District,District Code,Mandal,Mandal Code,Village,Village (Native),Native Source,Village Code,Pincode,Category,Status
Andhra Pradesh,Demo District,0506,Demo Mandal,05070,Demo Village,డెమో గ్రామం,authoritative,000123,500001,,
Andhra Pradesh,Demo District,0506,Demo Mandal,05070,Second Village,,,000124,,,
""".encode("utf-8")
FIXED_NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def _release(content=CSV):
    return ReviewedVillageFinderRelease(
        state_slug="andhra_pradesh",
        revision="eddc9c373d79af0f162aaaddfe27e6f2227f99bb",
        content_sha256=hashlib.sha256(content).hexdigest(),
        review_reference="geo-review-2026-08-01",
    )


def test_reviewed_village_finder_release_is_pinned_and_parses_leading_zero_codes():
    calls = []
    dataset, content = fetch_reviewed_village_finder_csv(
        _release(), opener=lambda url: calls.append(url) or CSV,
    )
    imported = parse_village_finder_csv(dataset, content)

    assert calls == [
        "https://raw.githubusercontent.com/mchittineni/india-village-finder/"
        "eddc9c373d79af0f162aaaddfe27e6f2227f99bb/andhra_pradesh/data/andhra_pradesh_villages.csv"
    ]
    assert [(item.kind, item.code) for item in imported.references] == [
        ("district", "0506"), ("subdistrict", "05070"), ("village", "000123"), ("village", "000124"),
    ]
    candidate = imported.import_row_candidates()[2]
    assert candidate["pincode"] == "500001"
    assert candidate["native_name_source"] == "authoritative"
    assert candidate["review_reference"] == "geo-review-2026-08-01"


def test_village_finder_rejects_unreviewed_or_inconsistent_content():
    with pytest.raises(ValueError, match="immutable git SHA"):
        fetch_reviewed_village_finder_csv(
            ReviewedVillageFinderRelease("andhra_pradesh", "main", "0" * 64, "review"),
            opener=lambda _url: CSV,
        )
    with pytest.raises(ValueError, match="hash does not match"):
        fetch_reviewed_village_finder_csv(
            ReviewedVillageFinderRelease("andhra_pradesh", "eddc9c373d79af0f162aaaddfe27e6f2227f99bb", "0" * 64, "review"),
            opener=lambda _url: CSV,
        )
    conflicting = CSV + b"Andhra Pradesh,Other District,0999,Demo Mandal,05070,Third Village,,,000125,500001,,\n"
    dataset, _ = fetch_reviewed_village_finder_csv(
        _release(conflicting), opener=lambda _url: conflicting,
    )
    with pytest.raises(ValueError, match="conflicting parent"):
        parse_village_finder_csv(dataset, conflicting)


def test_imd_dry_run_has_a_non_secret_registration_contract_and_never_calls_network(ffl_db, owner):
    review = IMDAccessReview(
        endpoint="https://api.imd.gov.in",
        product_identifier="district-warning-product-to-be-reviewed",
        egress_identity="hetzner-static-egress-1",
        review_reference="imd-access-review-2026-08-01",
        cache_ttl_seconds=300,
    )
    fields = review.source_registration_spec()
    assert fields["enabled"] is False
    assert "imd-access-review-2026-08-01" in fields["license_notes"]
    assert "credentials_reference" not in fields
    fields["enabled"] = True  # A test-only source registration; the adapter remains network-free.
    source = sources.register_source(ffl_db, owner_id=owner.id, **fields)

    run = sources.refresh_source(
        ffl_db,
        source.source_key,
        adapters=sources.AdapterRegistry([IMDDryRunAdapter(review)]),
        now=FIXED_NOW,
    )

    assert run.status == "unavailable"
    assert run.error_summary == "imd_network_not_enabled"
    assert sources.regional_context(ffl_db, "any-district", now=FIXED_NOW)["signals"] == []


def test_imd_dry_run_refuses_non_official_endpoint_or_unreviewed_access_plan():
    with pytest.raises(ValueError, match="api.imd.gov.in"):
        IMDAccessReview(
            "https://weather.example.invalid", "product", "egress", "review", 300,
        ).validate()
    with pytest.raises(ValueError, match="review reference"):
        IMDAccessReview(
            "https://api.imd.gov.in", "product", "egress", "", 300,
        ).validate()
    with pytest.raises(ValueError, match="cache TTL"):
        IMDAccessReview(
            "https://api.imd.gov.in", "product", "egress", "review", 10,
        ).validate()
