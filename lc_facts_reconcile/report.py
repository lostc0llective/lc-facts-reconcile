"""Render the reconciliation report as markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .diff import Disagreement, OpenClaim

REPORT_ROOT = Path.home() / "Claude/cowork/brand-voice/facts-library/_reconciliation"

SEVERITY_ORDER = ["R0-live", "R0-pending", "internal", "drift", "caption-conflict", "stale-claim"]


@dataclass
class RunMetadata:
    run_date: str
    trigger: str
    series_scanned: int
    products_scanned: int
    planes_used: list[str]
    since_date: str | None = None
    handles_scoped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ReportData:
    metadata: RunMetadata
    disagreements: list[Disagreement]
    open_claims: list[OpenClaim]
    series_summaries: dict[str, str] = field(default_factory=dict)


def default_report_path() -> Path:
    today = date.today()
    year_dir = REPORT_ROOT / str(today.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    return year_dir / f"reconciliation-report-{today.isoformat()}.md"


def render_report(data: ReportData) -> str:
    lines: list[str] = []

    lines.append("# LC Facts Library Reconciliation Report")
    lines.append("")
    lines.append(f"**Run date:** {data.metadata.run_date}")
    lines.append(f"**Trigger:** {data.metadata.trigger}")
    lines.append(f"**Planes:** {', '.join(data.metadata.planes_used)}")
    if data.metadata.since_date:
        lines.append(f"**Since:** {data.metadata.since_date}")
    if data.metadata.handles_scoped:
        lines.append(f"**Scoped to:** {', '.join(data.metadata.handles_scoped)}")
    lines.append("")

    counts = _count_by_severity(data.disagreements)
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Series scanned: {data.metadata.series_scanned}")
    lines.append(f"- Products scanned: {data.metadata.products_scanned}")
    lines.append(f"- Total disagreements: {len(data.disagreements)}")
    for sev in SEVERITY_ORDER:
        n = counts.get(sev, 0)
        if n:
            lines.append(f"  - {sev}: {n}")
    if data.metadata.errors:
        lines.append(f"- Errors during scan: {len(data.metadata.errors)}")
    lines.append("")

    if data.disagreements:
        lines.append("## Disagreements")
        lines.append("")
        lines.append("| Severity | Handle | Surface | Field | Library says | Applied says | Shopify says | Caption says | Resolution | Action |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")

        sorted_d = sorted(
            data.disagreements,
            key=lambda d: (SEVERITY_ORDER.index(d.severity) if d.severity in SEVERITY_ORDER else 99, d.handle)
        )
        for d in sorted_d:
            row = [
                d.severity,
                d.handle,
                d.surface,
                d.field,
                _cell(d.library_says),
                _cell(d.applied_says),
                _cell(d.shopify_says),
                _cell(d.caption_says),
                d.resolution_rule[:60] + "..." if len(d.resolution_rule) > 63 else d.resolution_rule,
                d.recommended_action[:60] + "..." if len(d.recommended_action) > 63 else d.recommended_action,
            ]
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    if data.series_summaries:
        lines.append("## Per-series summaries")
        lines.append("")
        for handle, summary in sorted(data.series_summaries.items()):
            lines.append(f"### {handle}")
            lines.append("")
            lines.append(summary)
            lines.append("")

    if data.open_claims:
        lines.append("## Open-claims register")
        lines.append("")
        lines.append("All `[FACT: verify]` and 'Claims to verify' entries across research files.")
        lines.append("")
        by_handle: dict[str, list[OpenClaim]] = {}
        for oc in data.open_claims:
            by_handle.setdefault(oc.handle, []).append(oc)
        for handle in sorted(by_handle):
            lines.append(f"### {handle}")
            lines.append("")
            for oc in by_handle[handle]:
                lines.append(f"- {oc.claim_text}")
            lines.append("")

    if data.metadata.errors:
        lines.append("## Scan errors")
        lines.append("")
        for err in data.metadata.errors:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines)


def _cell(val: str | None) -> str:
    if val is None:
        return "(none)"
    cleaned = str(val).replace("|", "&#124;").replace("\n", " ")
    return cleaned[:80] + "..." if len(cleaned) > 83 else cleaned


def _count_by_severity(disagreements: list[Disagreement]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in disagreements:
        counts[d.severity] = counts.get(d.severity, 0) + 1
    return counts


def write_report(data: ReportData, output_path: Path | None = None) -> Path:
    path = output_path or default_report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_report(data)
    path.write_text(content, encoding="utf-8")
    return path
