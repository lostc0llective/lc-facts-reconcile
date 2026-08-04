"""Applied-plane parsing tests (LOS7-1929).

The original free-form regex parser was opt-out because it reliably produced
garbage handles/fields from prose (LOS7-1587). This covers the replacement:
a parser for the structured per-series, per-product record shape factual-audit
applies write, plus the multi-root discovery and chronological conflict
resolution that make it safe to run by default.
"""

from __future__ import annotations

import pytest

from lc_facts_reconcile.planes import applied as applied_mod


def write_record(root, series: str, field: str, applied_date: str, blocks: list[tuple[str, str, str]]) -> None:
    """blocks: list of (product_handle, before, after)."""
    lines = [
        f"# {series} — subject_description applied record",
        "",
        "**Issue:** LOS7-1870 (Phase 2 apply of the LOS7-1864 audit)",
        f"**Applied:** {applied_date}",
        f"**Field:** `{field}` (multi_line_text_field)",
        f"**Products written:** {len(blocks)}",
        "",
        "## Values written",
        "",
    ]
    for handle, before, after in blocks:
        lines += [
            f"### `{handle}`",
            "",
            "**Before:**",
            "",
            f"> {before}",
            "",
            "**After:**",
            "",
            f"> {after}",
            "",
        ]
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{series}.md").write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture
def applied_roots(tmp_path, monkeypatch):
    applied_root = tmp_path / "applied"
    audits_root = tmp_path / "audits"
    monkeypatch.setattr(applied_mod, "APPLIED_ROOT", applied_root)
    monkeypatch.setattr(applied_mod, "AUDITS_ROOT", audits_root)
    return applied_root, audits_root


class TestStructuredParsing:
    def test_one_entry_per_product_block(self, applied_roots):
        _, audits_root = applied_roots
        pass_dir = audits_root / "subject-description-factual-reaudit-2026-07-31" / "applied"
        write_record(pass_dir, "ashio-copper-mine", "custom.subject_description", "2026-07-31", [
            ("ashio-copper-mine-crusher", "The cone crusher took the first pass.", "The crusher took the first pass."),
            ("ashio-copper-mine-gantry", "Grated steel walkways span the refinery floor.", "Grated steel walkways span the dressing floor."),
        ])
        result = applied_mod.read_applied()
        assert len(result.entries) == 2
        series_plane = result.plane_by_handle["ashio-copper-mine"]
        assert series_plane.values[("product.ashio-copper-mine-crusher", "subject_description")] == (
            "The crusher took the first pass."
        )
        assert series_plane.values[("product.ashio-copper-mine-gantry", "subject_description")] == (
            "Grated steel walkways span the dressing floor."
        )

    def test_custom_prefix_is_stripped_from_field_name(self, applied_roots):
        _, audits_root = applied_roots
        pass_dir = audits_root / "some-pass" / "applied"
        write_record(pass_dir, "bathurst-gasworks", "custom.print_story", "2026-08-01", [
            ("bathurst-gasworks-purifier-shed", "before text", "after text"),
        ])
        result = applied_mod.read_applied()
        series_plane = result.plane_by_handle["bathurst-gasworks"]
        assert ("product.bathurst-gasworks-purifier-shed", "print_story") in series_plane.values
        assert ("product.bathurst-gasworks-purifier-shed", "custom.print_story") not in series_plane.values

    def test_handles_filter_scopes_by_series_not_product(self, applied_roots):
        _, audits_root = applied_roots
        pass_dir = audits_root / "pass" / "applied"
        write_record(pass_dir, "ashio-copper-mine", "custom.subject_description", "2026-07-31", [
            ("ashio-copper-mine-crusher", "before", "after"),
        ])
        write_record(pass_dir, "bathurst-gasworks", "custom.subject_description", "2026-07-31", [
            ("bathurst-gasworks-purifier-shed", "before", "after"),
        ])
        result = applied_mod.read_applied(handles=["ashio-copper-mine"])
        assert list(result.plane_by_handle.keys()) == ["ashio-copper-mine"]

    def test_non_structured_file_is_skipped_not_guessed_at(self, applied_roots):
        """Free-form prose (the LOS7-1587 shape) must not produce entries —
        it must be silently skipped, not fed through prose heuristics."""
        applied_root, _ = applied_roots
        applied_root.mkdir(parents=True, exist_ok=True)
        (applied_root / "some-sprint-report.md").write_text(
            "# Some sprint\n\n**Series:** wangi-power-station\n\n"
            "We changed a few things after the fact and it went fine.\n",
            encoding="utf-8",
        )
        result = applied_mod.read_applied()
        assert result.entries == []
        assert result.plane_by_handle == {}

    def test_missing_field_header_defaults_to_subject_description(self, applied_roots):
        _, audits_root = applied_roots
        pass_dir = audits_root / "pass" / "applied"
        pass_dir.mkdir(parents=True, exist_ok=True)
        (pass_dir / "kandos-cement-works.md").write_text(
            "# kandos-cement-works\n\n"
            "### `kandos-cement-works-control-room`\n\n"
            "**Before:**\n\n> old text\n\n"
            "**After:**\n\n> new text\n\n",
            encoding="utf-8",
        )
        result = applied_mod.read_applied()
        series_plane = result.plane_by_handle["kandos-cement-works"]
        assert ("product.kandos-cement-works-control-room", "subject_description") in series_plane.values


