"""Review-first language packs and issue groups for private operating data.

This module has three narrow jobs:

* propose Hindi display labels and local search aliases for controlled terms;
* materialize an accountable issue-group queue from already-proposed keys; and
* propose Hindi display labels and search aliases for existing place records.

It never changes a raw source value, relates people, merges places, draws a
boundary, or turns a reported issue into an agronomic diagnosis.  Imports do
not call it; an operator runs a bounded command deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping, Optional, Sequence

from ffl.services import gemini_structured, operating_vocabulary


LOCALE_HINDI = "hi"
LANGUAGE_MAPPING_VERSION = "language-v1"
ISSUE_GROUP_VERSION = "issue-group-v1"
_MODEL_BATCH_SIZE = 8
_CANDIDATE_SCAN_LIMIT = 1_000
_DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097f]")


@dataclass(frozen=True)
class VocabularyLocalizationCandidate:
    source_id: str
    vocabulary_kind: str
    source_context: str
    raw_fingerprint: str
    display_label: str
    occurrence_count: int
    first_seen_at: str
    last_seen_at: str


@dataclass(frozen=True)
class PlaceLocalizationCandidate:
    source_id: str
    place_key: str
    village_name: Optional[str]
    block_name: Optional[str]
    district_name: Optional[str]
    first_seen_at: str
    last_seen_at: str


def language_schema_available(conn) -> bool:
    """Return whether all private language tables are ready for use."""
    return all(
        _relation_available(conn, postgres_name, sqlite_name)
        for postgres_name, sqlite_name in (
            ("agro_operating_vocabulary_localizations", "operating_vocabulary_localizations"),
            ("agro_operating_issue_group_proposals", "operating_issue_group_proposals"),
            ("agro_place_localizations", "place_localizations"),
        )
    )


def pending_vocabulary_localizations(
    conn,
    source_id: str,
    *,
    locale_code: str = LOCALE_HINDI,
    limit: int = _MODEL_BATCH_SIZE,
) -> list[VocabularyLocalizationCandidate]:
    """Return a bounded, non-identity fact pack for one language pass."""
    _require_hindi(locale_code)
    if not _relation_available(
        conn, "agro_operating_vocabulary_localizations", "operating_vocabulary_localizations"
    ) or not operating_vocabulary.vocabulary_schema_available(conn):
        return []
    limit = _bounded_limit(limit)
    rows = conn.execute(
        """SELECT vocabulary.source_id, vocabulary.vocabulary_kind, vocabulary.source_context,
                  vocabulary.raw_fingerprint, vocabulary.display_label,
                  vocabulary.occurrence_count, vocabulary.first_seen_at, vocabulary.last_seen_at
           FROM operating_vocabulary_terms AS vocabulary
           LEFT JOIN operating_vocabulary_localizations AS localization
             ON localization.source_id = vocabulary.source_id
            AND localization.vocabulary_kind = vocabulary.vocabulary_kind
            AND localization.source_context = vocabulary.source_context
            AND localization.raw_fingerprint = vocabulary.raw_fingerprint
            AND localization.locale_code = ?
           WHERE vocabulary.source_id = ?
             AND vocabulary.mapping_state IN ('automatic', 'suggested', 'reviewed')
             AND vocabulary.display_label IS NOT NULL
             AND localization.source_id IS NULL
           ORDER BY vocabulary.occurrence_count DESC, vocabulary.vocabulary_kind,
                    vocabulary.display_label
           LIMIT ?""",
        (locale_code, source_id, _CANDIDATE_SCAN_LIMIT),
    ).fetchall()
    candidates = []
    for row in rows:
        value = _safe_text(dict(row).get("display_label"))
        if value is None:
            continue
        candidates.append(VocabularyLocalizationCandidate(
            source_id=str(row["source_id"]),
            vocabulary_kind=str(row["vocabulary_kind"]),
            source_context=str(row["source_context"]),
            raw_fingerprint=str(row["raw_fingerprint"]),
            display_label=value,
            occurrence_count=int(row["occurrence_count"] or 0),
            first_seen_at=str(row["first_seen_at"]),
            last_seen_at=str(row["last_seen_at"]),
        ))
        if len(candidates) >= limit:
            break
    return candidates


def suggest_hindi_vocabulary_localizations(
    conn,
    source_id: str,
    *,
    limit: int = _MODEL_BATCH_SIZE,
    commit: bool = True,
) -> dict[str, Any]:
    """Persist reviewable Hindi vocabulary labels; never auto-publish them."""
    candidates = pending_vocabulary_localizations(conn, source_id, limit=limit)
    if not candidates:
        return _nothing_pending()
    payload, model = gemini_structured.structured_output(
        prompt=_vocabulary_prompt(candidates),
        schema_name="operating_vocabulary_hindi_localizations",
        schema=_vocabulary_schema(),
    )
    if payload is None or model is None:
        return _unavailable(len(candidates))
    suggestions, kept_raw = _validated_vocabulary_decisions(payload, candidates)
    _upsert_vocabulary_localizations(conn, suggestions, kept_raw, model)
    if (suggestions or kept_raw) and commit:
        conn.commit()
    return _result(suggestions, kept_raw, model, len(candidates))


def pending_place_localizations(
    conn,
    source_id: str,
    *,
    locale_code: str = LOCALE_HINDI,
    limit: int = _MODEL_BATCH_SIZE,
) -> list[PlaceLocalizationCandidate]:
    """Return place labels for display only, never prospective place matching."""
    _require_hindi(locale_code)
    if not _relation_available(conn, "agro_place_localizations", "place_localizations") or not _relation_available(
        conn, "agro_place_catalog", "place_catalog"
    ):
        return []
    limit = _bounded_limit(limit)
    rows = conn.execute(
        """SELECT place.source_id, place.place_key, place.village_name, place.block_name,
                  place.district_name, place.first_seen_at, place.last_seen_at
           FROM place_catalog AS place
           LEFT JOIN place_localizations AS localization
             ON localization.source_id = place.source_id
            AND localization.place_key = place.place_key
            AND localization.locale_code = ?
           WHERE place.source_id = ? AND localization.source_id IS NULL
           ORDER BY place.district_name, place.block_name, place.village_name, place.place_key
           LIMIT ?""",
        (locale_code, source_id, _CANDIDATE_SCAN_LIMIT),
    ).fetchall()
    candidates = []
    for row in rows:
        village_name = _safe_text(row["village_name"])
        block_name = _safe_text(row["block_name"])
        district_name = _safe_text(row["district_name"])
        if not any((village_name, block_name, district_name)):
            continue
        candidates.append(PlaceLocalizationCandidate(
            source_id=str(row["source_id"]), place_key=str(row["place_key"]),
            village_name=village_name, block_name=block_name, district_name=district_name,
            first_seen_at=str(row["first_seen_at"]), last_seen_at=str(row["last_seen_at"]),
        ))
        if len(candidates) >= limit:
            break
    return candidates


def suggest_hindi_place_localizations(
    conn,
    source_id: str,
    *,
    limit: int = _MODEL_BATCH_SIZE,
    commit: bool = True,
) -> dict[str, Any]:
    """Persist suggested Hindi place labels and search aliases without place merges."""
    candidates = pending_place_localizations(conn, source_id, limit=limit)
    if not candidates:
        return _nothing_pending()
    payload, model = gemini_structured.structured_output(
        prompt=_place_prompt(candidates),
        schema_name="operating_place_hindi_localizations",
        schema=_place_schema(),
    )
    if payload is None or model is None:
        return _unavailable(len(candidates))
    suggestions, kept_raw = _validated_place_decisions(payload, candidates)
    _upsert_place_localizations(conn, suggestions, kept_raw, model)
    if (suggestions or kept_raw) and commit:
        conn.commit()
    return _result(suggestions, kept_raw, model, len(candidates))


def refresh_issue_group_proposals(
    conn,
    source_id: str,
    *,
    refreshed_at: Optional[str] = None,
    commit: bool = True,
) -> int:
    """Materialize small review groups from existing semantic suggestions.

    This performs no model call.  A group only appears when two or more
    reported issue labels already share the same proposed normalized key within
    their source-provided disease/pest lane.
    """
    if not _relation_available(
        conn, "agro_operating_issue_group_proposals", "operating_issue_group_proposals"
    ) or not operating_vocabulary.vocabulary_schema_available(conn):
        return 0
    rows = conn.execute(
        """SELECT source_id, source_context, normalized_key, min(display_label) AS display_label,
                  count(*) AS member_count, sum(occurrence_count) AS occurrence_count,
                  min(first_seen_at) AS first_seen_at, max(last_seen_at) AS last_seen_at
           FROM operating_vocabulary_terms
           WHERE source_id = ? AND vocabulary_kind = 'reported_issue'
             AND mapping_state IN ('suggested', 'reviewed')
             AND normalized_key IS NOT NULL AND display_label IS NOT NULL
           GROUP BY source_id, source_context, normalized_key
           HAVING count(*) >= 2""",
        (source_id,),
    ).fetchall()
    if not rows:
        return 0
    now = refreshed_at or _now()
    conn.executemany(
        """INSERT INTO operating_issue_group_proposals (
               source_id, source_context, normalized_key, display_label, member_count,
               occurrence_count, first_seen_at, last_seen_at, mapping_state,
               mapping_method, mapping_version, reviewed_at, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'suggested', 'deterministic', ?, NULL, ?)
           ON CONFLICT (source_id, source_context, normalized_key) DO UPDATE SET
               display_label = CASE WHEN operating_issue_group_proposals.mapping_state = 'suggested'
                   THEN excluded.display_label ELSE operating_issue_group_proposals.display_label END,
               member_count = excluded.member_count,
               occurrence_count = excluded.occurrence_count,
               first_seen_at = CASE WHEN excluded.first_seen_at < operating_issue_group_proposals.first_seen_at
                   THEN excluded.first_seen_at ELSE operating_issue_group_proposals.first_seen_at END,
               last_seen_at = CASE WHEN excluded.last_seen_at > operating_issue_group_proposals.last_seen_at
                   THEN excluded.last_seen_at ELSE operating_issue_group_proposals.last_seen_at END,
               mapping_version = CASE WHEN operating_issue_group_proposals.mapping_state = 'suggested'
                   THEN excluded.mapping_version ELSE operating_issue_group_proposals.mapping_version END,
               refreshed_at = excluded.refreshed_at""",
        [
            (
                row["source_id"], row["source_context"], row["normalized_key"], row["display_label"],
                int(row["member_count"] or 0), int(row["occurrence_count"] or 0),
                row["first_seen_at"], row["last_seen_at"], ISSUE_GROUP_VERSION, now,
            )
            for row in rows
        ],
    )
    if commit:
        conn.commit()
    return len(rows)


def language_summary(conn, source_id: str) -> dict[str, dict[str, int]]:
    """Return only aggregate receipts for an operator or settings surface."""
    return {
        "vocabulary": _state_summary(
            conn, "agro_operating_vocabulary_localizations", "operating_vocabulary_localizations",
            source_id,
        ),
        "places": _state_summary(
            conn, "agro_place_localizations", "place_localizations", source_id,
        ),
        "issue_groups": _state_summary(
            conn, "agro_operating_issue_group_proposals", "operating_issue_group_proposals",
            source_id,
        ),
    }


def vocabulary_localization_review_queue(conn, source_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return a bounded manager review queue without exposing raw source values."""
    if not _relation_available(
        conn, "agro_operating_vocabulary_localizations", "operating_vocabulary_localizations"
    ):
        return []
    rows = conn.execute(
        """SELECT localization.vocabulary_kind, localization.source_context,
                  localization.raw_fingerprint, vocabulary.display_label AS source_label,
                  localization.display_label AS suggested_label, localization.search_aliases_json,
                  localization.confidence
           FROM operating_vocabulary_localizations AS localization
           JOIN operating_vocabulary_terms AS vocabulary
             ON vocabulary.source_id = localization.source_id
            AND vocabulary.vocabulary_kind = localization.vocabulary_kind
            AND vocabulary.source_context = localization.source_context
            AND vocabulary.raw_fingerprint = localization.raw_fingerprint
           WHERE localization.source_id = ? AND localization.locale_code = ?
             AND localization.mapping_state = 'suggested'
           ORDER BY vocabulary.occurrence_count DESC, vocabulary.vocabulary_kind, vocabulary.display_label
           LIMIT ?""",
        (source_id, LOCALE_HINDI, _review_limit(limit)),
    ).fetchall()
    return [{
        "vocabulary_kind": str(row["vocabulary_kind"]),
        "source_context": str(row["source_context"]),
        "raw_fingerprint": str(row["raw_fingerprint"]),
        "source_label": str(row["source_label"]),
        "suggested_label": str(row["suggested_label"]),
        "search_aliases": _read_aliases(row["search_aliases_json"]),
        "confidence": float(row["confidence"]),
    } for row in rows]


