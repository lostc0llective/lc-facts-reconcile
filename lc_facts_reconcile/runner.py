"""Main reconciliation runner — coordinates plane reads, diff, and report."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .diff import Disagreement, OpenClaim, PlaneData, compute_disagreements
from .planes.library import LibraryReadResult, list_research_handles, read_library
from .report import ReportData, RunMetadata, write_report


@dataclass
class ReconciliationResult:
    report_path: Path
    disagreements: list[Disagreement]
    open_claims: list[OpenClaim]
    series_count: int
    product_count: int
    disagreement_count: int
    by_severity: dict[str, int]
    open_claim_count: int
    errors: list[str]


def run_reconciliation(
    handles: list[str] | None = None,
    planes: set[str] | None = None,
    since_date: date | None = None,
    severity_filter: str | None = None,
    delta_date: str | None = None,
    linear_comment: bool = False,
    linear_issue: str | None = None,
    output_path: Path | None = None,
    dry_run: bool = False,
) -> ReconciliationResult:
    if planes is None:
        planes = {"library", "applied", "shopify", "captions"}

    all_handles = handles or _discover_handles()

    use_applied = "applied" in planes
    use_shopify = "shopify" in planes
    use_captions = "captions" in planes

    applied_results = None
    if use_applied:
        from .planes.applied import read_applied
        applied_results = read_applied(handles=all_handles, since=since_date)

    all_disagreements: list[Disagreement] = []
    all_open_claims: list[OpenClaim] = []
    errors: list[str] = []
    total_products = 0

    for handle in all_handles:
        lib_result: LibraryReadResult = read_library(handle)
        library_plane = lib_result.plane
        internal_conflicts = lib_result.internal_conflicts
        all_open_claims.extend(lib_result.open_claims)

        applied_plane: PlaneData | None = None
        if applied_results and handle in applied_results.plane_by_handle:
            applied_plane = applied_results.plane_by_handle[handle]

        shopify_plane: PlaneData | None = None
        if use_shopify:
            try:
                from .planes.shopify import read_shopify
                sho = read_shopify(handle)
                if sho.error:
                    errors.append(f"{handle}: Shopify read error — {sho.error}")
                else:
                    shopify_plane = sho.plane
                    total_products += sho.product_count
            except Exception as exc:
                errors.append(f"{handle}: Shopify read exception — {exc}")

        captions_plane: PlaneData | None = None
        if use_captions:
            try:
                from .planes.captions import read_captions
                cap = read_captions(handle)
                if cap:
                    captions_plane = cap.plane
            except Exception as exc:
                errors.append(f"{handle}: captions read exception — {exc}")

        series_name = handle.replace("-", " ").title()
        disagreements = compute_disagreements(
            handle=handle,
            series=series_name,
            library=library_plane,
            applied=applied_plane,
            shopify=shopify_plane,
            captions=captions_plane,
            internal_conflicts=internal_conflicts,
        )
        all_disagreements.extend(disagreements)

    if severity_filter:
        all_disagreements = [d for d in all_disagreements if d.severity == severity_filter]

    by_severity: dict[str, int] = {}
    for d in all_disagreements:
        by_severity[d.severity] = by_severity.get(d.severity, 0) + 1

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    trigger = "manual" if not since_date else f"incremental since {since_date.isoformat()}"
    if handles:
        trigger = f"scoped ({', '.join(handles)})"

    metadata = RunMetadata(
        run_date=run_date,
        trigger=trigger,
        series_scanned=len(all_handles),
        products_scanned=total_products,
        planes_used=sorted(planes),
        since_date=since_date.isoformat() if since_date else None,
        handles_scoped=handles or [],
        errors=errors,
    )

    report_data = ReportData(
        metadata=metadata,
        disagreements=all_disagreements,
        open_claims=all_open_claims,
    )

    final_path: Path | None = None
    if delta_date:
        from .delta import find_report_for_date, compute_delta, format_delta_section
        prev_path = find_report_for_date(delta_date)
        if prev_path:
            delta = compute_delta(all_disagreements, prev_path)
            delta_section = format_delta_section(delta)
        else:
            delta_section = f"\n\n## Delta\n\nNo previous report found for {delta_date}.\n"

    if not dry_run:
        final_path = write_report(report_data, output_path)
        if delta_date and "delta_section" in dir():
            existing = final_path.read_text(encoding="utf-8")
            final_path.write_text(existing + "\n" + delta_section, encoding="utf-8")
    else:
        from .report import default_report_path
        final_path = output_path or default_report_path()

    if linear_comment and linear_issue and not dry_run:
        from .linear_comment import post_r0_summary
        post_r0_summary(
            issue_id=linear_issue,
            report_path=final_path,
            disagreements=all_disagreements,
            dry_run=dry_run,
        )

    return ReconciliationResult(
        report_path=final_path,
        disagreements=all_disagreements,
        open_claims=all_open_claims,
        series_count=len(all_handles),
        product_count=total_products,
        disagreement_count=len(all_disagreements),
        by_severity=by_severity,
        open_claim_count=len(all_open_claims),
        errors=errors,
    )


def _discover_handles() -> list[str]:
    """Return all handles to scan. Prefers research-file-backed handles."""
    handles = list_research_handles()
    if not handles:
        return []
    return sorted(set(handles))
