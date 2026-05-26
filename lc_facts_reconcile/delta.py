"""--delta flag: diff the current run against a previous dated report.

Shows only findings that changed since the comparison date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .diff import Disagreement
from .report import REPORT_ROOT


@dataclass
class DeltaResult:
    added: list[Disagreement]
    resolved: list[tuple[str, str, str]]
    changed: list[tuple[Disagreement, str]]


def find_report_for_date(date_str: str) -> Path | None:
    """Find the closest report file at or before date_str."""
    year = date_str[:4]
    year_dir = REPORT_ROOT / year
    if not year_dir.exists():
        return None

    candidates = sorted(year_dir.glob("reconciliation-report-*.md"), reverse=True)
    for c in candidates:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", c.name)
        if m and m.group(1) <= date_str:
            return c
    return None


def parse_disagreements_from_report(path: Path) -> list[dict]:
    """Parse the disagreements table from a previous report."""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict] = []
    in_table = False
    header_passed = False

    for line in text.splitlines():
        if "| Severity |" in line:
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            header_passed = True
            continue
        if in_table and header_passed and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 4:
                rows.append({
                    "severity": cells[0],
                    "handle": cells[1],
                    "surface": cells[2],
                    "field": cells[3],
                })
        elif in_table and line.startswith("#"):
            break

    return rows


def compute_delta(
    current: list[Disagreement],
    previous_path: Path,
) -> DeltaResult:
    """Compare current run against a previous report."""
    prev_rows = parse_disagreements_from_report(previous_path)
    prev_keys = {(r["severity"], r["handle"], r["surface"], r["field"]) for r in prev_rows}
    curr_keys = {(d.severity, d.handle, d.surface, d.field) for d in current}

    added = [d for d in current if (d.severity, d.handle, d.surface, d.field) not in prev_keys]
    resolved = [
        (r["severity"], r["handle"], r["field"])
        for r in prev_rows
        if (r["severity"], r["handle"], r["surface"], r["field"]) not in curr_keys
    ]

    return DeltaResult(added=added, resolved=resolved, changed=[])


def format_delta_section(delta: DeltaResult) -> str:
    lines: list[str] = ["## Delta since previous report", ""]
    if delta.added:
        lines.append(f"### New findings ({len(delta.added)})")
        lines.append("")
        for d in delta.added:
            lines.append(f"- **{d.severity}** `{d.handle}` — {d.surface}/{d.field}")
        lines.append("")
    if delta.resolved:
        lines.append(f"### Resolved ({len(delta.resolved)})")
        lines.append("")
        for sev, handle, fld in delta.resolved:
            lines.append(f"- ~~{sev}~~ `{handle}` — {fld}")
        lines.append("")
    if not delta.added and not delta.resolved:
        lines.append("No changes since the comparison report.")
        lines.append("")
    return "\n".join(lines)
