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

    if isinstance(raw, dict):
        for image_key, entry in raw.items():
            caption_text = None
            if isinstance(entry, str):
                caption_text = entry
            elif isinstance(entry, dict):
                caption_text = entry.get("caption") or entry.get("description") or entry.get("abstract")

            if caption_text and isinstance(caption_text, str):
                stem = Path(image_key).stem
                plane.values[("captions.iptc", stem)] = caption_text.strip()

    logger.debug("read_captions(handle=%s) finished — %d captions", handle, len(plane.values))
    return CaptionReadResult(
        handle=handle,
        plane=plane,
        caption_count=len(plane.values),
    )
