"""Synthetic fixture tests for the diff engine.

All five spec fixtures (2026-05-26) tested here using synthetic PlaneData
objects — no file system or Shopify API access required.
"""

from __future__ import annotations

import pytest

from lc_facts_reconcile.diff import (
    Disagreement,
    OpenClaim,
    PlaneData,
    compute_disagreements,
)
from lc_facts_reconcile.planes.library import (
    LibraryReadResult,
    _extract_open_claims,
    _parse_at_a_glance,
)


def make_plane(**kwargs: str) -> PlaneData:
    """Build a PlaneData from (surface, field) = value kwargs formatted as 'surface__field'."""
    p = PlaneData()
    for k, v in kwargs.items():
        surface, _, field_name = k.partition("__")
        p.values[(surface, field_name)] = v
    return p


# ---------------------------------------------------------------------------
# Fixture 1: drift
# Library says X, applied record says Y, Shopify says Y → drift
# (live is correct, library is stale)
# ---------------------------------------------------------------------------

def test_fixture_1_drift():
    library = make_plane(**{"series.location__location": "VALUE-X"})
    applied = make_plane(**{"series.location__location": "VALUE-Y"})
    shopify = make_plane(**{"series.location__location": "VALUE-Y"})

    result = compute_disagreements(
        handle="test-series",
        series="Test Series",
        library=library,
        applied=applied,
        shopify=shopify,
    )

    assert len(result) == 1, f"Expected 1 disagreement, got {len(result)}: {result}"
    assert result[0].severity == "drift", f"Expected drift, got {result[0].severity}"
    assert result[0].library_says == "VALUE-X"
    assert result[0].shopify_says == "VALUE-Y"
    assert result[0].applied_says == "VALUE-Y"


# ---------------------------------------------------------------------------
# Fixture 2: R0-live
# Library says X, applied says X, Shopify says Z → R0-live
# (live production surface has a claim the library does not back)
# ---------------------------------------------------------------------------

def test_fixture_2_r0_live():
    library = make_plane(**{"series.metaobject__year_range": "1888-1987"})
    applied = make_plane(**{"series.metaobject__year_range": "1888-1987"})
    shopify = make_plane(**{"series.metaobject__year_range": "1888-1995"})

    result = compute_disagreements(
        handle="test-series",
        series="Test Series",
        library=library,
        applied=applied,
        shopify=shopify,
    )

    assert len(result) == 1, f"Expected 1 disagreement, got {len(result)}: {result}"
    assert result[0].severity == "R0-live", f"Expected R0-live, got {result[0].severity}"
    assert result[0].library_says == "1888-1987"
    assert result[0].shopify_says == "1888-1995"


# ---------------------------------------------------------------------------
# Fixture 3: caption-conflict
# Research file says "gasworks" confidently, caption says "possibly gasworks"
# → caption-conflict; caption wins per standing rule
# ---------------------------------------------------------------------------

def test_fixture_3_caption_conflict():
    library = make_plane(**{"research.at_a_glance__subject": "confirmed gasworks"})
    captions = make_plane(**{"research.at_a_glance__subject": "possibly gasworks"})

    result = compute_disagreements(
        handle="test-series",
        series="Test Series",
        library=library,
        applied=None,
        shopify=None,
        captions=captions,
    )

    assert len(result) == 1, f"Expected 1 disagreement, got {len(result)}: {result}"
    assert result[0].severity == "caption-conflict", f"Expected caption-conflict, got {result[0].severity}"
    assert "caption wins" in result[0].resolution_rule.lower()


# ---------------------------------------------------------------------------
# Fixture 4: internal disagreement
# master entry says one date, research file says another → internal disagreement
# (surfaced via internal_conflicts passed to compute_disagreements)
# ---------------------------------------------------------------------------

def test_fixture_4_internal_disagreement():
    internal_d = Disagreement(
        severity="internal",
        series="Test Series",
        handle="test-series",
        surface="library.internal",
        field="year_range",
        library_says="_master.md: opened 1890",
        applied_says=None,
        shopify_says=None,
        caption_says="research file: opened 1888",
        resolution_rule="Two library files disagree. Surface to Brett — no auto-resolution.",
        recommended_action="Brett to choose canonical version; update the non-canonical file.",
    )

    library = PlaneData()
    result = compute_disagreements(
        handle="test-series",
        series="Test Series",
        library=library,
        applied=None,
        shopify=None,
        captions=None,
        internal_conflicts=[internal_d],
    )

    assert len(result) == 1, f"Expected 1 internal disagreement, got {len(result)}"
    assert result[0].severity == "internal"
    assert result[0].field == "year_range"


