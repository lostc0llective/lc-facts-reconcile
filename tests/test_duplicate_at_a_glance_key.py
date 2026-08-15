"""A duplicated At-a-glance key must not discard a sourced row (LOS7-2098).

ashio-copper-mine's research file carries TWO tables under one `## At a glance`
heading: the first describes the Tsudō dressing plant Brett actually
photographed, the second the wider Ashio mine. Both carry a `| Location |` row
and both carry a `| Heritage status |` row, each sourced to a different cite.

`_parse_at_a_glance` built a plain dict, so the second row silently overwrote
the first. The library plane then held only the [S3] variant, and the live
metaobject — which matches the [S1] row verbatim — was graded R0-live for
carrying a claim the library does in fact back, on the row the parser threw
away.

Fixture values below are the REAL rows from
facts-library/research/locations/ashio-copper-mine.md and the REAL live
`series.metaobject` location value, both read 2026-08-15.
"""

from __future__ import annotations

import pytest

from lc_facts_reconcile.diff import PlaneData, compute_disagreements
from lc_facts_reconcile.planes.library import _parse_at_a_glance, read_library

# --- real values, ashio-copper-mine, 2026-08-15 ----------------------------

ASHIO_LOCATION_S1 = (
    "Tsudō (通洞), Ashio Town (足尾町), now part of Nikkō City, "
    "Tochigi Prefecture, Japan [S1]"
)
ASHIO_LOCATION_S3 = (
    "Ashio, Tochigi Prefecture (now part of Nikkō, Tochigi), "
    "northern Kantō region, Japan [S3]"
)
# What the live Shopify series metaobject actually carries — the [S1] row,
# minus the citation tag (Shopify plain text never carries library cites).
ASHIO_LIVE_LOCATION = (
    "Tsudō (通洞), Ashio Town (足尾町), now part of Nikkō City, "
    "Tochigi Prefecture, Japan"
)

ASHIO_HERITAGE_S12 = (
    "**Recognised** under the METI 2007 \"33 Modern Industrial Heritage "
    "Groups\" designation as item 02 of 22 in Story 12 [S12]"
)
ASHIO_HERITAGE_S1 = "National Historic Site of Japan, designated 28 March 2008 [S1]"

ASHIO_TWO_TABLE_MARKDOWN = f"""# Ashio Copper Mine

## At a glance

| Field | Value |
|---|---|
| Location | {ASHIO_LOCATION_S1} |
| Operator | Furukawa Mining Co. [S1][S3] |
| Heritage status | {ASHIO_HERITAGE_S12} |

---

| Field | Value |
|---|---|
| Full name | Ashio Copper Mine / 足尾銅山 (Ashio Dōzan) [S3] |
| Location | {ASHIO_LOCATION_S3} |
| Heritage status | {ASHIO_HERITAGE_S1} |

---

## History

Notes here.
"""


def _write_library(tmp_path, monkeypatch, handle: str, markdown: str):
    """Point the library module at a temp facts tree holding one research file."""
    research_root = tmp_path / "facts-library" / "research" / "locations"
    research_root.mkdir(parents=True, exist_ok=True)
    (research_root / f"{handle}.md").write_text(markdown, encoding="utf-8")

    from lc_facts_reconcile.planes import library as lib_module

    monkeypatch.setattr(lib_module, "FACTS_ROOT", tmp_path / "facts-library")
    monkeypatch.setattr(lib_module, "RESEARCH_ROOT", research_root)
    monkeypatch.setattr(lib_module, "MASTER_FILE", tmp_path / "facts-library" / "series" / "_master.md")
    monkeypatch.setattr(lib_module, "ENRICHMENT_ROOT", tmp_path / "facts-library" / "enrichment-drafts")
    return read_library(handle)


def _r0_live_locations(findings):
    return [f for f in findings if f.severity == "R0-live" and f.field == "location"]


# ---------------------------------------------------------------------------
# Parser: both sourced rows survive
# ---------------------------------------------------------------------------


class TestParserKeepsEveryRow:
    def test_duplicated_key_keeps_both_candidate_values_in_document_order(self):
        facts = _parse_at_a_glance(ASHIO_TWO_TABLE_MARKDOWN)

        assert facts["location"] == [ASHIO_LOCATION_S1, ASHIO_LOCATION_S3]

    def test_second_duplicated_key_also_keeps_both(self):
        facts = _parse_at_a_glance(ASHIO_TWO_TABLE_MARKDOWN)

        assert facts["heritage_status"] == [ASHIO_HERITAGE_S12, ASHIO_HERITAGE_S1]

    def test_single_row_key_is_still_a_one_item_list(self):
        facts = _parse_at_a_glance(ASHIO_TWO_TABLE_MARKDOWN)

        assert facts["operator"] == ["Furukawa Mining Co. [S1][S3]"]


