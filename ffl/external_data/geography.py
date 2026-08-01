"""Import a pinned India Village Finder release as FFL reference geography.

This module uses the project's LGD-derived flat CSV only.  It does not ingest
approximate coordinates, maps, cadastral parcels, market prices, weather,
schemes, or soil-model estimates bundled elsewhere in that project.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional, Tuple
from urllib.request import urlopen


VILLAGE_FINDER_REPOSITORY = "https://github.com/mchittineni/india-village-finder"
_RAW_HOST = "raw.githubusercontent.com"
_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
_PINCODE_PATTERN = re.compile(r"[0-9]{6}")
_REQUIRED_COLUMNS = {
    "State", "District", "District Code", "Mandal", "Mandal Code", "Village", "Village Code",
    "Pincode", "Village (Native)", "Native Source",
}
_STATE_FILES = {
    "andhra_pradesh": ("Andhra Pradesh", "28"),
    "telangana": ("Telangana", "36"),
    "karnataka": ("Karnataka", "29"),
    "tamil_nadu": ("Tamil Nadu", "33"),
    "kerala": ("Kerala", "32"),
}
_NATIVE_SOURCES = {"authoritative", "transliterated"}


@dataclass(frozen=True)
class GeographyDataset:
    state_slug: str
    state_name: str
    state_code: str
    revision: str
    content_sha256: str
    source_url: str
    attribution: str


@dataclass(frozen=True)
class Place:
    kind: str
    code: str
    parent_code: Optional[str]
    canonical_name: str
    native_name: Optional[str]
    native_name_source: Optional[str]
    pincode: Optional[str]


@dataclass(frozen=True)
class GeographyImport:
    dataset: GeographyDataset
    places: Tuple[Place, ...]

    def places_of_kind(self, kind: str) -> Tuple[Place, ...]:
        return tuple(place for place in self.places if place.kind == kind)

    def village(self, village_code: str) -> Place:
        matches = [place for place in self.places if place.kind == "village" and place.code == village_code]
        if len(matches) != 1:
            raise LookupError("village code is not uniquely present in this geography dataset")
        return matches[0]


def village_finder_raw_url(state_slug: str, revision: str) -> str:
    """Build the one allowed release URL; branches and mutable refs are forbidden."""
    _state_details(state_slug)
    if _REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("Village Finder revision must be a full immutable git SHA")
    return "https://{0}/mchittineni/india-village-finder/{1}/{2}/data/{2}_villages.csv".format(
        _RAW_HOST, revision, state_slug
    )


def fetch_village_finder_csv(
    state_slug: str, revision: str, expected_sha256: str,
    opener: Optional[Callable[[str], bytes]] = None,
) -> Tuple[GeographyDataset, bytes]:
    """Fetch one pinned CSV and verify it before any parsing or persistence.

    Network access is explicit at the call site; FFL's normal test and preview
    paths never call this function.  The immutable SHA and content hash prevent
    a mutable GitHub branch or a changed source file from silently changing FFL.
    """
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("Village Finder content hash must be a lowercase SHA-256")
    url = village_finder_raw_url(state_slug, revision)
    content = (opener or _download)(url)
    if not isinstance(content, bytes):
        raise ValueError("Village Finder downloader must return bytes")
    content_hash = hashlib.sha256(content).hexdigest()
    if content_hash != expected_sha256:
        raise ValueError("Village Finder content hash does not match the reviewed release")
    state_name, state_code = _state_details(state_slug)
    return GeographyDataset(
        state_slug, state_name, state_code, revision, content_hash, url, _attribution(),
    ), content


def parse_village_finder_csv(dataset: GeographyDataset, content: bytes) -> GeographyImport:
    """Normalise the flat CSV into a strict state/district/sub-district/village tree."""
    if hashlib.sha256(content).hexdigest() != dataset.content_sha256:
        raise ValueError("Village Finder content does not match dataset manifest")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Village Finder CSV must be UTF-8") from error
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not _REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise ValueError("Village Finder CSV has an unsupported schema")

    districts: Dict[str, Place] = {}
    subdistricts: Dict[str, Place] = {}
    villages: Dict[str, Place] = {}
    for row_number, row in enumerate(reader, start=2):
        state = _text(row, "State", row_number)
        if state != dataset.state_name:
            raise ValueError("Village Finder row state does not match the reviewed dataset")
        district_code = _code(row, "District Code", row_number)
        subdistrict_code = _code(row, "Mandal Code", row_number)
        village_code = _code(row, "Village Code", row_number)
        district = Place("district", district_code, dataset.state_code, _text(row, "District", row_number), None, None, None)
        subdistrict = Place("subdistrict", subdistrict_code, district_code, _text(row, "Mandal", row_number), None, None, None)
        native_name = _optional_text(row.get("Village (Native)"))
        native_source = _optional_text(row.get("Native Source"))
        if native_source is not None and native_source not in _NATIVE_SOURCES:
            raise ValueError("Village Finder native-name provenance is unsupported")
        if native_name is None and native_source:
            raise ValueError("Village Finder native-name provenance requires a native name")
        village = Place(
            "village", village_code, subdistrict_code, _text(row, "Village", row_number), native_name,
            native_source or None, _pincode(row.get("Pincode"), row_number),
        )
        _consistent(districts, district)
        _consistent(subdistricts, subdistrict)
        _consistent(villages, village)

    if not villages:
        raise ValueError("Village Finder CSV contains no villages")
    return GeographyImport(dataset, tuple(
        sorted(districts.values(), key=lambda item: item.code)
        + sorted(subdistricts.values(), key=lambda item: item.code)
        + sorted(villages.values(), key=lambda item: item.code)
    ))


def _download(url: str) -> bytes:
    # The URL comes exclusively from village_finder_raw_url above.
    with urlopen(url, timeout=20) as response:  # nosec B310 - allow-listed immutable GitHub URL
        return response.read()


def _state_details(state_slug: str) -> Tuple[str, str]:
    try:
        return _STATE_FILES[state_slug]
    except KeyError as error:
        raise ValueError("Village Finder state must be one of its five supported states") from error


def _text(row: Dict[str, str], key: str, row_number: int) -> str:
    value = _optional_text(row.get(key))
    if value is None:
        raise ValueError("Village Finder row {0} is missing {1}".format(row_number, key))
    return value


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _code(row: Dict[str, str], key: str, row_number: int) -> str:
    value = _text(row, key, row_number)
    if not value.isdigit():
        raise ValueError("Village Finder row {0} has an invalid {1}".format(row_number, key))
    return value


def _pincode(value: Optional[str], row_number: int) -> Optional[str]:
    parsed = _optional_text(value)
    if parsed is not None and _PINCODE_PATTERN.fullmatch(parsed) is None:
        raise ValueError("Village Finder row {0} has an invalid Pincode".format(row_number))
    return parsed


def _consistent(existing: Dict[str, Place], candidate: Place) -> None:
    prior = existing.get(candidate.code)
    if prior is not None and prior != candidate:
        raise ValueError("Village Finder code maps to conflicting parent or name")
    existing[candidate.code] = candidate


def _attribution() -> str:
    return (
        "Contains administrative data from the Local Government Directory (LGD), Ministry of Panchayati Raj, "
        "Government of India, used under the Government Open Data License – India (GODL-India), via the "
        "mchittineni/india-village-finder reviewed release."
    )
