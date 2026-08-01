import hashlib

import pytest

from ffl.persistence.repository import (
    create_evidence_artifact,
    create_field_signal,
    create_crop_stage_checkpoint,
    create_harvest_correction,
    create_harvest_record,
    create_import_batch,
    create_operating_unit,
    create_operational_block,
    create_playbook,
    create_regional_signal,
    create_season,
    create_signal_template,
    create_source_registry,
    create_source_run,
    create_trial,
    create_trial_allocation,
    create_trial_conclusion,
    create_trial_confounder,
    create_crop_allocation,
    get_import_batch_by_content_hash,
    get_source_registry_by_key,
    list_source_registry,
    list_trial_allocations,
    list_trial_conclusions,
)
from ffl.persistence.schema import create_schema


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_source_registry_is_idempotent_and_stores_only_a_credentials_reference(ffl_db, owner):
    create_schema(ffl_db)
    source = create_source_registry(
        ffl_db,
        source_key="imd-weather",
        display_name="IMD Weather",
        source_type="official_public_context",
        purpose="regional weather context",
        authority_level="official",
        owner_id=owner.id,
        credentials_reference="secret://ffl/imd/api-key",
        permitted_data_classes=["forecast", "warning"],
        schema_version="2026-08",
        mapping_version="1",
        default_coverage={"country": "IN"},
    )
    duplicate = create_source_registry(
        ffl_db,
        source_key="imd-weather",
        display_name="Changed display name is ignored on retry",
        source_type="official_public_context",
        purpose="regional weather context",
        authority_level="official",
        owner_id=owner.id,
        credentials_reference="secret://ffl/imd/api-key",
        permitted_data_classes=[],
        schema_version="2026-08",
        mapping_version="1",
        default_coverage={},
    )

    columns = {row["name"] for row in ffl_db.execute("PRAGMA table_info(source_registry)")}
    assert duplicate.id == source.id
    assert get_source_registry_by_key(ffl_db, "imd-weather") == source
    assert list_source_registry(ffl_db) == [source]
    assert source.permitted_data_classes == ["forecast", "warning"]
    assert "credentials_reference" in columns
    assert "credentials" not in columns


def test_import_batch_is_idempotent_on_sha256_and_retains_artifact_linkage(ffl_db, owner):
    content_hash = _hash("plot,area\nA,5\n")
    artifact = create_evidence_artifact(
        ffl_db, content_hash, "text/csv", "evidence/land-register.csv", created_by_person_id=owner.id
    )
    batch = create_import_batch(
        ffl_db,
        purpose="land_register",
        content_hash=content_hash,
        evidence_artifact_id=artifact.id,
        mapping_version="land-register-v1",
        owner_id=owner.id,
        profile={"headers": ["plot", "area"]},
    )
    duplicate = create_import_batch(
        ffl_db,
        purpose="land_register",
        content_hash=content_hash,
        evidence_artifact_id=artifact.id,
        mapping_version="land-register-v2",
        owner_id=owner.id,
        profile={},
    )

    assert duplicate.id == batch.id
    assert get_import_batch_by_content_hash(ffl_db, content_hash) == batch
    assert batch.evidence_artifact_id == artifact.id
    assert batch.profile == {"headers": ["plot", "area"]}
    with pytest.raises(ValueError, match="SHA-256"):
        create_import_batch(ffl_db, "land_register", "not-a-hash", artifact.id, "v1", owner.id, {})


def test_harvest_correction_creates_linked_append_only_version(ffl_db, crop_allocation, users):
    original = create_harvest_record(
        ffl_db,
        crop_allocation.id,
        harvest_starts_on="2026-11-05",
        quantity=1000,
        canonical_unit="kg",
        measurement_method="weighbridge",
        quality_metrics={"grade": "A"},
        status="final",
    )
    correction = create_harvest_correction(
        ffl_db,
        original.id,
        corrected_by_person_id=users.manager.id,
        correction_reason="calibrated scale ticket received",
        quantity=980,
        quality_metrics={"grade": "A", "ticket": "WB-22"},
    )

    assert correction.id != original.id
    assert correction.correction_of_id == original.id
    assert correction.corrected_by_person_id == users.manager.id
    assert correction.status == "corrected"
    assert original.quantity == 1000


