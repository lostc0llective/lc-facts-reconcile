"""Captions plane + grade-precedence regression tests (LOS7-1587).

Across all 31 reconciliation reports ever written (3,762 graded rows), every row
was R0-live and both the applied and captions columns were `(none)` on every
one — so caption-conflict, drift and R0-pending were mechanically unreachable
while each report header advertised four planes.

Two stacked bugs caused the captions half:
  1. the parser iterated the TOP level of the export, manufacturing values out
     of file metadata (series_handle, generated_at) and missing the real
     captions nested under "captions";
  2. it keyed them ("captions.iptc", stem), a namespace that can never match the
     ("product.<handle>", "subject_description") tuples diff.py correlates on.
"""

from __future__ import annotations

import json

import pytest

from lc_facts_reconcile.diff import PlaneData, compute_disagreements
from lc_facts_reconcile.planes import captions as captions_mod


def write_export(tmp_path, handle: str, entries: dict) -> None:
    payload = {
        "series_handle": handle,
        "collection_name": handle.replace("-", " ").title(),
        "generated_at": "2026-07-15T19:27:27+10:00",
        "source": "Lightroom plugin export.",
        "exported_by": "LostCollective.lrplugin/ExportCaptions v1",
        "count": len(entries),
        "skipped": 0,
        "captions": entries,
    }
    (tmp_path / f"{handle}.captions.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def caps_root(tmp_path, monkeypatch):
    monkeypatch.setattr(captions_mod, "CAPTIONS_ROOT", tmp_path)
    return tmp_path


class TestCaptionParsing:
    def test_envelope_metadata_is_not_treated_as_captions(self, caps_root):
        """series_handle / generated_at / source must never become caption values."""
        write_export(caps_root, "wangi-power-station", {
            "a-electrical-workshop": {"iptc_caption": "Heavily corroded gauges."},
        })
        res = captions_mod.read_captions("wangi-power-station")
        assert res is not None
        values = res.plane.values
        assert res.caption_count == 1
        joined = " ".join(str(v) for v in values.values())
        assert "2026-07-15" not in joined
        assert "Lightroom plugin export." not in joined
        assert not any(f in ("series_handle", "generated_at", "source") for _, f in values)

    def test_captions_key_on_the_product_surface_diff_correlates_on(self, caps_root):
        write_export(caps_root, "wangi-power-station", {
            "a-electrical-workshop": {"iptc_caption": "Heavily corroded gauges."},
        })
        res = captions_mod.read_captions("wangi-power-station")
        assert ("product.wangi-power-station-a-electrical-workshop", "subject_description") in res.plane.values

    def test_key_already_carrying_the_series_prefix_is_not_doubled(self, caps_root):
        write_export(caps_root, "wangi-power-station", {
            "wangi-power-station-a-electrical-workshop": {"iptc_caption": "x"},
        })
        res = captions_mod.read_captions("wangi-power-station")
        assert ("product.wangi-power-station-a-electrical-workshop", "subject_description") in res.plane.values

    def test_falls_back_through_caption_field_names(self, caps_root):
        write_export(caps_root, "s", {
            "a": {"xmp_description": "from xmp"},
            "b": {"caption": "from caption"},
        })
        res = captions_mod.read_captions("s")
        assert res.caption_count == 2

    def test_missing_file_returns_none(self, caps_root):
        assert captions_mod.read_captions("does-not-exist") is None


class TestGradePrecedence:
    """Live exposure must never be demoted by a caption conflict."""

    def _planes(self):
        key = ("product.x-y", "subject_description")
        library = PlaneData(); library.values[key] = "LIBRARY TEXT"
        shopify = PlaneData(); shopify.values[key] = "DIFFERENT LIVE TEXT"
        caption = PlaneData(); caption.values[key] = "DIFFERENT CAPTION TEXT"
        return library, shopify, caption

    def test_r0_live_survives_a_simultaneous_caption_conflict(self):
        """The regression that mattered: repairing captions naively would have
        demoted 102 of 162 live R0-live rows to caption-conflict, reading as a
        large improvement while hiding live Rule-0 exposure."""
        library, shopify, caption = self._planes()
        ds = compute_disagreements(handle="x", series="X", library=library,
                                   shopify=shopify, captions=caption)
        sev = [d.severity for d in ds]
        assert "R0-live" in sev, "live exposure was masked by the caption conflict"

    def test_both_findings_are_emitted_not_one(self):
        library, shopify, caption = self._planes()
        ds = compute_disagreements(handle="x", series="X", library=library,
                                   shopify=shopify, captions=caption)
        assert sorted(d.severity for d in ds) == ["R0-live", "caption-conflict"]

    def test_caption_conflict_alone_when_live_agrees(self):
        key = ("product.x-y", "subject_description")
        library = PlaneData(); library.values[key] = "SAME TEXT"
        shopify = PlaneData(); shopify.values[key] = "SAME TEXT"
        caption = PlaneData(); caption.values[key] = "DIFFERENT CAPTION"
        ds = compute_disagreements(handle="x", series="X", library=library,
                                   shopify=shopify, captions=caption)
        assert [d.severity for d in ds] == ["caption-conflict"]

    def test_agreeing_caption_produces_nothing(self):
        key = ("product.x-y", "subject_description")
        library = PlaneData(); library.values[key] = "SAME TEXT"
        caption = PlaneData(); caption.values[key] = "same text"  # normalised match
        ds = compute_disagreements(handle="x", series="X", library=library, captions=caption)
        assert ds == []
