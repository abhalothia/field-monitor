from __future__ import annotations

from ffl.persistence import repository
from ffl.services import operating_vocabulary


NOW = "2026-08-08T12:00:00+00:00"


def _seed_vocabulary_source(conn, owner):
    source = repository.create_source_registry(
        conn,
        source_key="vocabulary-source",
        display_name="Vocabulary source",
        source_type="partner",
        purpose="Operating context",
        authority_level="partner",
        owner_id=owner.id,
        permitted_data_classes=["farm_candidate_context"],
        schema_version="v1",
        mapping_version="v1",
        default_coverage={},
        enabled=True,
    )
    conn.execute(
        """INSERT INTO trackwick_tasks (
               id, source_id, provider_task_id, task_type, task_status,
               provider_created_at, provider_completed_at, source_fingerprint,
               mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES ('task-1', ?, 'provider-task-1', 'Farmer Visit', 'completed', ?, ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (source.id, NOW, NOW, "a" * 64, NOW, NOW, NOW),
    )
    conn.execute(
        """INSERT INTO trackwick_visits (
               task_id, source_id, observed_at, kit_status, source_fingerprint,
               mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES ('task-1', ?, ?, 'unknown', ?, 'v1', 'valid', ?, ?, ?)""",
        (source.id, NOW, "b" * 64, NOW, NOW, NOW),
    )
    conn.execute(
        """INSERT INTO trackwick_visit_findings (
               id, visit_task_id, source_id, finding_kind, reported_value, source_field,
               declared_severity, observed_at, source_fingerprint, mapping_version,
               data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES ('finding-1', 'task-1', ?, 'disease', 'Bacterial Leaf Blight',
                     'issue', 'moderate', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (source.id, NOW, "c" * 64, NOW, NOW, NOW),
    )
    conn.execute(
        """INSERT INTO trackwick_crop_inputs (
               id, visit_task_id, source_id, input_kind, event_kind, reported_product,
               source_field, occurred_at, source_fingerprint, mapping_version,
               data_quality_status, first_seen_at, last_seen_at, created_at
           ) VALUES ('input-1', 'task-1', ?, 'pesticide', 'applied', 'Brand X 20 EC',
                     'product', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (source.id, NOW, "d" * 64, NOW, NOW, NOW),
    )
    conn.commit()
    return source


def test_discovery_is_deterministic_and_never_calls_a_model(ffl_db, owner, monkeypatch):
    source = _seed_vocabulary_source(ffl_db, owner)
    monkeypatch.setattr(
        operating_vocabulary.openai_responses,
        "structured_output",
        lambda **_: (_ for _ in ()).throw(AssertionError("source refresh must not call a model")),
    )

    assert operating_vocabulary.refresh_source_vocabulary(ffl_db, source.id) == 3
    rows = ffl_db.execute(
        """SELECT vocabulary_kind, source_context, raw_value, normalized_key,
                  display_label, mapping_state, mapping_method
           FROM operating_vocabulary_terms WHERE source_id = ?
           ORDER BY vocabulary_kind""",
        (source.id,),
    ).fetchall()

    assert [row["vocabulary_kind"] for row in rows] == [
        "crop_product", "reported_issue", "task_type",
    ]
    task = rows[-1]
    assert dict(task) == {
        "vocabulary_kind": "task_type", "source_context": "task", "raw_value": "Farmer Visit",
        "normalized_key": "visit", "display_label": "Field visit",
        "mapping_state": "automatic", "mapping_method": "deterministic",
    }
    assert operating_vocabulary.vocabulary_summary(ffl_db, source.id) == {
        "terms": 3, "pending": 2, "suggested": 0, "reviewed": 0, "automatic": 1,
    }


def test_luna_only_stores_reviewable_suggestions(ffl_db, owner, monkeypatch):
    source = _seed_vocabulary_source(ffl_db, owner)
    operating_vocabulary.refresh_source_vocabulary(ffl_db, source.id)
    calls = []

    def fake_structured_output(*, prompt, schema_name, schema):
        calls.append({"prompt": prompt, "schema_name": schema_name, "schema": schema})
        return ({"items": [{
            "id": "0", "outcome": "suggest", "normalized_key": "brand-x-20-ec",
            "display_label": "Brand X 20 EC", "confidence": 0.91,
        }]}, "gpt-5.6-luna")

    monkeypatch.setattr(operating_vocabulary.openai_responses, "structured_output", fake_structured_output)
    result = operating_vocabulary.suggest_pending_terms(ffl_db, source.id, limit=1)
    term = operating_vocabulary.pending_terms_for_source(ffl_db, source.id, limit=10)[0]
    stored = ffl_db.execute(
        """SELECT mapping_state, mapping_method, normalized_key, display_label,
                  classifier_model FROM operating_vocabulary_terms
           WHERE source_id = ? AND vocabulary_kind = 'crop_product'""",
        (source.id,),
    ).fetchone()

    assert result == {"state": "suggested", "considered": 1, "suggested": 1, "model": "gpt-5.6-luna"}
    assert calls[0]["schema_name"] == "operating_vocabulary_suggestions"
    assert "Bacterial Leaf Blight" not in calls[0]["prompt"]
    assert dict(stored) == {
        "mapping_state": "suggested", "mapping_method": "ai", "normalized_key": "brand-x-20-ec",
        "display_label": "Brand X 20 EC", "classifier_model": "gpt-5.6-luna",
    }
    assert term.vocabulary_kind == "reported_issue"


def test_invalid_model_result_is_not_saved_and_a_manual_review_is_versioned(ffl_db, owner, monkeypatch):
    source = _seed_vocabulary_source(ffl_db, owner)
    operating_vocabulary.refresh_source_vocabulary(ffl_db, source.id)
    monkeypatch.setattr(
        operating_vocabulary.openai_responses,
        "structured_output",
        lambda **_: ({"items": [{
            "id": "999", "outcome": "suggest", "normalized_key": "invented",
            "display_label": "Invented diagnosis", "confidence": 1,
        }]}, "gpt-5.6-luna"),
    )

    assert operating_vocabulary.suggest_pending_terms(ffl_db, source.id, limit=1)["state"] == "no_safe_suggestions"
    candidate = operating_vocabulary.pending_terms_for_source(ffl_db, source.id, limit=1)[0]
    assert operating_vocabulary.review_term(
        ffl_db, candidate, normalized_key="brand-x-20-ec", display_label="Brand X 20 EC", state="reviewed",
    )
    stored = ffl_db.execute(
        """SELECT mapping_state, mapping_method, mapping_version, confidence
           FROM operating_vocabulary_terms WHERE source_id = ? AND raw_fingerprint = ?""",
        (source.id, candidate.raw_fingerprint),
    ).fetchone()
    assert dict(stored) == {
        "mapping_state": "reviewed", "mapping_method": "manual",
        "mapping_version": operating_vocabulary.MANUAL_MAPPING_VERSION, "confidence": 1.0,
    }


def test_suspicious_raw_terms_remain_private_and_are_not_model_candidates(ffl_db, owner):
    source = _seed_vocabulary_source(ffl_db, owner)
    ffl_db.execute(
        """UPDATE trackwick_crop_inputs
           SET reported_product = 'call 999 999 9999 for product', source_fingerprint = ?
           WHERE id = 'input-1'""",
        ("e" * 64,),
    )
    ffl_db.commit()
    operating_vocabulary.refresh_source_vocabulary(ffl_db, source.id)

    assert [
        (term.vocabulary_kind, term.raw_value)
        for term in operating_vocabulary.pending_terms_for_source(ffl_db, source.id)
    ] == [("reported_issue", "Bacterial Leaf Blight")]
    assert ffl_db.execute(
        "SELECT count(*) FROM operating_vocabulary_terms WHERE source_id = ? AND vocabulary_kind = 'crop_product'",
        (source.id,),
    ).fetchone()[0] == 1