def test_trial_allocation_and_conclusion_preserve_trial_evidence_and_decision_linkage(
    ffl_db, crop_allocation, users
):
    evidence = create_evidence_artifact(
        ffl_db, _hash("trial observations"), "text/plain", "evidence/trial-observations.txt",
        created_by_person_id=users.lead.id,
    )
    playbook = create_playbook(
        ffl_db, "Rice irrigation cadence", 1, users.lead.id, {"cadence_days": 5}
    )
    trial = create_trial(
        ffl_db,
        name="Rice cadence pilot",
        hypothesis="A five-day cadence reduces water stress",
        owner_id=users.lead.id,
        protocol_version="1",
        decision_question="Should FFL promote the cadence?",
        treatment={"cadence_days": 5},
        comparator={"cadence_days": 7},
        eligibility_rule={"crop": "Rice"},
        measurements=["stress score"],
        guardrails=["no quality decline"],
    )
    allocation = create_trial_allocation(ffl_db, trial.id, crop_allocation.id, "treatment")
    conclusion = create_trial_conclusion(
        ffl_db,
        trial.id,
        reviewer_id=users.lead.id,
        status="approved",
        result={"stress_score_change": -1},
        confidence_level="medium",
        limitations=["one allocation"],
        evidence_artifact_id=evidence.id,
        playbook_id=playbook.id,
        playbook_decision="promote",
        approved_at="2026-12-01T12:00:00+00:00",
    )

    assert list_trial_allocations(ffl_db, trial.id) == [allocation]
    assert list_trial_conclusions(ffl_db, trial.id) == [conclusion]
    assert conclusion.evidence_artifact_id == evidence.id
    assert conclusion.playbook_id == playbook.id


@pytest.mark.parametrize("credentials_reference", ["raw-api-token", "secret://", "env://has space"])
def test_source_registry_rejects_raw_or_malformed_credentials_references(
    ffl_db, owner, credentials_reference
):
    with pytest.raises(ValueError, match="credentials_reference"):
        create_source_registry(
            ffl_db, "bad-source-" + credentials_reference[:3], "Bad", "official", "context",
            "official", owner.id, [], "1", "1", {}, credentials_reference=credentials_reference,
        )


def test_regional_signal_rejects_source_run_from_another_source(ffl_db, owner):
    source_a = create_source_registry(
        ffl_db, "source-a", "Source A", "official", "context", "official", owner.id, [], "1", "1", {}
    )
    source_b = create_source_registry(
        ffl_db, "source-b", "Source B", "official", "context", "official", owner.id, [], "1", "1", {}
    )
    run_b = create_source_run(ffl_db, source_b.id, {"district": "A"}, "1")

    with pytest.raises(ValueError, match="source_run must belong"):
        create_regional_signal(
            ffl_db, source_a.id, "imd-1", "District A", "forecast", "2026-08-01T00:00:00+00:00",
            {"rain_mm": 5}, {"district": "A"}, "forecast", source_run_id=run_b.id,
        )


