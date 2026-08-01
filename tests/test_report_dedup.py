"""LOS7-1857: write_report must not commit a new dated file when the only
thing that changed since the previous report is the run-date timestamp.
"""

from __future__ import annotations

from datetime import date, timedelta

import lc_facts_reconcile.report as report_mod
from lc_facts_reconcile.diff import Disagreement
from lc_facts_reconcile.report import ReportData, RunMetadata, render_report, write_report


def make_data(run_date: str, with_finding: bool = False) -> ReportData:
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


def test_write_report_skips_when_only_run_date_differs(tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, "REPORT_ROOT", tmp_path)

    yesterday = date.today() - timedelta(days=1)
    year_dir = tmp_path / str(yesterday.year)
    year_dir.mkdir(parents=True)
    yesterday_path = year_dir / f"reconciliation-report-{yesterday.isoformat()}.md"
    yesterday_path.write_text(render_report(make_data("2026-07-30 06:43 UTC")), encoding="utf-8")

    result_path = write_report(make_data("2026-07-31 06:43 UTC"))

    assert result_path == yesterday_path
    assert not report_mod.default_report_path().exists()


def test_write_report_writes_when_findings_actually_change(tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, "REPORT_ROOT", tmp_path)

    yesterday = date.today() - timedelta(days=1)
    year_dir = tmp_path / str(yesterday.year)
    year_dir.mkdir(parents=True)
    yesterday_path = year_dir / f"reconciliation-report-{yesterday.isoformat()}.md"
    yesterday_path.write_text(render_report(make_data("2026-07-30 06:43 UTC")), encoding="utf-8")

    today_path = report_mod.default_report_path()
    result_path = write_report(make_data("2026-07-31 06:43 UTC", with_finding=True))

    assert result_path == today_path
    assert today_path.exists()
    assert today_path.read_text(encoding="utf-8") != yesterday_path.read_text(encoding="utf-8")


def test_skip_if_unchanged_false_always_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, "REPORT_ROOT", tmp_path)

    yesterday = date.today() - timedelta(days=1)
    year_dir = tmp_path / str(yesterday.year)
    year_dir.mkdir(parents=True)
    yesterday_path = year_dir / f"reconciliation-report-{yesterday.isoformat()}.md"
    yesterday_path.write_text(render_report(make_data("2026-07-30 06:43 UTC")), encoding="utf-8")

    today_path = report_mod.default_report_path()
    result_path = write_report(make_data("2026-07-31 06:43 UTC"), skip_if_unchanged=False)

    assert result_path == today_path
    assert today_path.exists()


def test_explicit_output_path_always_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, "REPORT_ROOT", tmp_path)

    explicit_path = tmp_path / "manual-report.md"
    result_path = write_report(make_data("2026-07-31 06:43 UTC"), output_path=explicit_path)

    assert result_path == explicit_path
    assert explicit_path.exists()
