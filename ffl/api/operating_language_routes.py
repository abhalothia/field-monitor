"""Manager-only review endpoints for private operating language packs."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.communications.auth import require_manager
from ffl.persistence import repository
from ffl.services import operating_language
from ffl.services.trackwick_ingest import SOURCE_KEY


router = APIRouter(prefix="/api/v1/operating-language")


class VocabularyLocalizationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vocabulary_kind: Literal["task_type", "reported_issue", "crop_product"]
    source_context: str = Field(min_length=1, max_length=160)
    raw_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: Literal["reviewed", "rejected", "unmapped"]
    display_label: Optional[str] = Field(default=None, max_length=120)
    search_aliases: list[str] = Field(default_factory=list, max_length=4)


class PlaceLocalizationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_key: str = Field(min_length=3, max_length=320)
    state: Literal["reviewed", "rejected", "unmapped"]
    village_label: Optional[str] = Field(default=None, max_length=120)
    block_label: Optional[str] = Field(default=None, max_length=120)
    district_label: Optional[str] = Field(default=None, max_length=120)
    search_aliases: list[str] = Field(default_factory=list, max_length=4)


class IssueGroupReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_context: Literal["reported_disease", "reported_pest"]
    normalized_key: str = Field(min_length=1, max_length=80)
    state: Literal["reviewed", "rejected"]


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _source_id(conn) -> str:
    source = repository.get_source_registry_by_key(conn, SOURCE_KEY)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operating language data is unavailable")
    return source.id


def _vocabulary_candidate(payload: VocabularyLocalizationReview, source_id: str) -> operating_language.VocabularyLocalizationCandidate:
    return operating_language.VocabularyLocalizationCandidate(
        source_id=source_id,
        vocabulary_kind=payload.vocabulary_kind,
        source_context=payload.source_context,
        raw_fingerprint=payload.raw_fingerprint,
        display_label="reviewed label",
        occurrence_count=0,
        first_seen_at="",
        last_seen_at="",
    )


def _place_candidate(payload: PlaceLocalizationReview, source_id: str) -> operating_language.PlaceLocalizationCandidate:
    return operating_language.PlaceLocalizationCandidate(
        source_id=source_id, place_key=payload.place_key, village_name=None,
        block_name=None, district_name=None, first_seen_at="", last_seen_at="",
    )


@router.get("")
def language_board(
    request: Request,
    limit: int = Query(default=24, ge=1, le=100),
    _manager_id: str = Depends(require_manager),
) -> dict:
    """Read a compact review board; no raw source phrase is returned."""
    conn = _connection(request)
    source_id = _source_id(conn)
    return {
        "summary": operating_language.language_summary(conn, source_id),
        "vocabulary": operating_language.vocabulary_localization_review_queue(conn, source_id, limit=limit),
        "places": operating_language.place_localization_review_queue(conn, source_id, limit=limit),
        "issue_groups": operating_language.issue_group_review_queue(conn, source_id, limit=limit),
    }


@router.patch("/vocabulary")
def review_vocabulary(
    payload: VocabularyLocalizationReview,
    request: Request,
    _manager_id: str = Depends(require_manager),
) -> dict:
    conn = _connection(request)
    accepted = operating_language.review_vocabulary_localization(
        conn, _vocabulary_candidate(payload, _source_id(conn)),
        display_label=payload.display_label, search_aliases=payload.search_aliases, state=payload.state,
    )
    if not accepted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="language suggestion was not found")
    return {"state": payload.state}


@router.patch("/places")
def review_place(
    payload: PlaceLocalizationReview,
    request: Request,
    _manager_id: str = Depends(require_manager),
) -> dict:
    conn = _connection(request)
    accepted = operating_language.review_place_localization(
        conn, _place_candidate(payload, _source_id(conn)),
        village_label=payload.village_label, block_label=payload.block_label,
        district_label=payload.district_label, search_aliases=payload.search_aliases,
        state=payload.state,
    )
    if not accepted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="place language suggestion was not found")
    return {"state": payload.state}


@router.patch("/issue-groups")
def review_issue_group(
    payload: IssueGroupReview,
    request: Request,
    _manager_id: str = Depends(require_manager),
) -> dict:
    conn = _connection(request)
    accepted = operating_language.review_issue_group(
        conn, _source_id(conn), source_context=payload.source_context,
        normalized_key=payload.normalized_key, state=payload.state,
    )
    if not accepted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue group was not found")
    return {"state": payload.state}