# ---------------------------------------------------------------------------
# Plane: every candidate is reachable, and the primary is the first row
# ---------------------------------------------------------------------------


class TestPlaneCarriesCandidates:
    def test_plane_exposes_every_candidate_for_a_duplicated_key(self, tmp_path, monkeypatch):
        result = _write_library(tmp_path, monkeypatch, "ashio-copper-mine", ASHIO_TWO_TABLE_MARKDOWN)

        assert result.plane.candidates("series.metaobject", "location") == [
            ASHIO_LOCATION_S1,
            ASHIO_LOCATION_S3,
        ]

    def test_primary_value_is_the_first_row_not_the_last(self, tmp_path, monkeypatch):
        """Document order. The old dict overwrite silently made this the [S3] row."""
        result = _write_library(tmp_path, monkeypatch, "ashio-copper-mine", ASHIO_TWO_TABLE_MARKDOWN)

        assert result.plane.get("series.metaobject", "location") == ASHIO_LOCATION_S1

    def test_candidates_of_an_unduplicated_key_is_its_single_value(self, tmp_path, monkeypatch):
        result = _write_library(tmp_path, monkeypatch, "ashio-copper-mine", ASHIO_TWO_TABLE_MARKDOWN)

        assert result.plane.candidates("series.metaobject", "operator") == [
            "Furukawa Mining Co. [S1][S3]"
        ]

    def test_candidates_of_an_absent_key_is_empty(self, tmp_path, monkeypatch):
        result = _write_library(tmp_path, monkeypatch, "ashio-copper-mine", ASHIO_TWO_TABLE_MARKDOWN)

        assert result.plane.candidates("series.metaobject", "nonexistent") == []


# ---------------------------------------------------------------------------
# The finding itself: live matching ANY candidate is backed
# ---------------------------------------------------------------------------


class TestLiveMatchingAnyCandidateIsNotExposure:
    def _findings(self, tmp_path, monkeypatch, live_location: str):
        result = _write_library(tmp_path, monkeypatch, "ashio-copper-mine", ASHIO_TWO_TABLE_MARKDOWN)
        shopify = PlaneData()
        shopify.values[("series.metaobject", "location")] = live_location
        return compute_disagreements(
            handle="ashio-copper-mine",
            series="Ashio Copper Mine",
            library=result.plane,
            shopify=shopify,
        )

    def test_live_matching_the_discarded_first_row_is_not_r0_live(self, tmp_path, monkeypatch):
        """The real regression: live matches [S1], which the parser threw away."""
        findings = self._findings(tmp_path, monkeypatch, ASHIO_LIVE_LOCATION)

        assert _r0_live_locations(findings) == []

    def test_live_matching_the_second_row_is_also_not_r0_live(self, tmp_path, monkeypatch):
        findings = self._findings(
            tmp_path,
            monkeypatch,
            "Ashio, Tochigi Prefecture (now part of Nikkō, Tochigi), northern Kantō region, Japan",
        )

        assert _r0_live_locations(findings) == []

    def test_live_matching_no_candidate_is_still_r0_live(self, tmp_path, monkeypatch):
        """The guard must not be blinded. A claim outside EVERY candidate still fires."""
        findings = self._findings(
            tmp_path, monkeypatch, "Osaka Prefecture, Kansai region, Japan"
        )

        r0 = _r0_live_locations(findings)
        assert len(r0) == 1
        assert r0[0].shopify_says == "Osaka Prefecture, Kansai region, Japan"

    def test_r0_live_finding_reports_every_candidate_the_library_holds(self, tmp_path, monkeypatch):
        """A human adjudicating the flag must see both rows, not just one."""
        findings = self._findings(
            tmp_path, monkeypatch, "Osaka Prefecture, Kansai region, Japan"
        )

        says = _r0_live_locations(findings)[0].library_says
        assert ASHIO_LOCATION_S1 in says
        assert ASHIO_LOCATION_S3 in says

    def test_heritage_status_duplicate_behaves_the_same_way(self, tmp_path, monkeypatch):
        result = _write_library(tmp_path, monkeypatch, "ashio-copper-mine", ASHIO_TWO_TABLE_MARKDOWN)
        shopify = PlaneData()
        # Live carries the wider-mine variant, the SECOND row for this key.
        shopify.values[("series.metaobject", "heritage_status")] = (
            "National Historic Site of Japan, designated 28 March 2008"
        )

        findings = compute_disagreements(
            handle="ashio-copper-mine",
            series="Ashio Copper Mine",
            library=result.plane,
            shopify=shopify,
        )

        assert [f for f in findings if f.field == "heritage_status"] == []


