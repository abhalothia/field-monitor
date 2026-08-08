from __future__ import annotations

from hashlib import sha256

from ffl.persistence import repository
from ffl.services import operating_language


NOW = "2026-08-08T12:00:00+00:00"


def _source(conn, owner):
    return repository.create_source_registry(
        conn,
        source_key="language-source",
        display_name="Language source",
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


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _vocabulary_term(
    conn,
    source,
    *,
    raw_value: str,
    kind: str = "crop_product",
    context: str = "product",
    key: str = "brand-x",
    label: str = "Brand X",
):
    fingerprint = _fingerprint(f"{kind}:{context}:{raw_value}")
    conn.execute(
        """INSERT INTO operating_vocabulary_terms (
               source_id, vocabulary_kind, source_context, raw_value, raw_fingerprint,
               occurrence_count, normalized_key, display_label, mapping_state, mapping_method,
               confidence, classifier_model, mapping_version, first_seen_at, last_seen_at, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, 3, ?, ?, 'suggested', 'ai', .9, 'gemini-3.5-flash-lite',
                     'vocabulary-ai-v1', ?, ?, ?)""",
        (source.id, kind, context, raw_value, fingerprint, key, label, NOW, NOW, NOW),
    )
    conn.commit()
    return fingerprint


def _place(conn, source):
    conn.execute(
        """INSERT INTO place_catalog (
               source_id, place_key, village_name, block_name, district_name,
               first_seen_at, last_seen_at, enrichment_version, refreshed_at
           ) VALUES (?, 'village|block|district', 'Village One', 'Block One', 'District One', ?, ?, 'v1', ?)""",
        (source.id, NOW, NOW, NOW),
    )
    conn.commit()


def test_hindi_vocabulary_localization_is_suggested_not_published(ffl_db, owner, monkeypatch):
    source = _source(ffl_db, owner)
    fingerprint = _vocabulary_term(ffl_db, source, raw_value="Brand X 20 EC")
    captured = []

    def fake_structured_output(*, prompt, **_):
        captured.append(prompt)
        return ({"items": [{
            "id": "0", "outcome": "suggest", "display_label": "ब्रांड एक्स",
            "search_aliases": ["brand x", "brand-x"], "confidence": .91,
        }]}, "gemini-3.5-flash-lite")

    monkeypatch.setattr(operating_language.gemini_structured, "structured_output", fake_structured_output)
    result = operating_language.suggest_hindi_vocabulary_localizations(ffl_db, source.id, limit=1)
    row = ffl_db.execute(
        """SELECT display_label, search_aliases_json, mapping_state, mapping_method
           FROM operating_vocabulary_localizations
           WHERE source_id = ? AND raw_fingerprint = ?""",
        (source.id, fingerprint),
    ).fetchone()

    assert result == {
        "state": "suggested", "considered": 1, "suggested": 1, "kept_raw": 0,
        "model": "gemini-3.5-flash-lite",
    }
    assert "Brand X" in captured[0]
    assert dict(row) == {
        "display_label": "ब्रांड एक्स", "search_aliases_json": '["brand x","brand-x"]',
        "mapping_state": "suggested", "mapping_method": "ai",
    }
    assert operating_language.reviewed_vocabulary_localizations(ffl_db, source.id) == {}


def test_place_localization_cannot_change_or_merge_the_source_place(ffl_db, owner, monkeypatch):
    source = _source(ffl_db, owner)
    _place(ffl_db, source)
    monkeypatch.setattr(
        operating_language.gemini_structured,
        "structured_output",
        lambda **_: ({"items": [{
            "id": "0", "outcome": "suggest", "village_label": "गाँव एक",
            "block_label": "ब्लॉक एक", "district_label": "ज़िला एक",
            "search_aliases": ["village one", "gaon ek"], "confidence": .93,
        }]}, "gemini-3.5-flash-lite"),
    )

    result = operating_language.suggest_hindi_place_localizations(ffl_db, source.id, limit=1)
    source_place = ffl_db.execute(
        "SELECT village_name, block_name, district_name FROM place_catalog WHERE source_id = ?",
        (source.id,),
    ).fetchone()
    suggestion = ffl_db.execute(
        """SELECT village_label, block_label, district_label, mapping_state
           FROM place_localizations WHERE source_id = ?""",
        (source.id,),
    ).fetchone()

    assert result["state"] == "suggested"
    assert dict(source_place) == {
        "village_name": "Village One", "block_name": "Block One", "district_name": "District One",
    }
    assert dict(suggestion) == {
        "village_label": "गाँव एक", "block_label": "ब्लॉक एक", "district_label": "ज़िला एक",
        "mapping_state": "suggested",
    }
    assert operating_language.reviewed_place_localizations(ffl_db, source.id) == {}


def test_issue_group_queue_is_deterministic_and_requires_multiple_mapped_terms(ffl_db, owner):
    source = _source(ffl_db, owner)
    _vocabulary_term(
        ffl_db, source, raw_value="Leaf blight", kind="reported_issue", context="reported_disease",
        key="leaf-blight", label="Leaf blight",
    )
    _vocabulary_term(
        ffl_db, source, raw_value="Leaf-blight", kind="reported_issue", context="reported_disease",
        key="leaf-blight", label="Leaf blight",
    )

    assert operating_language.refresh_issue_group_proposals(ffl_db, source.id) == 1
    row = ffl_db.execute(
        """SELECT source_context, normalized_key, member_count, occurrence_count,
                  mapping_state, mapping_method
           FROM operating_issue_group_proposals WHERE source_id = ?""",
        (source.id,),
    ).fetchone()

    assert dict(row) == {
        "source_context": "reported_disease", "normalized_key": "leaf-blight",
        "member_count": 2, "occurrence_count": 6,
        "mapping_state": "suggested", "mapping_method": "deterministic",
    }
    assert operating_language.review_issue_group(
        ffl_db, source.id, source_context="reported_disease", normalized_key="leaf-blight", state="reviewed",
    )
    assert ffl_db.execute(
        "SELECT mapping_state FROM operating_issue_group_proposals WHERE source_id = ?",
        (source.id,),
    ).fetchone()[0] == "reviewed"