def test_field_signal_and_checkpoint_require_matching_published_template(ffl_db, crop_allocation, owner):
    published = create_signal_template(
        ffl_db, "stage-check", 1, "published", "[]", owner.id, "2026-08-01T00:00:00+00:00"
    )
    draft = create_signal_template(
        ffl_db, "draft-stage-check", 1, "draft", "[]", owner.id, "2026-08-01T00:00:00+00:00"
    )
    signal = create_field_signal(
        ffl_db, crop_allocation.id, published.id, 1, "2026-08-01T00:00:00+00:00", owner.id, {"stage": "tillering"}
    )

    assert signal.template_id == published.id
    with pytest.raises(ValueError, match="ID and version do not match"):
        create_field_signal(
            ffl_db, crop_allocation.id, published.id, 2, "2026-08-01T00:00:00+00:00", owner.id, {}
        )
    with pytest.raises(ValueError, match="ID and version do not match"):
        create_crop_stage_checkpoint(
            ffl_db, crop_allocation.id, "tillering", "2026-08-03", {}, published.id, 2
        )
    with pytest.raises(ValueError, match="must be published"):
        create_crop_stage_checkpoint(
            ffl_db, crop_allocation.id, "tillering", "2026-08-03", {}, draft.id, 1
        )
    with pytest.raises(ValueError, match="must be published"):
        create_field_signal(
            ffl_db, crop_allocation.id, draft.id, 1, "2026-08-01T00:00:00+00:00", owner.id, {}
        )


def test_harvest_record_rejects_correction_from_different_allocation(ffl_db, crop_allocation, users):
    original = create_harvest_record(
        ffl_db, crop_allocation.id, "2026-11-05", 1000, "kg", "weighbridge", {}, status="final"
    )
    unit = create_operating_unit(ffl_db, "Other Farm")
    block = create_operational_block(ffl_db, unit.id, "Other Block", 1.0)
    season = create_season(ffl_db, unit.id, "Other Season", "2026-06-01", "2026-11-30")
    other_allocation = create_crop_allocation(
        ffl_db, unit.id, block.id, season.id, "Rice", None, 1.0
    )

    with pytest.raises(ValueError, match="predecessor allocation"):
        create_harvest_record(
            ffl_db, other_allocation.id, "2026-11-05", 990, "kg", "weighbridge", {},
            status="corrected", correction_of_id=original.id, corrected_by_person_id=users.manager.id,
            correction_reason="wrong allocation",
        )


def test_json_serialization_rejects_non_portable_nan(ffl_db, owner):
    with pytest.raises(ValueError, match="NaN or infinity"):
        create_trial(
            ffl_db, "NaN trial", "test JSON", owner.id, "1", "should fail",
            {"rate": float("nan")}, {}, {}, [], [],
        )


def test_trial_confounder_allocation_must_participate_in_named_trial(ffl_db, crop_allocation, owner):
    participating_trial = create_trial(
        ffl_db, "Participating", "test", owner.id, "1", "decision", {}, {}, {}, [], []
    )
    other_trial = create_trial(
        ffl_db, "Other", "test", owner.id, "1", "decision", {}, {}, {}, [], []
    )
    create_trial_allocation(ffl_db, participating_trial.id, crop_allocation.id, "treatment")

    with pytest.raises(ValueError, match="must participate"):
        create_trial_confounder(
            ffl_db, other_trial.id, "weather", "rain", "2026-08-01T00:00:00+00:00", owner.id,
            allocation_id=crop_allocation.id,
        )


def test_import_batch_lifecycle_requires_consistent_review_and_publish_timestamps(ffl_db, owner):
    content_hash = _hash("lifecycle")
    artifact = create_evidence_artifact(ffl_db, content_hash, "text/csv", "evidence/lifecycle.csv")

    with pytest.raises(ValueError, match="published imports require"):
        create_import_batch(
            ffl_db, "land_register", content_hash, artifact.id, "1", owner.id, {}, status="published",
            published_at="2026-08-01T00:00:00+00:00",
        )
    with pytest.raises(ValueError, match="received and profiled"):
        create_import_batch(
            ffl_db, "land_register", content_hash, artifact.id, "1", owner.id, {},
            reviewed_at="2026-08-01T00:00:00+00:00",
        )


def test_shared_schema_has_v1_query_indexes(ffl_db):
    indexes = {row["name"] for row in ffl_db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}

    assert {
        "idx_import_batches_purpose_received",
        "idx_season_reviews_allocation_created",
        "idx_trial_confounders_trial",
    } <= indexes
