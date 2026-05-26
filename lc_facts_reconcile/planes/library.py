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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..diff import Disagreement, OpenClaim, PlaneData

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


def read_library(handle: str) -> LibraryReadResult:
    """Read all library planes for a series handle."""
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

        open_claims.extend(_extract_open_claims(handle, text, str(research_file)))

    master_facts = _parse_master_entry(handle)
    for key, val in master_facts.items():
        surface = "series.master"
        plane.values[(surface, key)] = val

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
            _absorb_enrichment(plane, data, handle)
        except (json.JSONDecodeError, OSError):
            pass

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

    pattern = re.compile(
        r"(?i)(?:^|\n).*?" + re.escape(handle) + r".*?(?=\n(?:##|\d+\.|---)|$)",
        re.DOTALL,
    )
    m = pattern.search(text[:20000])
    if not m:
        return facts

    block = m.group(0)

    year_m = re.search(r"\b(1[89]\d{2})\s*[-\u2013\u2014]\s*(1[89]\d{2}|present|ongoing)", block, re.IGNORECASE)
    if year_m:
        facts["year_range"] = year_m.group(0)

    loc_m = re.search(r"(?i)location[:\s]+([^\n|]{5,80})", block)
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


def _absorb_enrichment(plane: PlaneData, data: Any, handle: str) -> None:
    """Pull structured fields from enrichment draft JSON into the library plane."""
    if not isinstance(data, dict):
        return
    for product_handle, product_data in data.items():
        if not isinstance(product_data, dict):
            continue
        for field_name in ("subject_description", "print_story", "origin_line"):
            val = product_data.get(field_name)
            if val and isinstance(val, str):
                surface = f"enrichment.{field_name}"
                plane.values[(surface, product_handle)] = val


def list_research_handles() -> list[str]:
    """Return all handles that have a research file in locations/."""
    if not RESEARCH_ROOT.exists():
        return []
    return [
        p.stem
        for p in RESEARCH_ROOT.glob("*.md")
        if not p.stem.startswith("_")
    ]