# ---------------------------------------------------------------------------
# A trim of ANY candidate is still a trim, not exposure
# ---------------------------------------------------------------------------


class TestTrimAppliesAcrossCandidates:
    def test_live_trimmed_from_the_first_candidate_is_not_exposure(self, tmp_path, monkeypatch):
        result = _write_library(tmp_path, monkeypatch, "ashio-copper-mine", ASHIO_TWO_TABLE_MARKDOWN)
        shopify = PlaneData()
        # A strict prefix of the [S1] row, breaking at a word boundary.
        shopify.values[("series.metaobject", "location")] = (
            "Tsudō (通洞), Ashio Town (足尾町), now part of Nikkō City,"
        )

        findings = compute_disagreements(
            handle="ashio-copper-mine",
            series="Ashio Copper Mine",
            library=result.plane,
            shopify=shopify,
        )

        assert _r0_live_locations(findings) == []


# ---------------------------------------------------------------------------
# Internal-conflict detection must also consult every candidate
# ---------------------------------------------------------------------------


class TestInternalConflictConsultsEveryCandidate:
    """_master.md agreeing with ANY research candidate is agreement, not conflict.

    Same bug class as the R0-live one: the old parser kept only the last row, so
    a master entry matching the FIRST row was compared against the second and
    reported as two library files disagreeing when they do not.

    _parse_master_entry needs the handle backtick-wrapped in a pipe row and reads
    `| location | ...` (2 pipes, <=80 chars) out of the block that follows, so
    this fixture is compact rather than ashio's full two-table shape.
    """

    FIRST = "Tsudō, Ashio Town, Tochigi Prefecture, Japan [S1]"
    SECOND = "Ashio, northern Kantō region, Japan [S3]"
    # Matches FIRST — the row the old parser discarded.
    MASTER_SAYS = "Tsudō, Ashio Town, Tochigi Prefecture, Japan"

    def _read(self, tmp_path, monkeypatch):
        research_root = tmp_path / "facts-library" / "research" / "locations"
        research_root.mkdir(parents=True)
        (research_root / "ashio-copper-mine.md").write_text(
            "# Ashio\n\n"
            "## At a glance\n\n"
            "| Field | Value |\n|---|---|\n"
            f"| Location | {self.FIRST} |\n"
            "\n---\n\n"
            "| Field | Value |\n|---|---|\n"
            f"| Location | {self.SECOND} |\n"
            "\n## History\n\nNotes.\n",
            encoding="utf-8",
        )
        series_root = tmp_path / "facts-library" / "series"
        series_root.mkdir(parents=True)
        master = series_root / "_master.md"
        master.write_text(
            "| Series | Notes |\n|---|---|\n"
            "| `ashio-copper-mine` | Ashio Copper Mine |\n"
            f"| location | {self.MASTER_SAYS}\n",
            encoding="utf-8",
        )

        from lc_facts_reconcile.planes import library as lib_module

        monkeypatch.setattr(lib_module, "FACTS_ROOT", tmp_path / "facts-library")
        monkeypatch.setattr(lib_module, "RESEARCH_ROOT", research_root)
        monkeypatch.setattr(lib_module, "MASTER_FILE", master)
        monkeypatch.setattr(lib_module, "ENRICHMENT_ROOT", tmp_path / "facts-library" / "enrichment-drafts")
        return read_library("ashio-copper-mine")

    def test_fixture_actually_extracts_a_master_location(self, tmp_path, monkeypatch):
        """Guard the guard: a master entry that parses to nothing tests nothing."""
        result = self._read(tmp_path, monkeypatch)

        assert result.plane.get("series.master", "location") == self.MASTER_SAYS

    def test_master_matching_the_discarded_row_is_not_an_internal_conflict(
        self, tmp_path, monkeypatch
    ):
        result = self._read(tmp_path, monkeypatch)

        location_conflicts = [c for c in result.internal_conflicts if c.field == "location"]
        assert location_conflicts == []

    def test_master_matching_no_candidate_is_still_an_internal_conflict(
        self, tmp_path, monkeypatch
    ):
        """The guard must not be blinded here either."""
        self.MASTER_SAYS = "Osaka Prefecture, Kansai region, Japan"
        try:
            result = self._read(tmp_path, monkeypatch)
            location_conflicts = [c for c in result.internal_conflicts if c.field == "location"]
            assert len(location_conflicts) == 1
        finally:
            del self.MASTER_SAYS
