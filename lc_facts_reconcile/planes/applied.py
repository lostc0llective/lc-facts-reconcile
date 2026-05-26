"""Plane 2 — applied records from tone-of-voice-rollout/applied/.

Each applied record is a markdown file documenting a field change:
  field, handle(s) affected, before/after values, source cited.

We parse a best-effort extraction from the markdown structure.
Records are treated as "what was applied to live Shopify per LC's own log."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..diff import PlaneData

APPLIED_ROOT = Path.home() / "Claude/cowork/tone-of-voice-rollout/applied"

_FIELD_MAP: dict[str, str] = {
    "print-story": "print_story",
    "seo": "seo.description",
    "alt-text": "alt_text",
    "exif": "exif",
    "series-about": "series.summary",
    "series-chronology": "series.chronology",
    "subject-description": "subject_description",
}


@dataclass
class AppliedEntry:
    record_path: str
    handles: list[str]
    field: str
    surface: str
    before: str | None
    after: str
    source_cited: str | None
    record_date: str | None


@dataclass
class AppliedReadResult:
    entries: list[AppliedEntry]
    plane_by_handle: dict[str, PlaneData]


def read_applied(
    handles: list[str] | None = None,
    since: date | None = None,
) -> AppliedReadResult:
    """Walk applied/* and build per-handle PlaneData objects."""
    if not APPLIED_ROOT.exists():
        return AppliedReadResult(entries=[], plane_by_handle={})

    entries: list[AppliedEntry] = []
    for md_file in APPLIED_ROOT.rglob("*.md"):
        if since and _file_is_before(md_file, since):
            continue

        subdir = md_file.parent.name
        surface = _FIELD_MAP.get(subdir, subdir)

        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        parsed = _parse_applied_record(text, str(md_file), surface)
        if parsed:
            if handles is None or any(h in handles for h in parsed.handles):
                entries.append(parsed)

    plane_by_handle: dict[str, PlaneData] = {}
    for entry in entries:
        for handle in entry.handles:
            if handle not in plane_by_handle:
                plane_by_handle[handle] = PlaneData()
            key = (entry.surface, entry.field)
            plane_by_handle[handle].values[key] = entry.after

    return AppliedReadResult(entries=entries, plane_by_handle=plane_by_handle)


def _file_is_before(path: Path, since: date) -> bool:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
        return mtime < since
    except OSError:
        return False


def _parse_applied_record(text: str, path: str, surface: str) -> AppliedEntry | None:
    handles = _extract_list_field(text, r"(?:handle|series|product)s?")
    if not handles:
        handles = _infer_handle_from_path(path)

    after = _extract_field(text, r"after|new.value|applied")
    if not after:
        return None

    before = _extract_field(text, r"before|old.value|previous")
    field_name = _extract_field(text, r"field|metafield|surface") or surface
    source = _extract_field(text, r"source|based.on|sourced")
    record_date = _extract_date(path)

    return AppliedEntry(
        record_path=path,
        handles=handles,
        field=field_name,
        surface=surface,
        before=before,
        after=after,
        source_cited=source,
        record_date=record_date,
    )


def _extract_field(text: str, pattern: str) -> str | None:
    m = re.search(
        r"(?i)\*{0,2}(?:" + pattern + r")[:\s*]+\*{0,2}\s*(.+?)(?:\n|\Z)",
        text,
    )
    if m:
        return m.group(1).strip().strip("*").strip()
    return None


def _extract_list_field(text: str, pattern: str) -> list[str]:
    m = re.search(
        r"(?i)\*{0,2}(?:" + pattern + r")[:\s*]+\*{0,2}\s*(.+?)(?:\n|\Z)",
        text,
    )
    if not m:
        return []
    raw = m.group(1).strip().strip("*").strip()
    parts = re.split(r"[,;]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _infer_handle_from_path(path: str) -> list[str]:
    stem = Path(path).stem
    parts = stem.split("-")
    for i in range(len(parts), 0, -1):
        candidate = "-".join(parts[:i])
        if len(candidate) > 4:
            return [candidate]
    return []


def _extract_date(path: str) -> str | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path)
    if m:
        return m.group(1)
    return None
