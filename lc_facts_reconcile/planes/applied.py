"""Plane 2 — applied records: what LC's own apply scripts logged as written to
live Shopify.

Two source roots, both under ~/Claude/cowork/brand-voice/:
  applied/            — top-level, for applied records not tied to a named audit
  audits/*/applied/   — per-audit-pass records (e.g. the LOS7-1870 factual
                         re-audit apply, one file per series)

Each series-level file holds one product block per product it touched:

    **Field:** `custom.subject_description` (multi_line_text_field)

    ### `<product-handle>`

    **Before:**

    > ...

    **After:**

    > ...

This is the ONLY shape read_applied() extracts. The retired free-form regex
scraper (LOS7-1587) is gone: tested against both the archived tone-of-voice-
rollout corpus and the one hand-written sprint report that has since landed in
applied/, it reliably produced garbage — e.g. one record yielded
handles=['links (5 -> 15 total). lc-map placeholder HTML comment in the Now
section.'], which matches no real handle and could never usefully back or
contradict anything. A file that doesn't match the structured shape above is
skipped rather than run through prose heuristics (LOS7-1929). The archived
~/Claude/archive/tone-of-voice-rollout/applied/ corpus is frozen (nothing
writes new records there) and, per README.md's own findings, contains nothing
this parser could extract reliably either way — it is no longer walked.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..diff import PlaneData

logger = logging.getLogger(__name__)

BRAND_VOICE_ROOT = Path.home() / "Claude/cowork/brand-voice"
APPLIED_ROOT = BRAND_VOICE_ROOT / "applied"
AUDITS_ROOT = BRAND_VOICE_ROOT / "audits"


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


def _discover_applied_roots() -> list[Path]:
    """Every directory read_applied() walks for *.md applied records.

    Module-level constants (not a hardcoded literal here) so tests can
    monkeypatch APPLIED_ROOT / AUDITS_ROOT the same way test_captions_plane.py
    monkeypatches CAPTIONS_ROOT.
    """
    roots: list[Path] = []
    if APPLIED_ROOT.exists():
        roots.append(APPLIED_ROOT)
    if AUDITS_ROOT.exists():
        for child in sorted(AUDITS_ROOT.iterdir()):
            candidate = child / "applied"
            if candidate.is_dir():
                roots.append(candidate)
    return roots


def read_applied(
    handles: list[str] | None = None,
    since: date | None = None,
) -> AppliedReadResult:
    """Walk every applied root and build per-series PlaneData objects.

    plane_by_handle is keyed by SERIES handle (matching library.py and
    shopify.py's per-series call shape) even though each value inside carries
    per-PRODUCT surfaces (f"product.<product-handle>", field) — the same
    multiplexing pattern those two planes already use.
    """
    logger.debug("read_applied(handles=%s, since=%s) starting", handles, since)
    roots = _discover_applied_roots()
    if not roots:
        logger.debug("read_applied: no applied roots exist")
        return AppliedReadResult(entries=[], plane_by_handle={})

    entries: list[AppliedEntry] = []
    for root in roots:
        for md_file in sorted(root.rglob("*.md")):
            if since and _file_is_before(md_file, since):
                continue

            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            parsed = _parse_applied_file(text, str(md_file))
            if not parsed:
                logger.debug("read_applied: %s did not match the structured record shape, skipped", md_file)
                continue

            for entry in parsed:
                if handles is None or any(h in handles for h in entry.handles):
                    entries.append(entry)

    # Sort so the chronologically LATEST record wins when more than one
    # applied record touches the same (surface, field) for a handle.
    # root.rglob() order is filesystem-dependent, not chronological, and an
    # older correction silently overwriting a newer one in the dict build
    # below would reintroduce exactly the false-positive this rewrite exists
    # to fix (LOS7-1929) on the next audit pass.
    entries.sort(key=lambda e: e.record_date or "")

    plane_by_handle: dict[str, PlaneData] = {}
    for entry in entries:
        for handle in entry.handles:
            if handle not in plane_by_handle:
                plane_by_handle[handle] = PlaneData()
            key = (entry.surface, entry.field)
            plane_by_handle[handle].values[key] = entry.after

    logger.debug("read_applied finished — %d entries across %d handles", len(entries), len(plane_by_handle))
    return AppliedReadResult(entries=entries, plane_by_handle=plane_by_handle)


def _file_is_before(path: Path, since: date) -> bool:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
        return mtime < since
    except OSError:
        return False


# One ### `<product-handle>` section per product, each with its own Before/
# After blockquote. The lack of a "> " line after a header ends the capture
# naturally (blank lines and the next "### " don't start with ">"), so no
# explicit lookahead terminator is needed.
_PRODUCT_BLOCK_RE = re.compile(
    r"(?m)^###\s+`([^`]+)`\s*\n"
    r"(?:^[ \t]*\n)*"
    r"\*\*Before:\*\*\s*\n"
    r"(?:^[ \t]*\n)*"
    r"((?:^>.*(?:\n|\Z))+)"
    r"(?:^[ \t]*\n)*"
    r"\*\*After:\*\*\s*\n"
    r"(?:^[ \t]*\n)*"
    r"((?:^>.*(?:\n|\Z))+)"
)

_FIELD_HEADER_RE = re.compile(r"(?im)^\*\*Field:\*\*\s*`([^`]+)`")
_APPLIED_DATE_RE = re.compile(r"(?im)^\*\*Applied:\*\*\s*(\d{4}-\d{2}-\d{2})")
_ISSUE_HEADER_RE = re.compile(r"(?im)^\*\*Issue:\*\*\s*(.+)$")


def _parse_applied_file(text: str, path: str) -> list[AppliedEntry]:
    """Parse one applied-record file into one AppliedEntry per product block.

    Returns an empty list for anything that isn't the structured per-series,
    per-product shape — never guesses at unstructured prose.
    """
    blocks = list(_PRODUCT_BLOCK_RE.finditer(text))
    if not blocks:
        return []

    series_handle = Path(path).stem

    field_m = _FIELD_HEADER_RE.search(text)
    field_name = _normalise_metafield(field_m.group(1)) if field_m else "subject_description"

    date_m = _APPLIED_DATE_RE.search(text)
    record_date = date_m.group(1) if date_m else _extract_date(path)

    issue_m = _ISSUE_HEADER_RE.search(text)
    source = issue_m.group(1).strip() if issue_m else None

    entries: list[AppliedEntry] = []
    for m in blocks:
        product_handle = m.group(1).strip()
        if not product_handle:
            continue
        after = _dequote(m.group(3))
        if not after:
            continue
        before = _dequote(m.group(2)) or None

        entries.append(AppliedEntry(
            record_path=path,
            handles=[series_handle],
            field=field_name,
            surface=f"product.{product_handle}",
            before=before,
            after=after,
            source_cited=source,
            record_date=record_date,
        ))
    return entries


def _dequote(block: str) -> str:
    """Join a markdown blockquote's "> " lines into one plain-text value."""
    lines = [ln.rstrip() for ln in block.strip("\n").splitlines()]
    stripped = [re.sub(r"^>\s?", "", ln).strip() for ln in lines]
    return " ".join(p for p in stripped if p).strip()


def _normalise_metafield(raw: str) -> str:
    """`custom.subject_description` -> `subject_description`.

    Matches the field-name shape library.py and shopify.py already key on
    (_ENRICHMENT_FIELD_PROJECTIONS / _PRODUCT_METAFIELD_ALIASES): the bare
    metafield key for `custom.*` fields, unchanged for anything else (e.g.
    the native `seo.description`).
    """
    return raw[len("custom."):] if raw.startswith("custom.") else raw


def _extract_date(path: str) -> str | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path)
    if m:
        return m.group(1)
    return None
