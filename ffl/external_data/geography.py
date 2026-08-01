"""Pinned LGD-derived reference geography from India Village Finder.

The source supports only Andhra Pradesh, Telangana, Karnataka, Tamil Nadu,
and Kerala.  It is administrative reference data, not a farm geocoder: a PIN
is not a coordinate and this lane never imports parcel geometry or binds an
operating unit automatically.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple
from urllib.request import urlopen


VILLAGE_FINDER_REPOSITORY = "https://github.com/mchittineni/india-village-finder"
_RAW_HOST = "raw.githubusercontent.com"
_GIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PINCODE = re.compile(r"[0-9]{6}")
_REQUIRED_COLUMNS = {
    "State", "District", "District Code", "Mandal", "Mandal Code", "Village",
    "Village (Native)", "Native Source", "Village Code", "Pincode",
}
_STATE_DETAILS = {
    "andhra_pradesh": ("Andhra Pradesh", "28"),
    "telangana": ("Telangana", "36"),
    "karnataka": ("Karnataka", "29"),
    "tamil_nadu": ("Tamil Nadu", "33"),
    "kerala": ("Kerala", "32"),
}
_NATIVE_NAME_SOURCES = {"authoritative", "transliterated"}


@dataclass(frozen=True)
class ReviewedVillageFinderRelease:
    """A human-approved immutable source identity required before any fetch."""

    state_slug: str
    revision: str
    content_sha256: str
    review_reference: str

    @property
    def source_url(self) -> str:
        _state_details(self.state_slug)
        if _GIT_SHA.fullmatch(self.revision) is None:
            raise ValueError("Village Finder revision must be a full immutable git SHA")
        return (
            "https://{host}/mchittineni/india-village-finder/{revision}/{state}/data/"
            "{state}_villages.csv"
        ).format(host=_RAW_HOST, revision=self.revision, state=self.state_slug)

    def validate(self) -> None:
        _state_details(self.state_slug)
        if _GIT_SHA.fullmatch(self.revision) is None:
            raise ValueError("Village Finder revision must be a full immutable git SHA")
        if _SHA256.fullmatch(self.content_sha256) is None:
            raise ValueError("Village Finder content hash must be a lowercase SHA-256")
        if not isinstance(self.review_reference, str) or not self.review_reference.strip():
            raise ValueError("Village Finder release requires a review reference")


@dataclass(frozen=True)
class GeographyDataset:
    state_slug: str
    state_name: str
    state_code: str
    revision: str
    content_sha256: str
    source_url: str
    review_reference: str
    attribution: str


@dataclass(frozen=True)
class VillageReference:
    """One hierarchy node ready to become a reviewed import-row candidate."""

    kind: str
    code: str
    parent_code: str
    canonical_name: str
    native_name: Optional[str]
    native_name_source: Optional[str]
    pincode: Optional[str]


@dataclass(frozen=True)
class GeographyImport:
    dataset: GeographyDataset
    references: Tuple[VillageReference, ...]

    def villages(self) -> Tuple[VillageReference, ...]:
        return tuple(reference for reference in self.references if reference.kind == "village")

    def import_row_candidates(self) -> Tuple[Dict[str, object], ...]:
        """Return safe import-row mappings; persistence and publication stay external."""
        return tuple(
            {
                "source_key": "village-finder-lgd",
                "state_slug": self.dataset.state_slug,
                "state_code": self.dataset.state_code,
                "revision": self.dataset.revision,
                "content_sha256": self.dataset.content_sha256,
                "source_url": self.dataset.source_url,
                "review_reference": self.dataset.review_reference,
                "place_kind": reference.kind,
                "place_code": reference.code,
                "parent_code": reference.parent_code,
                "canonical_name": reference.canonical_name,
                "native_name": reference.native_name,
                "native_name_source": reference.native_name_source,
                "pincode": reference.pincode,
            }
            for reference in self.references
        )


def fetch_reviewed_village_finder_csv(
    release: ReviewedVillageFinderRelease,
    opener: Optional[Callable[[str], bytes]] = None,
) -> Tuple[GeographyDataset, bytes]:
    """Fetch one already-reviewed file and reject it if any source identity changed.

    This is explicit I/O.  Normal application startup, tests, and previews do
    not call it.  A moving branch name, missing review reference, or unexpected
    content hash fails before parsing or persistence.
    """
    release.validate()
    content = (opener or _download)(release.source_url)
    if not isinstance(content, bytes):
        raise ValueError("Village Finder downloader must return bytes")
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != release.content_sha256:
        raise ValueError("Village Finder content hash does not match the reviewed release")
    state_name, state_code = _state_details(release.state_slug)
    return GeographyDataset(
        state_slug=release.state_slug,
        state_name=state_name,
        state_code=state_code,
        revision=release.revision,
        content_sha256=actual_hash,
        source_url=release.source_url,
        review_reference=release.review_reference.strip(),
        attribution=(
            "Contains administrative data from the Local Government Directory (LGD), Ministry of "
            "Panchayati Raj, Government of India, via the reviewed mchittineni/india-village-finder "
            "release; retain the Government Open Data License – India (GODL-India) attribution."
        ),
    ), content


def parse_village_finder_csv(dataset: GeographyDataset, content: bytes) -> GeographyImport:
    """Normalise a verified release into a strict district/subdistrict/village tree."""
    if hashlib.sha256(content).hexdigest() != dataset.content_sha256:
        raise ValueError("Village Finder content does not match dataset manifest")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Village Finder CSV must be UTF-8") from error
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not _REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise ValueError("Village Finder CSV has an unsupported schema")

    districts: Dict[str, VillageReference] = {}
    subdistricts: Dict[str, VillageReference] = {}
    villages: Dict[str, VillageReference] = {}
    for row_number, row in enumerate(reader, start=2):
        if _text(row, "State", row_number) != dataset.state_name:
            raise ValueError("Village Finder row state does not match the reviewed dataset")
        district_code = _code(row, "District Code", row_number)
        subdistrict_code = _code(row, "Mandal Code", row_number)
        village_code = _code(row, "Village Code", row_number)
        district = VillageReference(
            "district", district_code, dataset.state_code, _text(row, "District", row_number), None, None, None,
        )
        subdistrict = VillageReference(
            "subdistrict", subdistrict_code, district_code, _text(row, "Mandal", row_number), None, None, None,
        )
        native_name = _optional_text(row.get("Village (Native)"))
        native_source = _optional_text(row.get("Native Source"))
        if native_source is not None and native_source not in _NATIVE_NAME_SOURCES:
            raise ValueError("Village Finder native-name provenance is unsupported")
        if native_name is None and native_source is not None:
            raise ValueError("Village Finder native-name provenance requires a native name")
        village = VillageReference(
            "village", village_code, subdistrict_code, _text(row, "Village", row_number), native_name,
            native_source, _pincode(row.get("Pincode"), row_number),
        )
        _consistent(districts, district)
        _consistent(subdistricts, subdistrict)
        _consistent(villages, village)

    if not villages:
        raise ValueError("Village Finder CSV contains no villages")
    return GeographyImport(
        dataset,
        tuple(
            sorted(districts.values(), key=lambda item: item.code)
            + sorted(subdistricts.values(), key=lambda item: item.code)
            + sorted(villages.values(), key=lambda item: item.code)
        ),
    )


def _download(url: str) -> bytes:
    # The URL is built only from a five-state allow-list and a full immutable SHA.
    with urlopen(url, timeout=20) as response:  # nosec B310 - constrained immutable GitHub URL
        return response.read()


def _state_details(state_slug: str) -> Tuple[str, str]:
    try:
        return _STATE_DETAILS[state_slug]
    except KeyError as error:
        raise ValueError("Village Finder supports only Andhra Pradesh, Telangana, Karnataka, Tamil Nadu, and Kerala") from error


def _text(row: Dict[str, Optional[str]], key: str, row_number: int) -> str:
    parsed = _optional_text(row.get(key))
    if parsed is None:
        raise ValueError("Village Finder row {0} is missing {1}".format(row_number, key))
    return parsed


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    parsed = value.strip()
    return parsed or None


def _code(row: Dict[str, Optional[str]], key: str, row_number: int) -> str:
    parsed = _text(row, key, row_number)
    if not parsed.isdigit():
        raise ValueError("Village Finder row {0} has an invalid {1}".format(row_number, key))
    return parsed


def _pincode(value: Optional[str], row_number: int) -> Optional[str]:
    parsed = _optional_text(value)
    if parsed is not None and _PINCODE.fullmatch(parsed) is None:
        raise ValueError("Village Finder row {0} has an invalid Pincode".format(row_number))
    return parsed


def _consistent(existing: Dict[str, VillageReference], candidate: VillageReference) -> None:
    prior = existing.get(candidate.code)
    if prior is not None and prior != candidate:
        raise ValueError("Village Finder code maps to conflicting parent or name")
    existing[candidate.code] = candidate
