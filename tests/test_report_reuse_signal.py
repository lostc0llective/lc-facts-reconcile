"""LOS7-2004: a reused report must be reported AS reused.

The LOS7-1857 dedup is correct, but it made the daily log lie. When findings
are unchanged, `write_report` hands back an OLDER dated report and the CLI
printed `Report: <that old path>` with no indication it had not been written
today. Four days of healthy runs therefore read as four days of a broken job,
and cost a full investigation before the code was consulted.

The dedup decides whether to write; this signal reports what it decided.
"""

from __future__ import annotations

from datetime import date, timedelta

import lc_facts_reconcile.report as report_mod
from lc_facts_reconcile.report import (
    ReportData,
    RunMetadata,
    render_report,
    report_was_reused,
    write_report,
)


def make_data(run_date: str, with_finding: bool = False) -> ReportData:
    from lc_facts_reconcile.diff import Disagreement

    metadata = RunMetadata(
        run_date=run_date,
        trigger="manual",
        series_scanned=3,
        products_scanned=10,
        planes_used=["library", "shopify"],
    )
    disagreements = []
    if with_finding:
        disagreements.append(
            Disagreement(
                severity="drift",
                series="Bathurst Gasworks",
                handle="bathurst-gasworks",
                surface="series",
                field="location",
                library_says="VALUE-X",
                applied_says=None,
                shopify_says="VALUE-Y",
                caption_says=None,
                resolution_rule="live wins",
                recommended_action="update library",
            )
        )
    return ReportData(metadata=metadata, disagreements=disagreements, open_claims=[])


def _seed_yesterday(tmp_path, with_finding: bool = False):
    yesterday = date.today() - timedelta(days=1)
    year_dir = tmp_path / str(yesterday.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    path = year_dir / f"reconciliation-report-{yesterday.isoformat()}.md"
    path.write_text(
        render_report(make_data("2026-07-30 06:43 UTC", with_finding)), encoding="utf-8"
    )
    return path


def test_reused_report_is_flagged_as_reused(tmp_path, monkeypatch):
    """Unchanged findings -> the returned path is an older report -> reused."""
    monkeypatch.setattr(report_mod, "REPORT_ROOT", tmp_path)
    yesterday_path = _seed_yesterday(tmp_path)

    result_path = write_report(make_data("2026-07-31 06:43 UTC"))

    assert result_path == yesterday_path
    assert report_was_reused(result_path) is True


def test_freshly_written_report_is_not_flagged_as_reused(tmp_path, monkeypatch):
    """Changed findings -> today's dated file is written -> not reused."""
    monkeypatch.setattr(report_mod, "REPORT_ROOT", tmp_path)
    _seed_yesterday(tmp_path)

    result_path = write_report(make_data("2026-07-31 06:43 UTC", with_finding=True))

    assert result_path == report_mod.default_report_path()
    assert report_was_reused(result_path) is False


def test_explicit_output_path_is_never_reused(tmp_path, monkeypatch):
    """--output always writes what it is told to, so it is never a reuse."""
    monkeypatch.setattr(report_mod, "REPORT_ROOT", tmp_path)
    explicit_path = tmp_path / "manual-report.md"

    result_path = write_report(make_data("2026-07-31 06:43 UTC"), output_path=explicit_path)

    assert report_was_reused(result_path, output_path=explicit_path) is False
