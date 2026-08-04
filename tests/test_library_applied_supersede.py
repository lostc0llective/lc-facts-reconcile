"""library.py enrichment-draft supersession tests (LOS7-1929).

An enrichment-draft is Layer 3 pre-audit staging — nothing re-generates it
once a later factual audit corrects and applies different text straight to
Shopify. read_library() must not project a draft's proposed_subject_description
into the library plane once an applied record already covers that exact
(product, field) surface, or the reconciler compares live against a claim
nobody is standing behind and reports it as unbacked live exposure.
"""

from __future__ import annotations

import json

import pytest

from lc_facts_reconcile.diff import PlaneData
from lc_facts_reconcile.planes import library as library_mod


def write_draft(root, handle: str, drafts: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {"series": handle, "facts_library": "R1 verified", "drafts": drafts}
    (root / f"{handle}-enrichment-draft.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def library_root(tmp_path, monkeypatch):
    facts_root = tmp_path / "facts-library"
    monkeypatch.setattr(library_mod, "FACTS_ROOT", facts_root)
    monkeypatch.setattr(library_mod, "RESEARCH_ROOT", facts_root / "research/locations")
    monkeypatch.setattr(library_mod, "MASTER_FILE", facts_root / "series/_master.md")
    enrichment_root = facts_root / "enrichment-drafts"
    monkeypatch.setattr(library_mod, "ENRICHMENT_ROOT", enrichment_root)
    return enrichment_root


class TestSupersession:
    def test_a_field_covered_by_an_applied_record_is_not_absorbed_from_the_draft(self, library_root):
        write_draft(library_root, "ashio-copper-mine", [{
            "handle": "ashio-copper-mine-crusher",
            "proposed_subject_description": "The cone crusher took the first pass — STALE, 2026-05-09 draft.",
        }])
        applied_plane = PlaneData()
        applied_plane.values[("product.ashio-copper-mine-crusher", "subject_description")] = (
            "The crusher took the first pass — CURRENT, applied 2026-07-31."
        )

        result = library_mod.read_library("ashio-copper-mine", applied_plane=applied_plane)

        assert ("product.ashio-copper-mine-crusher", "subject_description") not in result.plane.values

    def test_a_field_with_no_applied_record_is_still_absorbed_as_before(self, library_root):
        write_draft(library_root, "ashio-copper-mine", [{
            "handle": "ashio-copper-mine-catwalk",
            "proposed_subject_description": "The catwalk runs from raw material toward crushing.",
        }])
        applied_plane = PlaneData()
        applied_plane.values[("product.ashio-copper-mine-crusher", "subject_description")] = "unrelated product"

        result = library_mod.read_library("ashio-copper-mine", applied_plane=applied_plane)

        assert result.plane.values[("product.ashio-copper-mine-catwalk", "subject_description")] == (
            "The catwalk runs from raw material toward crushing."
        )

    def test_no_applied_plane_at_all_behaves_exactly_as_before(self, library_root):
        """applied_plane defaults to None (e.g. a --planes run excluding
        'applied') — must not suppress anything, matching pre-LOS7-1929
        behaviour exactly."""
        write_draft(library_root, "ashio-copper-mine", [{
            "handle": "ashio-copper-mine-crusher",
            "proposed_subject_description": "The cone crusher took the first pass.",
        }])

        result = library_mod.read_library("ashio-copper-mine")

        assert result.plane.values[("product.ashio-copper-mine-crusher", "subject_description")] == (
            "The cone crusher took the first pass."
        )

    def test_suppression_is_per_field_not_per_product(self, library_root):
        """An applied record covering subject_description must not suppress
        a different field (e.g. print_story) the draft also proposes for
        the same product."""
        write_draft(library_root, "ashio-copper-mine", [{
            "handle": "ashio-copper-mine-crusher",
            "proposed_subject_description": "STALE subject description.",
            "proposed_print_story": "Print story draft, untouched by the audit.",
        }])
        applied_plane = PlaneData()
        applied_plane.values[("product.ashio-copper-mine-crusher", "subject_description")] = "CURRENT live text."

        result = library_mod.read_library("ashio-copper-mine", applied_plane=applied_plane)

        assert ("product.ashio-copper-mine-crusher", "subject_description") not in result.plane.values
        assert result.plane.values[("product.ashio-copper-mine-crusher", "print_story")] == (
            "Print story draft, untouched by the audit."
        )
