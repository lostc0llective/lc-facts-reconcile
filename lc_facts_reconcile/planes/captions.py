"""Plane 4 — IPTC captions store (Tier 1, direct artist confirmation).

Path: ~/Claude/cowork/brand-voice/facts-library/exif-snapshots/captions/{handle}.captions.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..diff import PlaneData

logger = logging.getLogger(__name__)

CAPTIONS_ROOT = Path.home() / "Claude/cowork/brand-voice/facts-library/exif-snapshots/captions"


@dataclass
class CaptionReadResult:
    handle: str
    plane: PlaneData
    caption_count: int


def read_captions(handle: str) -> CaptionReadResult | None:
    """Return captions plane data for a handle, or None if no captions file exists."""
    logger.debug("read_captions(handle=%s) starting", handle)
    captions_file = CAPTIONS_ROOT / f"{handle}.captions.json"
    if not captions_file.exists():
        logger.debug("read_captions(handle=%s) no captions file at %s", handle, captions_file)
        return None

    try:
        raw = json.loads(captions_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("read_captions(handle=%s) parse error: %s", handle, exc)
        return None

    plane = PlaneData()

    # The export is {series_handle, collection_name, generated_at, source,
    # exported_by, count, skipped, captions:{...}} — the payload lives under
    # "captions". The original code iterated the TOP level, so it manufactured
    # junk values out of the file metadata (("captions.iptc","series_handle") ->
    # "hotel-motel-101") and missed every real caption, because the metadata keys
    # carry no "caption"/"description"/"abstract" sub-key (LOS7-1587).
    entries = raw.get("captions") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        # Tolerate a bare {key: entry} export with no envelope, but never fall
        # back to treating envelope metadata as captions.
        entries = raw if isinstance(raw, dict) and "captions" not in raw else {}
        entries = {k: v for k, v in entries.items() if not isinstance(v, (str, int))} or {}

    for image_key, entry in entries.items():
        caption_text = None
        if isinstance(entry, str):
            caption_text = entry
        elif isinstance(entry, dict):
            caption_text = (
                entry.get("iptc_caption")
                or entry.get("xmp_description")
                or entry.get("caption")
                or entry.get("description")
                or entry.get("abstract")
            )

        if caption_text and isinstance(caption_text, str):
            # Key on the SAME (surface, field) tuple the library and Shopify
            # planes use, or the diff can never correlate it. diff.py matches by
            # exact tuple, so the old ("captions.iptc", stem) namespace could
            # never line up with ("product.<handle>", "subject_description") —
            # caption-conflict was unreachable even when captions parsed.
            #
            # Caption keys are product-slug suffixes without the series prefix
            # ("a-electrical-workshop" -> "wangi-power-station-a-electrical-workshop").
            stem = Path(image_key).stem
            product = stem if stem.startswith(f"{handle}-") else f"{handle}-{stem}"
            plane.values[(f"product.{product}", "subject_description")] = caption_text.strip()

    logger.debug("read_captions(handle=%s) finished — %d captions", handle, len(plane.values))
    return CaptionReadResult(
        handle=handle,
        plane=plane,
        caption_count=len(plane.values),
    )
