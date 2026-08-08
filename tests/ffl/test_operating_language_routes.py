from __future__ import annotations

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository


NOW = "2026-08-08T12:00:00+00:00"


def test_operating_language_review_board_is_manager_only_and_hides_raw_values(tmp_path):
    app = create_app(str(tmp_path / "language-routes.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id
        source = repository.create_source_registry(
            app.state.conn, "trackwick-fortune-paddy", "Operating source", "partner",
            "Operating context", "partner", manager.id, ["farm_candidate_context"], "v1", "v1", {}, enabled=True,
        )
        app.state.conn.execute(
            """INSERT INTO operating_vocabulary_terms (
                   source_id, vocabulary_kind, source_context, raw_value, raw_fingerprint,
                   occurrence_count, normalized_key, display_label, mapping_state, mapping_method,
                   confidence, classifier_model, mapping_version, first_seen_at, last_seen_at, refreshed_at
               ) VALUES (?, 'crop_product', 'product', 'RAW_SOURCE_SENTINEL', ?, 7, 'brand-x', 'Brand X',
                         'suggested', 'ai', .9, 'gemini-3.5-flash-lite', 'v1', ?, ?, ?)""",
            (source.id, "a" * 64, NOW, NOW, NOW),
        )
        app.state.conn.execute(
            """INSERT INTO operating_vocabulary_localizations (
                   source_id, vocabulary_kind, source_context, raw_fingerprint, locale_code,
                   display_label, search_aliases_json, mapping_state, mapping_method, confidence,
                   classifier_model, mapping_version, first_seen_at, last_seen_at, classified_at, refreshed_at
               ) VALUES (?, 'crop_product', 'product', ?, 'hi', 'ब्रांड एक्स', '[\"brand x\"]',
                         'suggested', 'ai', .9, 'gemini-3.5-flash-lite', 'language-v1', ?, ?, ?, ?)""",
            (source.id, "a" * 64, NOW, NOW, NOW, NOW),
        )
        app.state.conn.commit()

        denied = client.get("/api/v1/operating-language")
        allowed = client.get(
            "/api/v1/operating-language", headers={"X-FFL-Manager-Token": "manager-secret"},
        )
        reviewed = client.patch(
            "/api/v1/operating-language/vocabulary",
            headers={"X-FFL-Manager-Token": "manager-secret"},
            json={
                "vocabulary_kind": "crop_product", "source_context": "product",
                "raw_fingerprint": "a" * 64, "state": "reviewed",
                "display_label": "ब्रांड एक्स", "search_aliases": ["brand x"],
            },
        )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["vocabulary"][0]["source_label"] == "Brand X"
    assert "RAW_SOURCE_SENTINEL" not in repr(allowed.json())
    assert reviewed.status_code == 200
    assert reviewed.json() == {"state": "reviewed"}
