"""Matcher-widening tests — Agent 5 iterate-2 (2026-05-31 SDK-plumbing sprint).

Two structural fixes covered:

1. Enrichment-draft read: the canonical 2026-05-06 schema is
       {"series": ..., "facts_library": ..., "drafts": [
         {"handle": "...", "proposed_subject_description": "...", ...}
       ]}
   The previous `_absorb_enrichment` iterated as if the file were
   `{handle: {field: value}}` and silently dropped every entry — the
   structural defect behind iterate-1's "132 products scanned / 0
   disagreements" outcome. The fix reads the `drafts` array and projects
   each entry's `proposed_*` fields onto `(product.<handle>, <key>)`
   so the matcher's structural compare against Shopify product
   metafields fires.

2. Series-to-metaobject projection: every library at-a-glance and
   _master entry fact is mirrored onto the `series.metaobject` surface
   so the matcher can compare it against Shopify metaobject fields
   without an LLM fan-out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lc_facts_reconcile.diff import PlaneData, compute_disagreements
from lc_facts_reconcile.planes.library import _absorb_enrichment, read_library


# ---------------------------------------------------------------------------
# _absorb_enrichment — canonical nested schema (drafts: [...])
# ---------------------------------------------------------------------------

def test_absorb_enrichment_reads_canonical_drafts_array():
    plane = PlaneData()
    data = {
        "series": "wangi-power-station",
        "facts_library": "R2 verified — Wangi Power Station, …",
        "drafts": [
            {
                "handle": "wangi-power-station-a-electrical-workshop",
                "lr_caption": "The electrical workshop remains surprisingly intact",
                "proposed_subject_description": "The A Station electrical workshop at Wangi Power Station.",
                "rule0_notes": "Test panel, parquetry flooring throughout building",
            },
            {
                "handle": "wangi-power-station-control-room",
                "proposed_subject_description": "The control room: 30 feet long, 17 feet high",
                "proposed_print_story": "Built in 1958 as Lake Macquarie B",
                "proposed_origin_line": "Wangi Wangi, NSW",
            },
        ],
    }

    _absorb_enrichment(plane, data, handle="wangi-power-station")

    assert plane.values[("product.wangi-power-station-a-electrical-workshop", "subject_description")] == (
        "The A Station electrical workshop at Wangi Power Station."
    )
    assert plane.values[("product.wangi-power-station-control-room", "subject_description")] == (
        "The control room: 30 feet long, 17 feet high"
    )
    assert plane.values[("product.wangi-power-station-control-room", "print_story")] == (
        "Built in 1958 as Lake Macquarie B"
    )
    assert plane.values[("product.wangi-power-station-control-room", "origin_line")] == "Wangi Wangi, NSW"


def test_absorb_enrichment_skips_drafts_without_handle():
    plane = PlaneData()
    data = {
        "series": "test",
        "drafts": [
            {"proposed_subject_description": "no handle, dropped"},
            {"handle": "", "proposed_subject_description": "empty handle, dropped"},
            {"handle": "valid", "proposed_subject_description": "kept"},
        ],
    }

    _absorb_enrichment(plane, data, handle="test")

    keys = list(plane.values.keys())
    assert ("product.valid", "subject_description") in keys
    assert len([k for k in keys if k[0].startswith("product.")]) == 1


def test_absorb_enrichment_back_compat_flat_dict_schema():
    """Legacy pre-2026-05 enrichment drafts used a flat
    `{product_handle: {field: value}}` shape. The reader still handles
    that so old drafts surface correctly."""
    plane = PlaneData()
    data = {
        "wangi-power-station-1": {
            "subject_description": "Legacy flat-shape entry",
            "print_story": "Legacy print story",
        },
        "wangi-power-station-2": {
            "subject_description": "Another legacy entry",
        },
    }

    _absorb_enrichment(plane, data, handle="wangi-power-station")

    assert plane.values[("product.wangi-power-station-1", "subject_description")] == "Legacy flat-shape entry"
    assert plane.values[("product.wangi-power-station-1", "print_story")] == "Legacy print story"
    assert plane.values[("product.wangi-power-station-2", "subject_description")] == "Another legacy entry"


# ---------------------------------------------------------------------------
# read_library — series-to-metaobject projection
# ---------------------------------------------------------------------------

def test_read_library_mirrors_at_a_glance_onto_metaobject_surface(tmp_path, monkeypatch):
    """Project every at-a-glance fact onto `series.metaobject` so the
    matcher can compare it against Shopify metaobject reads."""
    research_root = tmp_path / "facts-library" / "research" / "locations"
    research_root.mkdir(parents=True)
    research_file = research_root / "test-series.md"
    research_file.write_text(
        "# Test Series\n\n"
        "## At a glance\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Location | Test City [S1] |\n"
        "| Year range | 1888-1987 [S2] |\n"
        "| Operator | Test Operator [S3] |\n"
        "\n## History\n\nNotes here.\n",
        encoding="utf-8",
    )

    # Re-point the library module's paths at the temp tree.
    from lc_facts_reconcile.planes import library as lib_module
    monkeypatch.setattr(lib_module, "FACTS_ROOT", tmp_path / "facts-library")
    monkeypatch.setattr(lib_module, "RESEARCH_ROOT", research_root)
    monkeypatch.setattr(lib_module, "MASTER_FILE", tmp_path / "facts-library" / "series" / "_master.md")
    monkeypatch.setattr(lib_module, "ENRICHMENT_ROOT", tmp_path / "facts-library" / "enrichment-drafts")

    result = read_library("test-series")

    # at-a-glance keeps its own surface for upstream consumers
    assert ("research.at_a_glance", "location") in result.plane.values
    assert ("research.at_a_glance", "year_range") in result.plane.values

    # AND every at-a-glance fact is mirrored onto series.metaobject
    assert result.plane.values[("series.metaobject", "location")] == "Test City [S1]"
    assert result.plane.values[("series.metaobject", "year_range")] == "1888-1987 [S2]"
    assert result.plane.values[("series.metaobject", "operator")] == "Test Operator [S3]"


# ---------------------------------------------------------------------------
# End-to-end matcher behaviour — Task 2c subtask tests
# ---------------------------------------------------------------------------

def _plane(**kwargs: str) -> PlaneData:
    p = PlaneData()
    for k, v in kwargs.items():
        surface, _, field_name = k.partition("__")
        p.values[(surface, field_name)] = v
    return p


def test_known_drift_case_emits_drift_finding():
    """Mock Shopify response with a known drift case (R2: founding year
    1907, product metafield: 1908) → assert ≥1 drift finding emitted."""
    library = _plane(**{"series.metaobject__founding_year": "1907"})
    applied = _plane(**{"series.metaobject__founding_year": "1908"})
    shopify = _plane(**{"series.metaobject__founding_year": "1908"})

    result = compute_disagreements(
        handle="test-series",
        series="Test",
        library=library,
        applied=applied,
        shopify=shopify,
    )

    drift = [d for d in result if d.severity == "drift"]
    assert len(drift) >= 1
    assert drift[0].field == "founding_year"
    assert drift[0].library_says == "1907"
    assert drift[0].shopify_says == "1908"


def test_caption_wins_precedence_on_bathurst_gasworks_shape():
    """Caption-vs-R2 conflict for a series that has captions in the store:
    severity = caption-conflict, caption value wins per the 2026-05-19
    standing rule."""
    library = _plane(**{"research.at_a_glance__subject": "confirmed gasworks operation 1888-1987"})
    captions = _plane(**{"research.at_a_glance__subject": "possibly a gasworks — verify"})
    shopify = _plane(**{"series.metaobject__year_range": "1888-1987"})

    result = compute_disagreements(
        handle="bathurst-gasworks",
        series="Bathurst Gasworks",
        library=library,
        applied=None,
        shopify=shopify,
        captions=captions,
    )

    cap_conflicts = [d for d in result if d.severity == "caption-conflict"]
    assert len(cap_conflicts) == 1
    assert "caption wins" in cap_conflicts[0].resolution_rule.lower()


def test_no_finding_when_r2_matches_live_exactly():
    """Mock an R2 fact that matches the live metafield exactly → assert
    NO finding emitted (no false-positive)."""
    library = _plane(**{"series.metaobject__year_range": "1888-1987"})
    shopify = _plane(**{"series.metaobject__year_range": "1888-1987"})

    result = compute_disagreements(
        handle="bathurst-gasworks",
        series="Bathurst Gasworks",
        library=library,
        applied=None,
        shopify=shopify,
        captions=None,
    )

    assert result == [], f"Expected no findings on exact match, got: {result}"


def test_no_captions_does_not_block_other_severities():
    """A series with no captions doesn't exercise caption-conflict but
    other grades still produce."""
    library = _plane(**{"series.metaobject__location": "Place A"})
    shopify = _plane(**{"series.metaobject__location": "Place B"})

    result = compute_disagreements(
        handle="no-captions-series",
        series="No Captions",
        library=library,
        applied=None,
        shopify=shopify,
        captions=None,
    )

    assert len(result) == 1
    assert result[0].severity == "R0-live"
    # caption-conflict severity not exercised
    assert all(d.severity != "caption-conflict" for d in result)


def test_enrichment_projection_surfaces_drift_against_live_product_metafield():
    """End-to-end matcher fixture: an enrichment-draft's
    proposed_subject_description disagrees with the live Shopify product
    metafield — drift fires on (product.<handle>, subject_description).

    This is the load-bearing fixture: it proves that the previously-
    broken enrichment-draft read, once fixed, lets the structural diff
    surface per-product findings without any LLM fan-out."""
    # Build library plane via the real _absorb_enrichment path
    library = PlaneData()
    draft_data = {
        "series": "wangi-power-station",
        "drafts": [
            {
                "handle": "wangi-power-station-control-room",
                "proposed_subject_description": "Control room with original test panel and parquetry floor.",
            },
        ],
    }
    _absorb_enrichment(library, draft_data, handle="wangi-power-station")

    applied = _plane(
        **{
            "product.wangi-power-station-control-room__subject_description": (
                "An AI-generated description that the proposed text supersedes."
            )
        }
    )
    shopify = _plane(
        **{
            "product.wangi-power-station-control-room__subject_description": (
                "An AI-generated description that the proposed text supersedes."
            )
        }
    )

    result = compute_disagreements(
        handle="wangi-power-station-control-room",
        series="Wangi Power Station",
        library=library,
        applied=applied,
        shopify=shopify,
    )

    # Library != Shopify (drift); applied agrees with Shopify so severity = drift
    drift_findings = [d for d in result if d.severity == "drift"]
    assert len(drift_findings) == 1
    assert drift_findings[0].surface == "product.wangi-power-station-control-room"
    assert drift_findings[0].field == "subject_description"