def place_localization_review_queue(conn, source_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return reviewable place display packs; source location fields remain immutable."""
    if not _relation_available(conn, "agro_place_localizations", "place_localizations"):
        return []
    rows = conn.execute(
        """SELECT localization.place_key, place.village_name, place.block_name, place.district_name,
                  localization.village_label, localization.block_label, localization.district_label,
                  localization.search_aliases_json, localization.confidence
           FROM place_localizations AS localization
           JOIN place_catalog AS place
             ON place.source_id = localization.source_id AND place.place_key = localization.place_key
           WHERE localization.source_id = ? AND localization.locale_code = ?
             AND localization.mapping_state = 'suggested'
           ORDER BY place.district_name, place.block_name, place.village_name, place.place_key
           LIMIT ?""",
        (source_id, LOCALE_HINDI, _review_limit(limit)),
    ).fetchall()
    return [{
        "place_key": str(row["place_key"]),
        "source": {
            "village": row["village_name"], "block": row["block_name"],
            "district": row["district_name"],
        },
        "suggested": {
            "village": row["village_label"], "block": row["block_label"],
            "district": row["district_label"],
        },
        "search_aliases": _read_aliases(row["search_aliases_json"]),
        "confidence": float(row["confidence"]),
    } for row in rows]


def issue_group_review_queue(conn, source_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return only derived group metadata—not individual raw source phrases."""
    if not _relation_available(
        conn, "agro_operating_issue_group_proposals", "operating_issue_group_proposals"
    ):
        return []
    rows = conn.execute(
        """SELECT source_context, normalized_key, display_label, member_count, occurrence_count
           FROM operating_issue_group_proposals
           WHERE source_id = ? AND mapping_state = 'suggested'
           ORDER BY occurrence_count DESC, source_context, display_label
           LIMIT ?""",
        (source_id, _review_limit(limit)),
    ).fetchall()
    return [{
        "source_context": str(row["source_context"]), "normalized_key": str(row["normalized_key"]),
        "display_label": str(row["display_label"]), "member_count": int(row["member_count"]),
        "occurrence_count": int(row["occurrence_count"]),
    } for row in rows]


def review_vocabulary_localization(
    conn,
    candidate: VocabularyLocalizationCandidate,
    *,
    display_label: Optional[str],
    search_aliases: Sequence[str],
    state: str,
    commit: bool = True,
) -> bool:
    """Accept, reject, or hold one localization without modifying its source term."""
    if state not in {"reviewed", "rejected", "unmapped"}:
        raise ValueError("Localization review state is invalid")
    label = _hindi_label(display_label) if state == "reviewed" else None
    aliases = _validated_aliases(search_aliases) if state == "reviewed" else []
    if state == "reviewed" and label is None:
        raise ValueError("A reviewed Hindi label is required")
    now = _now()
    result = conn.execute(
        """UPDATE operating_vocabulary_localizations
           SET display_label = ?, search_aliases_json = ?, mapping_state = ?,
               mapping_method = 'manual', confidence = CASE WHEN ? = 'reviewed' THEN 1 ELSE NULL END,
               classifier_model = NULL, mapping_version = ?, reviewed_at = ?, refreshed_at = ?
           WHERE source_id = ? AND vocabulary_kind = ? AND source_context = ?
             AND raw_fingerprint = ? AND locale_code = ?""",
        (
            label, _aliases_json(aliases), state, state, LANGUAGE_MAPPING_VERSION, now, now,
            candidate.source_id, candidate.vocabulary_kind, candidate.source_context,
            candidate.raw_fingerprint, LOCALE_HINDI,
        ),
    )
    if result.rowcount and commit:
        conn.commit()
    return bool(result.rowcount)


def review_place_localization(
    conn,
    candidate: PlaceLocalizationCandidate,
    *,
    village_label: Optional[str],
    block_label: Optional[str],
    district_label: Optional[str],
    search_aliases: Sequence[str],
    state: str,
    commit: bool = True,
) -> bool:
    """Accept/reject a display pack without touching the place catalogue."""
    if state not in {"reviewed", "rejected", "unmapped"}:
        raise ValueError("Place localization review state is invalid")
    labels = (
        _hindi_label(village_label), _hindi_label(block_label), _hindi_label(district_label),
    ) if state == "reviewed" else (None, None, None)
    aliases = _validated_aliases(search_aliases) if state == "reviewed" else []
    if state == "reviewed" and not any(labels):
        raise ValueError("A reviewed Hindi place label is required")
    now = _now()
    result = conn.execute(
        """UPDATE place_localizations
           SET village_label = ?, block_label = ?, district_label = ?, search_aliases_json = ?,
               mapping_state = ?, mapping_method = 'manual',
               confidence = CASE WHEN ? = 'reviewed' THEN 1 ELSE NULL END,
               classifier_model = NULL, mapping_version = ?, reviewed_at = ?, refreshed_at = ?
           WHERE source_id = ? AND place_key = ? AND locale_code = ?""",
        (
            *labels, _aliases_json(aliases), state, state, LANGUAGE_MAPPING_VERSION, now, now,
            candidate.source_id, candidate.place_key, LOCALE_HINDI,
        ),
    )
    if result.rowcount and commit:
        conn.commit()
    return bool(result.rowcount)


def review_issue_group(
    conn,
    source_id: str,
    *,
    source_context: str,
    normalized_key: str,
    state: str,
    commit: bool = True,
) -> bool:
    """Mark an exact proposed issue group reviewed or rejected."""
    if source_context not in {"reported_disease", "reported_pest"}:
        raise ValueError("Issue source context is invalid")
    if state not in {"reviewed", "rejected"}:
        raise ValueError("Issue group review state is invalid")
    key = operating_vocabulary._validated_key(normalized_key)
    if key is None:
        raise ValueError("Issue group key is invalid")
    now = _now()
    result = conn.execute(
        """UPDATE operating_issue_group_proposals
           SET mapping_state = ?, mapping_method = 'manual', mapping_version = ?,
               reviewed_at = ?, refreshed_at = ?
           WHERE source_id = ? AND source_context = ? AND normalized_key = ?""",
        (state, ISSUE_GROUP_VERSION, now, now, source_id, source_context, key),
    )
    if result.rowcount and commit:
        conn.commit()
    return bool(result.rowcount)


def reviewed_vocabulary_localizations(conn, source_id: str, *, locale_code: str = LOCALE_HINDI) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Provide safe reviewed labels to future map/card/search read models."""
    _require_hindi(locale_code)
    if not _relation_available(
        conn, "agro_operating_vocabulary_localizations", "operating_vocabulary_localizations"
    ):
        return {}
    rows = conn.execute(
        """SELECT vocabulary_kind, source_context, raw_fingerprint, display_label, search_aliases_json
           FROM operating_vocabulary_localizations
           WHERE source_id = ? AND locale_code = ? AND mapping_state = 'reviewed'""",
        (source_id, locale_code),
    ).fetchall()
    return {
        (str(row["vocabulary_kind"]), str(row["source_context"]), str(row["raw_fingerprint"])): {
            "display_label": str(row["display_label"]),
            "search_aliases": _read_aliases(row["search_aliases_json"]),
        }
        for row in rows
    }


def reviewed_place_localizations(conn, source_id: str, *, locale_code: str = LOCALE_HINDI) -> dict[str, dict[str, Any]]:
    """Provide only reviewed, display-only place packs to future map reads."""
    _require_hindi(locale_code)
    if not _relation_available(conn, "agro_place_localizations", "place_localizations"):
        return {}
    rows = conn.execute(
        """SELECT place_key, village_label, block_label, district_label, search_aliases_json
           FROM place_localizations
           WHERE source_id = ? AND locale_code = ? AND mapping_state = 'reviewed'""",
        (source_id, locale_code),
    ).fetchall()
    return {
        str(row["place_key"]): {
            "village_label": row["village_label"], "block_label": row["block_label"],
            "district_label": row["district_label"],
            "search_aliases": _read_aliases(row["search_aliases_json"]),
        }
        for row in rows
    }


def _upsert_vocabulary_localizations(conn, suggestions, kept_raw, model: str) -> None:
    now = _now()
    rows = []
    for candidate, decision in suggestions:
        rows.append((
            candidate.source_id, candidate.vocabulary_kind, candidate.source_context,
            candidate.raw_fingerprint, LOCALE_HINDI, decision["display_label"],
            _aliases_json(decision["search_aliases"]), "suggested", "ai", decision["confidence"],
            model, LANGUAGE_MAPPING_VERSION, candidate.first_seen_at, candidate.last_seen_at, now, now,
        ))
    for candidate, confidence in kept_raw:
        rows.append((
            candidate.source_id, candidate.vocabulary_kind, candidate.source_context,
            candidate.raw_fingerprint, LOCALE_HINDI, None, "[]", "unmapped", "ai", confidence,
            model, LANGUAGE_MAPPING_VERSION, candidate.first_seen_at, candidate.last_seen_at, now, now,
        ))
    if not rows:
        return
    conn.executemany(
        """INSERT INTO operating_vocabulary_localizations (
               source_id, vocabulary_kind, source_context, raw_fingerprint, locale_code,
               display_label, search_aliases_json, mapping_state, mapping_method, confidence,
               classifier_model, mapping_version, first_seen_at, last_seen_at, classified_at, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source_id, vocabulary_kind, source_context, raw_fingerprint, locale_code) DO UPDATE SET
               display_label = CASE WHEN operating_vocabulary_localizations.mapping_state = 'suggested'
                   THEN excluded.display_label ELSE operating_vocabulary_localizations.display_label END,
               search_aliases_json = CASE WHEN operating_vocabulary_localizations.mapping_state = 'suggested'
                   THEN excluded.search_aliases_json ELSE operating_vocabulary_localizations.search_aliases_json END,
               confidence = CASE WHEN operating_vocabulary_localizations.mapping_state = 'suggested'
                   THEN excluded.confidence ELSE operating_vocabulary_localizations.confidence END,
               classifier_model = CASE WHEN operating_vocabulary_localizations.mapping_state = 'suggested'
                   THEN excluded.classifier_model ELSE operating_vocabulary_localizations.classifier_model END,
               mapping_version = CASE WHEN operating_vocabulary_localizations.mapping_state = 'suggested'
                   THEN excluded.mapping_version ELSE operating_vocabulary_localizations.mapping_version END,
               refreshed_at = excluded.refreshed_at""",
        rows,
    )


def _upsert_place_localizations(conn, suggestions, kept_raw, model: str) -> None:
    now = _now()
    rows = []
    for candidate, decision in suggestions:
        rows.append((
            candidate.source_id, candidate.place_key, LOCALE_HINDI,
            decision["village_label"], decision["block_label"], decision["district_label"],
            _aliases_json(decision["search_aliases"]), "suggested", "ai", decision["confidence"],
            model, LANGUAGE_MAPPING_VERSION, candidate.first_seen_at, candidate.last_seen_at, now, now,
        ))
    for candidate, confidence in kept_raw:
        rows.append((
            candidate.source_id, candidate.place_key, LOCALE_HINDI,
            None, None, None, "[]", "unmapped", "ai", confidence, model,
            LANGUAGE_MAPPING_VERSION, candidate.first_seen_at, candidate.last_seen_at, now, now,
        ))
    if not rows:
        return
    conn.executemany(
        """INSERT INTO place_localizations (
               source_id, place_key, locale_code, village_label, block_label, district_label,
               search_aliases_json, mapping_state, mapping_method, confidence, classifier_model,
               mapping_version, first_seen_at, last_seen_at, classified_at, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source_id, place_key, locale_code) DO UPDATE SET
               village_label = CASE WHEN place_localizations.mapping_state = 'suggested'
                   THEN excluded.village_label ELSE place_localizations.village_label END,
               block_label = CASE WHEN place_localizations.mapping_state = 'suggested'
                   THEN excluded.block_label ELSE place_localizations.block_label END,
               district_label = CASE WHEN place_localizations.mapping_state = 'suggested'
                   THEN excluded.district_label ELSE place_localizations.district_label END,
               search_aliases_json = CASE WHEN place_localizations.mapping_state = 'suggested'
                   THEN excluded.search_aliases_json ELSE place_localizations.search_aliases_json END,
               confidence = CASE WHEN place_localizations.mapping_state = 'suggested'
                   THEN excluded.confidence ELSE place_localizations.confidence END,
               classifier_model = CASE WHEN place_localizations.mapping_state = 'suggested'
                   THEN excluded.classifier_model ELSE place_localizations.classifier_model END,
               mapping_version = CASE WHEN place_localizations.mapping_state = 'suggested'
                   THEN excluded.mapping_version ELSE place_localizations.mapping_version END,
               refreshed_at = excluded.refreshed_at""",
        rows,
    )


def _vocabulary_prompt(candidates: Sequence[VocabularyLocalizationCandidate]) -> str:
    terms = [
        {"id": str(index), "kind": item.vocabulary_kind, "label": item.display_label}
        for index, item in enumerate(candidates)
    ]
    return """Translate each controlled operating label into a concise Hindi display label.
The input is an approved-or-reviewable operating vocabulary label, not a person,
farm, address, or diagnosis. Return up to four safe search aliases that help an
operator find the same label in Roman/Hinglish spelling. Do not infer product
ingredients, diagnose a reported disease/pest, add advice, create a fact, or
return a source/provider name. Hindi display labels must contain Devanagari.
If a faithful display translation is unclear, use outcome `keep_raw` with null
display_label and an empty search_aliases list. Return exactly one item per id.

INPUT LABELS:
""" + json.dumps(terms, ensure_ascii=True, separators=(",", ":"))


def _place_prompt(candidates: Sequence[PlaceLocalizationCandidate]) -> str:
    places = [
        {
            "id": str(index), "village": item.village_name, "block": item.block_name,
            "district": item.district_name,
        }
        for index, item in enumerate(candidates)
    ]
    return """Create Hindi display labels for the supplied place components and a few safe
Roman/Hinglish search aliases. Preserve each village, block, and district as a
separate display component. Never join two places, correct geography, infer a
coordinate, address, boundary, owner, or farm. Hindi labels must contain
Devanagari for every supplied component. If a faithful transliteration is
unclear, use outcome `keep_raw` with all labels null and no aliases. Return
exactly one item per id.

INPUT PLACES:
""" + json.dumps(places, ensure_ascii=True, separators=(",", ":"))


def _vocabulary_schema() -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["suggest", "keep_raw"]},
                "display_label": {"type": ["string", "null"]},
                "search_aliases": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["id", "outcome", "display_label", "search_aliases", "confidence"],
        }}},
        "required": ["items"],
    }


def _place_schema() -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["suggest", "keep_raw"]},
                "village_label": {"type": ["string", "null"]},
                "block_label": {"type": ["string", "null"]},
                "district_label": {"type": ["string", "null"]},
                "search_aliases": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": [
                "id", "outcome", "village_label", "block_label", "district_label",
                "search_aliases", "confidence",
            ],
        }}},
        "required": ["items"],
    }


def _validated_vocabulary_decisions(payload: Mapping[str, Any], candidates: Sequence[VocabularyLocalizationCandidate]):
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return [], []
    by_id = {str(index): value for index, value in enumerate(candidates)}
    suggestions, kept_raw, seen = [], [], set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("id") or "")
        candidate = by_id.get(identifier)
        if candidate is None or identifier in seen:
            continue
        seen.add(identifier)
        confidence = operating_vocabulary._validated_confidence(item.get("confidence"))
        if confidence is None:
            continue
        if item.get("outcome") == "keep_raw":
            if item.get("display_label") is None and item.get("search_aliases") == []:
                kept_raw.append((candidate, confidence))
            continue
        if item.get("outcome") != "suggest":
            continue
        label = _hindi_label(item.get("display_label"))
        aliases = _validated_aliases(item.get("search_aliases"))
        if label is None:
            continue
        suggestions.append((candidate, {
            "display_label": label, "search_aliases": aliases, "confidence": confidence,
        }))
    return suggestions, kept_raw


def _validated_place_decisions(payload: Mapping[str, Any], candidates: Sequence[PlaceLocalizationCandidate]):
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return [], []
    by_id = {str(index): value for index, value in enumerate(candidates)}
    suggestions, kept_raw, seen = [], [], set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("id") or "")
        candidate = by_id.get(identifier)
        if candidate is None or identifier in seen:
            continue
        seen.add(identifier)
        confidence = operating_vocabulary._validated_confidence(item.get("confidence"))
        if confidence is None:
            continue
        labels = (
            _hindi_label(item.get("village_label")), _hindi_label(item.get("block_label")),
            _hindi_label(item.get("district_label")),
        )
        if item.get("outcome") == "keep_raw":
            if not any(labels) and item.get("search_aliases") == []:
                kept_raw.append((candidate, confidence))
            continue
        if item.get("outcome") != "suggest":
            continue
        expected = (candidate.village_name, candidate.block_name, candidate.district_name)
        if any((source is not None and label is None) or (source is None and label is not None)
               for source, label in zip(expected, labels)):
            continue
        aliases = _validated_aliases(item.get("search_aliases"))
        suggestions.append((candidate, {
            "village_label": labels[0], "block_label": labels[1], "district_label": labels[2],
            "search_aliases": aliases, "confidence": confidence,
        }))
    return suggestions, kept_raw


def _state_summary(conn, postgres_name: str, sqlite_name: str, source_id: str) -> dict[str, int]:
    if not _relation_available(conn, postgres_name, sqlite_name):
        return {"terms": 0, "suggested": 0, "reviewed": 0, "rejected": 0, "unmapped": 0}
    row = conn.execute(
        """SELECT count(*) AS terms,
                  sum(CASE WHEN mapping_state = 'suggested' THEN 1 ELSE 0 END) AS suggested,
                  sum(CASE WHEN mapping_state = 'reviewed' THEN 1 ELSE 0 END) AS reviewed,
                  sum(CASE WHEN mapping_state = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                  sum(CASE WHEN mapping_state = 'unmapped' THEN 1 ELSE 0 END) AS unmapped
           FROM {table_name} WHERE source_id = ?""".format(table_name=sqlite_name),
        (source_id,),
    ).fetchone()
    return {key: int(row[key] or 0) for key in ("terms", "suggested", "reviewed", "rejected", "unmapped")}


def _relation_available(conn, postgres_name: str, sqlite_name: str) -> bool:
    if getattr(conn, "dialect", "sqlite") == "postgres":
        row = conn.execute("SELECT to_regclass(?) AS relation_name", (postgres_name,)).fetchone()
        return row is not None and row["relation_name"] is not None
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (sqlite_name,),
    ).fetchone()
    return row is not None


def _hindi_label(value: Any) -> Optional[str]:
    value = _safe_text(value)
    return value if value is not None and _DEVANAGARI_PATTERN.search(value) else None


def _safe_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split()).strip()
    if not value or len(value) > 120 or not operating_vocabulary._safe_for_model(value):
        return None
    return value


def _validated_aliases(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result, seen = [], set()
    for item in value:
        alias = _safe_text(item)
        if alias is None:
            continue
        key = alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(alias)
        if len(result) == 4:
            break
    return result


def _aliases_json(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(",", ":"))


def _read_aliases(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return _validated_aliases(value)


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), _MODEL_BATCH_SIZE))


def _review_limit(limit: int) -> int:
    return max(1, min(int(limit), 100))


def _require_hindi(locale_code: str) -> None:
    if locale_code != LOCALE_HINDI:
        raise ValueError("Only the reviewed Hindi language pack is available")


def _nothing_pending() -> dict[str, Any]:
    return {"state": "nothing_pending", "considered": 0, "suggested": 0, "kept_raw": 0, "model": None}


def _unavailable(considered: int) -> dict[str, Any]:
    return {"state": "unavailable", "considered": considered, "suggested": 0, "kept_raw": 0, "model": None}


def _result(suggestions, kept_raw, model: str, considered: int) -> dict[str, Any]:
    return {
        "state": "suggested" if suggestions else "kept_raw" if kept_raw else "no_safe_suggestions",
        "considered": considered, "suggested": len(suggestions), "kept_raw": len(kept_raw), "model": model,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