# ---------------------------------------------------------------------------
# Fixture 5: open-claims register
# Research file has [FACT: verify] blocks → open-claims register lists all 5
# ---------------------------------------------------------------------------

FIXTURE_RESEARCH_TEXT = """\
## At a glance

| Field | Value |
|---|---|
| Location | Test Location |

## History

- First event 1900

[FACT: verify] founding date — no primary source confirmed
[FACT: verify] operator name — census record needed
[FACT: verify] demolition year — conflicting secondary sources
[FACT: verify] architect — not identified in any located source
[FACT: verify] capacity — figure appears only in one tertiary source
"""


def test_fixture_5_open_claims():
    claims = _extract_open_claims("test-handle", FIXTURE_RESEARCH_TEXT, "/fake/path.md")

    assert len(claims) == 5, f"Expected 5 open claims, got {len(claims)}: {[c.claim_text for c in claims]}"
    for claim in claims:
        assert "[FACT: verify]" in claim.claim_text or "claims to verify" in claim.claim_text.lower()
    texts = [c.claim_text for c in claims]
    assert any("founding date" in t for t in texts)
    assert any("operator name" in t for t in texts)
    assert any("demolition year" in t for t in texts)
    assert any("architect" in t for t in texts)
    assert any("capacity" in t for t in texts)


# ---------------------------------------------------------------------------
# Additional: clean case produces no disagreements
# ---------------------------------------------------------------------------

def test_clean_case_no_disagreements():
    library = make_plane(
        **{
            "series.metaobject__location": "Bathurst",
            "series.metaobject__year_range": "1888-1987",
        }
    )
    shopify = make_plane(
        **{
            "series.metaobject__location": "Bathurst",
            "series.metaobject__year_range": "1888-1987",
        }
    )

    result = compute_disagreements(
        handle="bathurst-gasworks",
        series="Bathurst Gasworks",
        library=library,
        applied=None,
        shopify=shopify,
    )

    assert result == [], f"Expected no disagreements, got: {result}"


# ---------------------------------------------------------------------------
# Edge: em-dash normalisation does not create false positives
# ---------------------------------------------------------------------------

def test_normalisation_em_dash():
    library = make_plane(**{"series.metaobject__year_range": "1888-1987"})
    shopify = make_plane(**{"series.metaobject__year_range": "1888\u20131987"})

    result = compute_disagreements(
        handle="test",
        series="Test",
        library=library,
        shopify=shopify,
    )

    assert result == [], f"Em-dash normalisation failed — got: {result}"


# ---------------------------------------------------------------------------
# Regression LOS7-1382: library citation tags / markdown must not create
# false-positive R0-live findings against Shopify's plain-text values.
# ---------------------------------------------------------------------------

def test_citation_tag_normalisation_no_false_positive():
    library = make_plane(
        **{
            "series.metaobject__location": (
                "Wangi Wangi, western shore of Lake Macquarie, City of Lake "
                "Macquarie, NSW 2267. Lat -33.0632, Long 151.5708. [S3]"
            )
        }
    )
    shopify = make_plane(
        **{
            "series.metaobject__location": (
                "Wangi Wangi, western shore of Lake Macquarie, City of Lake "
                "Macquarie, NSW 2267. Lat -33.0632, Long 151.5708."
            )
        }
    )

    result = compute_disagreements(
        handle="wangi-power-station",
        series="Wangi Power Station",
        library=library,
        shopify=shopify,
    )

    assert result == [], f"Citation-tag stripping failed — got: {result}"


def test_citation_tag_normalisation_multiple_tags_and_bold():
    library = make_plane(**{"series.metaobject__summary": "**Operated** 1888 to 1987[S1][S2]"})
    shopify = make_plane(**{"series.metaobject__summary": "Operated 1888 to 1987"})

    result = compute_disagreements(
        handle="test",
        series="Test",
        library=library,
        shopify=shopify,
    )

    assert result == [], f"Multi-tag/bold stripping failed — got: {result}"


def test_citation_tag_normalisation_still_catches_real_drift():
    library = make_plane(**{"series.metaobject__year_range": "1888-1987 [S3]"})
    shopify = make_plane(**{"series.metaobject__year_range": "1888-1995"})

    result = compute_disagreements(
        handle="test",
        series="Test",
        library=library,
        shopify=shopify,
    )

    assert len(result) == 1, f"Expected a real disagreement to still be caught, got: {result}"
    assert result[0].severity == "R0-live"
