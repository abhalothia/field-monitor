"""Bounded UTF-8 CSV bundle parser for reviewed TrackOlap exports."""

from __future__ import annotations

import csv
from io import BytesIO, TextIOWrapper
from pathlib import PurePosixPath
from typing import Mapping
from zipfile import BadZipFile, ZipFile

from .contracts import ParsedBundle, ParsedRow
from .mapping import MappingManifest, normalise_row


MAX_ARCHIVE_ENTRIES = 6
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000


def parse_csv_bundle(content: bytes, manifest: MappingManifest) -> ParsedBundle:
    """Parse only approved CSV filenames and validate every row via the mapper.

    The parser never selects a similarly named column.  A missing reviewed
    source column becomes a row error for human repair.
    """

    if not isinstance(content, bytes) or not content:
        raise ValueError("CSV bundle content is required")
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise ValueError("CSV bundle must be a valid ZIP archive") from exc

    rows: list[ParsedRow] = []
    errors: list[Mapping[str, str]] = []
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise ValueError(f"CSV bundle has more than {MAX_ARCHIVE_ENTRIES} files")
        uncompressed_bytes = sum(info.file_size for info in infos)
        if uncompressed_bytes > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("CSV bundle exceeds uncompressed size limit")

        seen_feeds: set[str] = set()
        parsed_count = 0
        for info in infos:
            feed = _feed_from_filename(info.filename)
            if feed is None:
                errors.append(
                    {"code": "unsafe_or_unknown_file", "field": "filename", "message": info.filename}
                )
                continue
            if feed in seen_feeds:
                errors.append(
                    {"code": "duplicate_feed_file", "field": "filename", "message": info.filename}
                )
                continue
            seen_feeds.add(feed)
            if feed not in manifest.feeds:
                errors.append(
                    {"code": "feed_not_mapped", "field": "filename", "message": info.filename}
                )
                continue

            try:
                source = TextIOWrapper(archive.open(info, "r"), encoding="utf-8-sig", newline="")
                reader = csv.DictReader(source)
                reviewed_columns = set(manifest.fields_for(feed).values())
                unknown_headers = sorted(
                    header for header in (reader.fieldnames or [])
                    if header is not None and header not in reviewed_columns
                )
                if unknown_headers:
                    errors.append(
                        {
                            "code": "unsupported_source_header",
                            "field": "filename",
                            "message": feed + ".csv contains unmapped columns: " + ", ".join(unknown_headers),
                        }
                    )
                for row_number, raw in enumerate(reader, start=2):
                    parsed_count += 1
                    if parsed_count > MAX_ROWS:
                        raise ValueError("CSV bundle exceeds row limit")
                    rows.append(
                        ParsedRow(
                            feed=feed,
                            row_number=row_number,
                            result=normalise_row(feed, raw, manifest),
                        )
                    )
            except UnicodeDecodeError as exc:
                errors.append(
                    {"code": "invalid_encoding", "field": "filename", "message": info.filename}
                )
            finally:
                if "source" in locals():
                    source.close()

    return ParsedBundle(rows=tuple(rows), errors=tuple(errors))


def _feed_from_filename(filename: str) -> str | None:
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        return None
    if path.suffix.lower() != ".csv":
        return None
    feed = path.stem
    return feed if feed else None
