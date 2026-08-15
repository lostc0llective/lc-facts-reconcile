"""Plane 1 — reads the LC facts library files.

Sources:
  _master.md             — per-series Approved metaobject summary blocks
  research/locations/    — per-location Layer 1 R2/R3 files
  enrichment-drafts/     — per-product subject_description drafts (JSON)
  exif-snapshots/captions/ — IPTC captions (Tier 1) — read by captions.py
  source-backgrounds/    — source archive index files
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..diff import Disagreement, OpenClaim, PlaneData

logger = logging.getLogger(__name__)

FACTS_ROOT = Path.home() / "Claude/cowork/brand-voice/facts-library"
RESEARCH_ROOT = FACTS_ROOT / "research/locations"
MASTER_FILE = FACTS_ROOT / "series/_master.md"
ENRICHMENT_ROOT = FACTS_ROOT / "enrichment-drafts"
SOURCE_BG_ROOT = FACTS_ROOT / "source-backgrounds"


@dataclass
class LibraryReadResult:
    handle: str
    plane: PlaneData
    open_claims: list[OpenClaim]
    internal_conflicts: list[Disagreement]
    research_file_exists: bool


def read_library(handle: str, applied_plane: PlaneData | None = None) -> LibraryReadResult:
    """Read all library planes for a series handle.

    applied_plane, when given, is that same series' PlaneData from
    planes.applied.read_applied() — passed in so enrichment-draft absorption
    can check it (see _absorb_enrichment's supersession note, LOS7-1929).
    """
    logger.debug("read_library(handle=%s) starting", handle)
    plane = PlaneData()
    open_claims: list[OpenClaim] = []
    internal_conflicts: list[Disagreement] = []

    research_file = RESEARCH_ROOT / f"{handle}.md"
    research_facts: dict[str, str] = {}
    research_exists = research_file.exists()

    if research_exists:
        text = research_file.read_text(encoding="utf-8", errors="replace")
        research_facts = _parse_at_a_glance(text)
        for key, val in research_facts.items():
            surface = "research.at_a_glance"
            plane.values[(surface, key)] = val

        # Series-to-metaobject projection (iterate-2, 2026-05-31).
        # The Shopify plane reads the series metaobject and emits
        # entries on the `series.metaobject` surface. The library
        # mirrors every at-a-glance fact onto the same surface so
        # the diff matcher can compare them structurally without
        # an LLM fan-out. When the metaobject has no entry for a
        # given key, _classify yields no finding; when both planes
        # have an entry, R0-live / drift / R0-pending fires per
        # the standing severity grade rules in diff.py.
        for key, val in research_facts.items():
            plane.values[("series.metaobject", key)] = val

        open_claims.extend(_extract_open_claims(handle, text, str(research_file)))

    master_facts = _parse_master_entry(handle)
    for key, val in master_facts.items():
        surface = "series.master"
        plane.values[(surface, key)] = val
        # Same projection rationale as above — _master entries also
        # mirror onto series.metaobject so the matcher can see them.
        if ("series.metaobject", key) not in plane.values:
            plane.values[("series.metaobject", key)] = val

    for key, lib_val in master_facts.items():
        if key in research_facts:
            res_val = research_facts[key]
            from ..diff import _values_agree, _RESOLUTION_RULES, _RECOMMENDED_ACTIONS
            if not _values_agree(lib_val, res_val):
                internal_conflicts.append(Disagreement(
                    severity="internal",
                    series=handle,
                    handle=handle,
                    surface="library.internal",
                    field=key,
                    library_says=f"_master.md: {lib_val}",
                    applied_says=None,
                    shopify_says=None,
                    caption_says=f"research file: {res_val}",
                    resolution_rule=_RESOLUTION_RULES["internal"],
                    recommended_action=_RECOMMENDED_ACTIONS["internal"],
                ))

    enrichment_file = ENRICHMENT_ROOT / f"{handle}-enrichment-draft.json"
    if enrichment_file.exists():
        try:
            data = json.loads(enrichment_file.read_text(encoding="utf-8"))
            _absorb_enrichment(plane, data, handle, applied_plane)
        except (json.JSONDecodeError, OSError):
            pass

    logger.debug("read_library(handle=%s) finished — %d values / %d open claims / %d internal conflicts", handle, len(plane.values), len(open_claims), len(internal_conflicts))
    return LibraryReadResult(
        handle=handle,
        plane=plane,
        open_claims=open_claims,
        internal_conflicts=internal_conflicts,
        research_file_exists=research_exists,
    )


def _parse_at_a_glance(text: str) -> dict[str, str]:
    """Extract the key-value table under '## At a glance'."""
    facts: dict[str, str] = {}
    in_table = False
    for line in text.splitlines():
        if re.match(r"^##\s+At a glance", line, re.IGNORECASE):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) >= 2 and parts[0] and not parts[0].startswith("---"):
                key = parts[0].rstrip(":")
                val = parts[1]
                if val and key.lower() not in ("field", "value"):
                    facts[key.lower().replace(" ", "_").replace("/", "_")] = val
    return facts


def _parse_master_entry(handle: str) -> dict[str, str]:
    """Find the handle's entry in _master.md and extract key facts.

    The master is a narrative document. We look for the handle string and
    extract any structured fields near it: location, year_range, summary, story.
    This is a best-effort extraction — gaps are expected and do not flag errors.
    """
    if not MASTER_FILE.exists():
        return {}

    text = MASTER_FILE.read_text(encoding="utf-8", errors="replace")
    facts: dict[str, str] = {}

    # Require handle to appear backtick-wrapped (table cell) so update-log
    # mentions like "entry X corrected from Y" in the preamble don't match.
    pattern = re.compile(
        r"(?m)^\|[^\n]*`" + re.escape(handle) + r"`[^\n]*(?:\n(?!\|[^\n]*\|[^\n]*\|).*)*",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return facts

    block = m.group(0)

    year_m = re.search(r"\b(1[89]\d{2})\s*[-\u2013\u2014]\s*(1[89]\d{2}|present|ongoing)", block, re.IGNORECASE)
    if year_m:
        facts["year_range"] = year_m.group(0)

    # Only extract location from a pipe-delimited table row to avoid
    # matching "location" in prose (e.g. "taken on the drive to a location").
    loc_m = re.search(r"(?im)^\|\s*\*?\*?location\*?\*?\s*\|\s*([^|\n]{5,80})", block)
    if loc_m:
        facts["location"] = loc_m.group(1).strip()

    return facts


def _extract_open_claims(handle: str, text: str, source_file: str) -> list[OpenClaim]:
    claims: list[OpenClaim] = []
    for line in text.splitlines():
        if "[FACT: verify]" in line or "Claims to verify" in line.lower():
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                claims.append(OpenClaim(
                    handle=handle,
                    surface="research.open_claim",
                    claim_text=cleaned,
                    source_file=source_file,
                ))
    return claims


_ENRICHMENT_FIELD_PROJECTIONS = {
    # enrichment-draft field name -> Shopify product metafield key
    "proposed_subject_description": "subject_description",
    "proposed_print_story": "print_story",
    "proposed_origin_line": "origin_line",
    # legacy flat-shape names kept for back-compat if older drafts surface
    "subject_description": "subject_description",
    "print_story": "print_story",
    "origin_line": "origin_line",
}


def _absorb_enrichment(
    plane: PlaneData,
    data: Any,
    handle: str,
    applied_plane: PlaneData | None = None,
) -> None:
    """Pull structured fields from enrichment-draft JSON into the library plane.

    Enrichment-draft schema (canonical 2026-05-06 IPTC ingestion onwards):

        {
          "series": "<series-handle>",
          "facts_library": "R2 verified — ...",
          "drafts": [
            {
              "handle": "<product-handle>",
              "lr_caption": "...",            # Lightroom IPTC (canonical lives in captions/)
              "proposed_subject_description": "...",  # draft for Shopify product.subject_description
              "rule0_notes": "...",
              "alt_text": "...",              # optional
              "meta_title": "..."             # optional, seo.title equivalent
            },
            ...
          ]
        }

    The previous flat-dict reader (`{handle: {field: value}}`) silently
    dropped every entry because the real shape has `drafts: [...]` at
    the top level. This was the structural defect behind Agent 5
    iterate-1's "0 disagreements" outcome on 132 products scanned.

    Output projection: each draft entry's `proposed_*` field is
    re-keyed to match the Shopify product metafield surface shape —
    `(product.<handle>, <metafield_key>)` — so the diff matcher's
    structural compare fires when the draft and the live metafield
    disagree.

    SUPERSESSION (LOS7-1929): an enrichment-draft is Layer 3 pre-audit
    staging — nothing re-generates it once a later, more authoritative
    factual audit (e.g. LOS7-1864/1870) corrects and applies different text
    straight to Shopify. When applied_plane already carries a value for the
    exact (product.<handle>, dst_key) surface this draft would otherwise
    project, the draft's claim is stale by construction and is skipped
    rather than absorbed. Confirmed live: ashio-copper-mine-crusher's
    enrichment draft (2026-05-09) still held the pre-audit "cone crusher"
    wording three months after LOS7-1870 (2026-07-31) applied a corrected
    "crusher" wording to Shopify — comparing the stale draft against live
    read as an unbacked live claim (R0-live) when live was in fact correct
    and the draft was the only thing out of date.
    """
    if not isinstance(data, dict):
        return

    drafts = data.get("drafts")

    if isinstance(drafts, list):
        for entry in drafts:
            if not isinstance(entry, dict):
                continue
            product_handle = entry.get("handle")
            if not product_handle or not isinstance(product_handle, str):
                continue
            for src_key, dst_key in _ENRICHMENT_FIELD_PROJECTIONS.items():
                val = entry.get(src_key)
                if val and isinstance(val, str) and not _superseded(applied_plane, product_handle, dst_key):
                    plane.values[(f"product.{product_handle}", dst_key)] = val
        return

    # Back-compat: pre-2026-05 enrichment drafts used a flat
    # `{product_handle: {field: value}}` shape. Read those too so any
    # legacy drafts still surface; the field-name projection rules
    # above apply identically.
    for product_handle, product_data in data.items():
        if not isinstance(product_data, dict):
            continue
        if not isinstance(product_handle, str):
            continue
        for src_key, dst_key in _ENRICHMENT_FIELD_PROJECTIONS.items():
            val = product_data.get(src_key)
            if val and isinstance(val, str) and not _superseded(applied_plane, product_handle, dst_key):
                plane.values[(f"product.{product_handle}", dst_key)] = val


def _superseded(applied_plane: PlaneData | None, product_handle: str, dst_key: str) -> bool:
    """True when a later applied pass has made this draft field stale.

    Keyed on the FIELD across the whole series, not on this one product.

    LOS7-2097. The original LOS7-1929 rule asked "does an applied record cover
    this exact (product, field)?" — which reads the ABSENCE of a record as "the
    draft is still authoritative". It does not mean that. A factual audit
    covers a SERIES and adjudicates every product in it: the ones it found
    defective get an applied record, and the ones it left alone were examined
    and found correct. Both outcomes date the pre-audit draft.

    Reading absence as authority left 87 of the 90 R0-live rows standing in the
    2026-08-04 report — live copy nobody disputes, measured against May
    enrichment drafts that were never promoted. 53 were elrington-colliery
    alone, where the LOS7-1870 apply rewrote 8 products and examined the rest.
    Same absence-is-not-a-negative class as LOS7-2078.

    Still per FIELD: an audit that rewrote subject_description says nothing
    about a print_story draft, so widening stops at the field boundary. And an
    applied_plane of None (a --planes run excluding 'applied') still suppresses
    nothing, exactly as before.
    """
    if applied_plane is None:
        return False
    if (f"product.{product_handle}", dst_key) in applied_plane.values:
        return True
    return any(
        surface.startswith("product.") and key == dst_key
        for surface, key in applied_plane.values
    )


def list_research_handles() -> list[str]:
    """Return all handles that have a research file in locations/."""
    if not RESEARCH_ROOT.exists():
        return []
    return [
        p.stem
        for p in RESEARCH_ROOT.glob("*.md")
        if not p.stem.startswith("_")
    ]
