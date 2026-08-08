"""Durable, private vocabulary enrichment for repeat source imports.

This is intentionally a dictionary, not an entity profiler.  Source refreshes
only discover or refresh exact terms; they never invoke AI.  A separately run,
bounded Luna pass can propose labels for the small unresolved vocabulary and
every proposal remains reviewable before it is used in an operating view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Optional, Sequence

from ffl.services import openai_responses


VOCABULARY_VERSION = "vocabulary-v1"
AI_MAPPING_VERSION = "vocabulary-ai-v1"
MANUAL_MAPPING_VERSION = "vocabulary-manual-v1"
_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_URL_PATTERN = re.compile(r"\b(?:https?://|www\.)", re.IGNORECASE)
_LONG_NUMBER_PATTERN = re.compile(r"\d[\d\s().-]{5,}\d")
_OPENAI_BATCH_SIZE = 80


@dataclass(frozen=True)
class VocabularyTerm:
    source_id: str
    vocabulary_kind: str
    source_context: str
    raw_value: str
    raw_fingerprint: str
    occurrence_count: int
    normalized_key: Optional[str]
    display_label: Optional[str]
    mapping_state: str
    mapping_method: str
    confidence: Optional[float]
    first_seen_at: str
    last_seen_at: str


def vocabulary_schema_available(conn) -> bool:
    """Support a staged deployment before the additive migration is applied."""
    if getattr(conn, "dialect", "sqlite") == "postgres":
        row = conn.execute(
            "SELECT to_regclass(?) AS relation_name", ("agro_operating_vocabulary_terms",)
        ).fetchone()
        return row is not None and row["relation_name"] is not None
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("operating_vocabulary_terms",),
    ).fetchone()
    return row is not None


def refresh_source_vocabulary(
    conn,
    source_id: str,
    *,
    refreshed_at: Optional[str] = None,
    commit: bool = True,
) -> int:
    """Discover source vocabulary idempotently, without model calls or identity work."""
    if not vocabulary_schema_available(conn):
        return 0
    now = refreshed_at or _now()
    terms = _discover_terms(conn, source_id, fallback_at=now)
    if not terms:
        return 0
    conn.executemany(
        """INSERT INTO operating_vocabulary_terms (
               source_id, vocabulary_kind, source_context, raw_value, raw_fingerprint,
               occurrence_count, normalized_key, display_label, mapping_state,
               mapping_method, confidence, classifier_model, mapping_version,
               first_seen_at, last_seen_at, classified_at, reviewed_at, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, ?)
           ON CONFLICT (source_id, vocabulary_kind, source_context, raw_fingerprint) DO UPDATE SET
               raw_value = excluded.raw_value,
               occurrence_count = excluded.occurrence_count,
               first_seen_at = CASE
                   WHEN excluded.first_seen_at < operating_vocabulary_terms.first_seen_at
                   THEN excluded.first_seen_at ELSE operating_vocabulary_terms.first_seen_at END,
               last_seen_at = CASE
                   WHEN excluded.last_seen_at > operating_vocabulary_terms.last_seen_at
                   THEN excluded.last_seen_at ELSE operating_vocabulary_terms.last_seen_at END,
               normalized_key = CASE
                   WHEN operating_vocabulary_terms.mapping_state = 'automatic'
                   THEN excluded.normalized_key ELSE operating_vocabulary_terms.normalized_key END,
               display_label = CASE
                   WHEN operating_vocabulary_terms.mapping_state = 'automatic'
                   THEN excluded.display_label ELSE operating_vocabulary_terms.display_label END,
               mapping_state = CASE
                   WHEN operating_vocabulary_terms.mapping_state = 'automatic'
                   THEN excluded.mapping_state ELSE operating_vocabulary_terms.mapping_state END,
               mapping_method = CASE
                   WHEN operating_vocabulary_terms.mapping_state = 'automatic'
                   THEN excluded.mapping_method ELSE operating_vocabulary_terms.mapping_method END,
               confidence = CASE
                   WHEN operating_vocabulary_terms.mapping_state = 'automatic'
                   THEN excluded.confidence ELSE operating_vocabulary_terms.confidence END,
               mapping_version = CASE
                   WHEN operating_vocabulary_terms.mapping_state = 'automatic'
                   THEN excluded.mapping_version ELSE operating_vocabulary_terms.mapping_version END,
               refreshed_at = excluded.refreshed_at""",
        [
            (
                term.source_id,
                term.vocabulary_kind,
                term.source_context,
                term.raw_value,
                term.raw_fingerprint,
                term.occurrence_count,
                term.normalized_key,
                term.display_label,
                term.mapping_state,
                term.mapping_method,
                term.confidence,
                VOCABULARY_VERSION,
                term.first_seen_at,
                term.last_seen_at,
                now,
            )
            for term in terms
        ],
    )
    if commit:
        conn.commit()
    return len(terms)


def pending_terms_for_source(conn, source_id: str, *, limit: int = _OPENAI_BATCH_SIZE) -> list[VocabularyTerm]:
    """Return only unresolved, non-identity vocabulary for a deliberate pass."""
    if not vocabulary_schema_available(conn):
        return []
    limit = max(1, min(int(limit), _OPENAI_BATCH_SIZE))
    # Fetch a small safety buffer: some raw terms are retained for audit but
    # intentionally unsuitable for a model (for example, a pasted phone
    # number).  They remain pending for an accountable manual review.
    rows = conn.execute(
        """SELECT source_id, vocabulary_kind, source_context, raw_value, raw_fingerprint,
                  occurrence_count, normalized_key, display_label, mapping_state,
                  mapping_method, confidence, first_seen_at, last_seen_at
           FROM operating_vocabulary_terms
           WHERE source_id = ? AND mapping_state = 'pending'
             AND vocabulary_kind IN ('reported_issue', 'crop_product')
           ORDER BY occurrence_count DESC, vocabulary_kind, raw_value
           LIMIT ?""",
        (source_id, limit * 4),
    ).fetchall()
    return [
        term for term in (_term_from_row(row) for row in rows)
        if _safe_for_model(term.raw_value)
    ][:limit]


def suggest_pending_terms(
    conn,
    source_id: str,
    *,
    limit: int = _OPENAI_BATCH_SIZE,
    commit: bool = True,
) -> dict[str, Any]:
    """Ask Luna once for suggestions, never auto-publishing semantic mappings.

    The model receives short source phrases plus their already-known kind.  It
    never receives farmer names, identifiers, contacts, coordinates, media, or
    full source records.  Returned suggestions are stored as ``suggested`` and
    remain invisible to facts/filters until reviewed.
    """
    candidates = pending_terms_for_source(conn, source_id, limit=limit)
    if not candidates:
        return {"state": "nothing_pending", "considered": 0, "suggested": 0, "model": None}
    payload, model = openai_responses.structured_output(
        prompt=_classification_prompt(candidates),
        schema_name="operating_vocabulary_suggestions",
        schema=_classification_schema(),
    )
    if payload is None or model is None:
        return {"state": "unavailable", "considered": len(candidates), "suggested": 0, "model": None}
    suggestions = _validated_suggestions(payload, candidates)
    if suggestions:
        now = _now()
        conn.executemany(
            """UPDATE operating_vocabulary_terms
               SET normalized_key = ?, display_label = ?, mapping_state = 'suggested',
                   mapping_method = 'ai', confidence = ?, classifier_model = ?,
                   mapping_version = ?, classified_at = ?, refreshed_at = ?
               WHERE source_id = ? AND vocabulary_kind = ? AND source_context = ?
                 AND raw_fingerprint = ? AND mapping_state = 'pending'""",
            [
                (
                    suggestion["normalized_key"], suggestion["display_label"], suggestion["confidence"],
                    model, AI_MAPPING_VERSION, now, now, candidate.source_id,
                    candidate.vocabulary_kind, candidate.source_context, candidate.raw_fingerprint,
                )
                for candidate, suggestion in suggestions
            ],
        )
        if commit:
            conn.commit()
    return {
        "state": "suggested" if suggestions else "no_safe_suggestions",
        "considered": len(candidates),
        "suggested": len(suggestions),
        "model": model,
    }


def review_term(
    conn,
    term: VocabularyTerm,
    *,
    normalized_key: Optional[str],
    display_label: Optional[str],
    state: str,
    commit: bool = True,
) -> bool:
    """Approve or reject one controlled mapping for a future review surface."""
    if state not in {"reviewed", "rejected", "unmapped"}:
        raise ValueError("Vocabulary review state is invalid")
    if state == "reviewed":
        normalized_key = _validated_key(normalized_key)
        display_label = _validated_label(display_label)
        if normalized_key is None or display_label is None:
            raise ValueError("Reviewed vocabulary needs a key and display label")
    else:
        normalized_key = None
        display_label = None
    now = _now()
    result = conn.execute(
        """UPDATE operating_vocabulary_terms
           SET normalized_key = ?, display_label = ?, mapping_state = ?,
               mapping_method = 'manual', confidence = CASE WHEN ? = 'reviewed' THEN 1 ELSE NULL END,
               mapping_version = ?, reviewed_at = ?, refreshed_at = ?
           WHERE source_id = ? AND vocabulary_kind = ? AND source_context = ?
             AND raw_fingerprint = ?""",
        (
            normalized_key, display_label, state, state, MANUAL_MAPPING_VERSION, now, now,
            term.source_id, term.vocabulary_kind, term.source_context, term.raw_fingerprint,
        ),
    )
    if commit:
        conn.commit()
    return bool(result.rowcount)


def vocabulary_summary(conn, source_id: str) -> dict[str, int]:
    """Safe aggregate receipt for a CLI or settings surface; never raw terms."""
    if not vocabulary_schema_available(conn):
        return {"terms": 0, "pending": 0, "suggested": 0, "reviewed": 0, "automatic": 0}
    row = conn.execute(
        """SELECT count(*) AS terms,
                  sum(CASE WHEN mapping_state = 'pending' THEN 1 ELSE 0 END) AS pending,
                  sum(CASE WHEN mapping_state = 'suggested' THEN 1 ELSE 0 END) AS suggested,
                  sum(CASE WHEN mapping_state = 'reviewed' THEN 1 ELSE 0 END) AS reviewed,
                  sum(CASE WHEN mapping_state = 'automatic' THEN 1 ELSE 0 END) AS automatic
           FROM operating_vocabulary_terms WHERE source_id = ?""",
        (source_id,),
    ).fetchone()
    return {key: int(row[key] or 0) for key in ("terms", "pending", "suggested", "reviewed", "automatic")}


def _discover_terms(conn, source_id: str, *, fallback_at: str) -> list[VocabularyTerm]:
    terms = []
    task_rows = conn.execute(
        """SELECT trim(task_type) AS raw_value, count(*) AS occurrence_count,
                  min(COALESCE(provider_created_at, first_seen_at)) AS first_seen_at,
                  max(COALESCE(provider_completed_at, provider_started_at, provider_created_at, last_seen_at)) AS last_seen_at
           FROM trackwick_tasks
           WHERE source_id = ? AND data_quality_status = 'valid' AND trim(task_type) <> ''
           GROUP BY trim(task_type)""",
        (source_id,),
    ).fetchall()
    for row in task_rows:
        raw_value = _safe_raw(row["raw_value"])
        if raw_value is None:
            continue
        task_key = _task_kind(raw_value)
        terms.append(_term(
            source_id, "task_type", "task", raw_value, int(row["occurrence_count"] or 0),
            task_key, _task_label(task_key), "automatic", "deterministic", 1.0,
            row["first_seen_at"] or fallback_at, row["last_seen_at"] or fallback_at,
        ))
    issue_rows = conn.execute(
        """SELECT finding_kind, trim(reported_value) AS raw_value, count(*) AS occurrence_count,
                  min(observed_at) AS first_seen_at, max(observed_at) AS last_seen_at
           FROM trackwick_visit_findings
           WHERE source_id = ? AND data_quality_status = 'valid' AND trim(reported_value) <> ''
           GROUP BY finding_kind, trim(reported_value)""",
        (source_id,),
    ).fetchall()
    for row in issue_rows:
        raw_value = _safe_raw(row["raw_value"])
        context = "reported_" + str(row["finding_kind"] or "issue").strip().lower()
        if raw_value is None or context not in {"reported_disease", "reported_pest"}:
            continue
        terms.append(_term(
            source_id, "reported_issue", context, raw_value, int(row["occurrence_count"] or 0),
            None, None, "pending", "deterministic", None,
            row["first_seen_at"] or fallback_at, row["last_seen_at"] or fallback_at,
        ))
    product_rows = conn.execute(
        """SELECT input_kind, event_kind, trim(reported_product) AS raw_value, count(*) AS occurrence_count,
                  min(occurred_at) AS first_seen_at, max(occurred_at) AS last_seen_at
           FROM trackwick_crop_inputs
           WHERE source_id = ? AND data_quality_status = 'valid' AND trim(reported_product) <> ''
           GROUP BY input_kind, event_kind, trim(reported_product)""",
        (source_id,),
    ).fetchall()
    for row in product_rows:
        raw_value = _safe_raw(row["raw_value"])
        input_kind = str(row["input_kind"] or "other").strip().lower()
        event_kind = str(row["event_kind"] or "reported").strip().lower()
        if raw_value is None or input_kind not in {"pesticide", "fertilizer"}:
            continue
        terms.append(_term(
            source_id, "crop_product", f"{input_kind}:{event_kind}", raw_value,
            int(row["occurrence_count"] or 0), None, None, "pending", "deterministic", None,
            row["first_seen_at"] or fallback_at, row["last_seen_at"] or fallback_at,
        ))
    return terms


def _term(
    source_id: str, vocabulary_kind: str, source_context: str, raw_value: str,
    occurrence_count: int, normalized_key: Optional[str], display_label: Optional[str],
    mapping_state: str, mapping_method: str, confidence: Optional[float],
    first_seen_at: str, last_seen_at: str,
) -> VocabularyTerm:
    return VocabularyTerm(
        source_id=source_id,
        vocabulary_kind=vocabulary_kind,
        source_context=source_context,
        raw_value=raw_value,
        raw_fingerprint=_fingerprint(vocabulary_kind, source_context, raw_value),
        occurrence_count=max(0, occurrence_count),
        normalized_key=normalized_key,
        display_label=display_label,
        mapping_state=mapping_state,
        mapping_method=mapping_method,
        confidence=confidence,
        first_seen_at=str(first_seen_at),
        last_seen_at=str(last_seen_at),
    )


def _term_from_row(row: Mapping[str, Any]) -> VocabularyTerm:
    row = dict(row)
    return VocabularyTerm(
        source_id=str(row["source_id"]), vocabulary_kind=str(row["vocabulary_kind"]),
        source_context=str(row["source_context"]), raw_value=str(row["raw_value"]),
        raw_fingerprint=str(row["raw_fingerprint"]), occurrence_count=int(row["occurrence_count"] or 0),
        normalized_key=row.get("normalized_key"), display_label=row.get("display_label"),
        mapping_state=str(row["mapping_state"]), mapping_method=str(row["mapping_method"]),
        confidence=None if row.get("confidence") is None else float(row["confidence"]),
        first_seen_at=str(row["first_seen_at"]), last_seen_at=str(row["last_seen_at"]),
    )


def _classification_prompt(candidates: Sequence[VocabularyTerm]) -> str:
    terms = [
        {
            "id": str(index),
            "kind": term.vocabulary_kind,
            "context": term.source_context,
            "source_phrase": term.raw_value,
            "uses": term.occurrence_count,
        }
        for index, term in enumerate(candidates)
    ]
    return """You maintain a private operating vocabulary for a farm team.