class TestMultiRootDiscovery:
    def test_walks_both_top_level_and_per_audit_applied_dirs(self, applied_roots):
        applied_root, audits_root = applied_roots
        write_record(applied_root, "elrington-colliery", "custom.subject_description", "2026-06-01", [
            ("elrington-colliery-drawing-desk", "before", "top-level after"),
        ])
        write_record(audits_root / "some-pass" / "applied", "kandos-cement-works", "custom.subject_description", "2026-06-01", [
            ("kandos-cement-works-dust-screws", "before", "audit after"),
        ])
        result = applied_mod.read_applied()
        assert "elrington-colliery" in result.plane_by_handle
        assert "kandos-cement-works" in result.plane_by_handle

    def test_directory_named_applied_but_not_under_an_audit_folder_is_ignored(self, applied_roots):
        applied_root, audits_root = applied_roots
        # A stray folder under audits/ with no "applied" subfolder must not error.
        (audits_root / "not-a-real-pass").mkdir(parents=True, exist_ok=True)
        applied_root.mkdir(parents=True, exist_ok=True)
        result = applied_mod.read_applied()
        assert result.entries == []

    def test_no_roots_exist_returns_empty_not_an_error(self, applied_roots):
        result = applied_mod.read_applied()
        assert result.entries == []
        assert result.plane_by_handle == {}


class TestChronologicalConflictResolution:
    def test_the_later_applied_date_wins_regardless_of_filesystem_order(self, applied_roots):
        """Two applied records touch the same (surface, field) for the same
        product at different dates. root.rglob() order is filesystem-
        dependent, not chronological -- an older record silently overwriting
        a newer one would reintroduce the exact false-positive this rewrite
        exists to fix on the next audit pass."""
        applied_root, audits_root = applied_roots
        write_record(
            audits_root / "second-pass-alphabetically-first" / "applied",
            "tin-city", "custom.subject_description", "2026-08-15",
            [("tin-city-aerials", "before", "LATEST correct text")],
        )
        write_record(
            audits_root / "z-first-pass-alphabetically-last" / "applied",
            "tin-city", "custom.subject_description", "2026-07-01",
            [("tin-city-aerials", "before", "stale earlier text")],
        )
        result = applied_mod.read_applied()
        series_plane = result.plane_by_handle["tin-city"]
        assert series_plane.values[("product.tin-city-aerials", "subject_description")] == "LATEST correct text"


class TestRealCorpusRegression:
    """The exact numbers a correct parse of the live LOS7-1870 corpus
    produces, per the LOS7-1929 diagnosis. Skipped if the corpus isn't on
    disk (e.g. CI without the brand-voice cowork tree mounted)."""

    def test_ashio_copper_mine_crusher_resolves_to_the_post_audit_wording(self):
        if not applied_mod.AUDITS_ROOT.exists():
            pytest.skip("brand-voice cowork tree not present in this environment")
        result = applied_mod.read_applied(handles=["ashio-copper-mine"])
        series_plane = result.plane_by_handle.get("ashio-copper-mine")
        assert series_plane is not None
        after = series_plane.values.get(("product.ashio-copper-mine-crusher", "subject_description"))
        assert after is not None
        assert after.startswith("The crusher took the first pass")
        assert "cone crusher" not in after
