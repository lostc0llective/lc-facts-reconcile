"""Main reconciliation runner — coordinates plane reads, diff, and report."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .diff import Disagreement, OpenClaim, PlaneData, compute_disagreements
from .planes.library import LibraryReadResult, list_research_handles, read_library
from .report import ReportData, RunMetadata, write_report


# Above this ratio of handles erroring on the live plane, the run is not a
# measurement — it is a failure wearing a report's clothes (LOS7-1585).
SHOPIFY_ERROR_ABORT_RATIO = 0.20


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
    # True when the live plane failed on so many handles that the run cannot be
    # read as "no findings". Callers MUST treat this as a failed run, not a clean
    # one. See run_failed below.
    aborted: bool = False
    abort_reason: str | None = None

    @property
    def run_failed(self) -> bool:
        """A run that read no live data is not a measurement of zero disagreements.

        On 2026-07-08 all 125 Shopify reads died on a latin-1 header encode. The
        run scanned 0 products, found 0 disagreements and exited 0 — so the only
        day the exit status looked clean was the day the reconciler was entirely
        broken. Anything deriving success from this result must consult this."""
        if self.aborted:
            return True
        if self.errors and self.product_count == 0:
            return True
        return False


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
        # library + shopify only. 'applied' and 'captions' are opt-in — see
        # LOS7-1587 and the --planes help text. Defaulting to all four is what
        # made every report advertise four planes while two supplied nothing.
        planes = {"library", "shopify"}

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
    shopify_errors = 0
    handles_tried = 0
    aborted = False
    abort_reason: str | None = None
    # Which planes actually supplied at least one value this run (LOS7-1587).
    planes_with_data: set[str] = set()

    for handle in all_handles:
        lib_result: LibraryReadResult = read_library(handle)
        library_plane = lib_result.plane
        internal_conflicts = lib_result.internal_conflicts
        all_open_claims.extend(lib_result.open_claims)

        applied_plane: PlaneData | None = None
        if applied_results and handle in applied_results.plane_by_handle:
            applied_plane = applied_results.plane_by_handle[handle]
            if applied_plane.values:
                planes_with_data.add("applied")

        shopify_plane: PlaneData | None = None
        if use_shopify:
            try:
                from .planes.shopify import read_shopify
                sho = read_shopify(handle)
                if sho.error:
                    errors.append(f"{handle}: Shopify read error — {sho.error}")
                    shopify_errors += 1
                else:
                    shopify_plane = sho.plane
                    total_products += sho.product_count
                    if shopify_plane.values:
                        planes_with_data.add("shopify")
            except Exception as exc:
                errors.append(f"{handle}: Shopify read exception — {exc}")
                shopify_errors += 1

            # Abort rather than grind through every remaining handle emitting the
            # same error and then writing a report that reads as clean. Only
            # meaningful once a few handles have been attempted, so a single early
            # failure on a short run does not trip it.
            handles_tried += 1
            if (
                handles_tried >= 5
                and shopify_errors / handles_tried > SHOPIFY_ERROR_ABORT_RATIO
            ):
                aborted = True
                abort_reason = (
                    f"Live (Shopify) plane failed on {shopify_errors} of "
                    f"{handles_tried} handles attempted "
                    f"({shopify_errors / handles_tried:.0%} > "
                    f"{SHOPIFY_ERROR_ABORT_RATIO:.0%} threshold). "
                    f"First error: {errors[0] if errors else 'unknown'}"
                )
                break

        captions_plane: PlaneData | None = None
        if use_captions:
            try:
                from .planes.captions import read_captions
                cap = read_captions(handle)
                if cap:
                    captions_plane = cap.plane
                    if captions_plane.values:
                        planes_with_data.add("captions")
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

    # Report what actually CONTRIBUTED, not what was requested. Every report ever
    # written advertised "applied, captions, library, shopify" purely because all
    # four were requested by default, while applied and captions supplied `(none)`
    # on all 3,762 graded rows — so three of six severity grades were
    # unreachable and the header said otherwise (LOS7-1587).
    planes_contributed = sorted(
        p for p in planes if p in planes_with_data or p == "library"
    )
    # NOT appended to `errors`: that list drives run_failed, and a legitimate
    # library-only run scans 0 products, so pushing a warning there would make an
    # intentional run self-report as failed.
    planes_requested_empty = sorted(planes - set(planes_contributed))

    metadata = RunMetadata(
        run_date=run_date,
        trigger=trigger,
        series_scanned=len(all_handles),
        products_scanned=total_products,
        planes_used=planes_contributed,
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
        aborted=aborted,
        abort_reason=abort_reason,
    )


def _discover_handles() -> list[str]:
    """Return all handles to scan. Prefers research-file-backed handles."""
    handles = list_research_handles()
    if not handles:
        return []
    return sorted(set(handles))