For each source phrase, propose at most a spelling/casing/translation normalization.
Do not make a diagnosis, infer an ingredient, make an agronomy recommendation,
identify a person, or add a fact not present in the phrase. For reported issues,
the display label must remain a source-reported label, not a diagnosis. For crop
products, do not guess the product family. If a safe normalization is unclear,
return outcome `keep_raw`. Return exactly one item for every input id.

INPUT TERMS:
""" + json.dumps(terms, ensure_ascii=True, separators=(",", ":"))


def _classification_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "outcome": {"type": "string", "enum": ["suggest", "keep_raw"]},
                        "normalized_key": {"type": ["string", "null"]},
                        "display_label": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["id", "outcome", "normalized_key", "display_label", "confidence"],
                },
            },
        },
        "required": ["items"],
    }


def _validated_suggestions(
    payload: Mapping[str, Any], candidates: Sequence[VocabularyTerm],
) -> list[tuple[VocabularyTerm, dict[str, Any]]]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return []
    candidates_by_id = {str(index): term for index, term in enumerate(candidates)}
    accepted: list[tuple[VocabularyTerm, dict[str, Any]]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        item_id = str(item.get("id") or "")
        candidate = candidates_by_id.get(item_id)
        if candidate is None or item_id in seen:
            continue
        seen.add(item_id)
        if item.get("outcome") != "suggest":
            continue
        normalized_key = _validated_key(item.get("normalized_key"))
        display_label = _validated_label(item.get("display_label"))
        confidence = item.get("confidence")
        if normalized_key is None or display_label is None or not isinstance(confidence, (int, float)):
            continue
        confidence = float(confidence)
        if not 0 <= confidence <= 1:
            continue
        accepted.append((candidate, {
            "normalized_key": normalized_key,
            "display_label": display_label,
            "confidence": confidence,
        }))
    return accepted


def _safe_raw(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split()).strip()
    return value if 1 <= len(value) <= 600 else None


def _safe_for_model(value: str) -> bool:
    """Keep suspicious source phrases private even during the explicit pass."""
    if not 1 <= len(value) <= 120:
        return False
    return not any(pattern.search(value) for pattern in (
        _EMAIL_PATTERN, _URL_PATTERN, _LONG_NUMBER_PATTERN,
    ))


def _validated_key(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if _KEY_PATTERN.fullmatch(value) else None


def _validated_label(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split()).strip()
    return value if 1 <= len(value) <= 160 else None


def _fingerprint(vocabulary_kind: str, source_context: str, raw_value: str) -> str:
    normalized = "\x1f".join((vocabulary_kind, source_context, raw_value.casefold()))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _task_kind(value: str) -> str:
    value = re.sub(r"[^\w]+", " ", value.casefold())
    if "visit" in value:
        return "visit"
    if "registration" in value or "register" in value:
        return "registration"
    if "soil" in value:
        return "soil"
    if "query" in value or "question" in value:
        return "query"
    if "agronomy" in value or "team" in value:
        return "team_work"
    return "other"


def _task_label(value: str) -> str:
    return {
        "visit": "Field visit",
        "registration": "Farm registration",
        "soil": "Soil work",
        "query": "Farmer query",
        "team_work": "Team work",
        "other": "Other work",
    }[value]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
