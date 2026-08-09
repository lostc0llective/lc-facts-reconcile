"""CLI entry point for lc-facts-reconcile."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

VALID_PLANES = {"library", "applied", "shopify", "captions"}
VALID_SEVERITIES = {"R0-live", "R0-pending", "drift", "caption-conflict", "internal", "stale-claim"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lc-facts-reconcile",
        description="Diff engine for the LC facts library (Agent 5).",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Comma-separated series handles to scope the run, e.g. bathurst-gasworks,woolla",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only diff applied records modified since this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--planes",
        default="library,shopify,applied",
        help=(
            "Comma-separated subset of planes: library,applied,shopify,captions. "
            "Default is library,shopify,applied. 'captions' stays OPT-IN — see "
            "LOS7-1587 — because whether caption != library is a defect is an "
            "editorial call, not a code one. 'applied' rejoined the default "
            "2026-08-04 (LOS7-1929): it now reads a structured per-product "
            "record shape instead of scraping free-form prose."
        ),
    )
    parser.add_argument(
        "--severity",
        default=None,
        help="Filter output to this severity only, e.g. R0-live",
    )
    parser.add_argument(
        "--delta",
        default=None,
        metavar="YYYY-MM-DD",
        help="Diff current run against the closest previous report on or before this date.",
    )
    parser.add_argument(
        "--linear-comment",
        action="store_true",
        help="Post R0-live summary to a Linear issue. Requires --linear-issue.",
    )
    parser.add_argument(
        "--linear-issue",
        default=None,
        help="Linear issue ID to comment against (e.g. LOS7-XXX). Required with --linear-comment.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override default report output path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write files or post Linear comments.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.linear_comment and not args.linear_issue:
        parser.error("--linear-comment requires --linear-issue.")

    planes = {p.strip() for p in args.planes.split(",") if p.strip()}
    unknown_planes = planes - VALID_PLANES
    if unknown_planes:
        parser.error(f"Unknown planes: {', '.join(sorted(unknown_planes))}. Valid: {', '.join(sorted(VALID_PLANES))}")

    handles: list[str] | None = None
    if args.only:
        handles = [h.strip() for h in args.only.split(",") if h.strip()]

    since_date: date | None = None
    if args.since:
        try:
            since_date = date.fromisoformat(args.since)
        except ValueError:
            parser.error(f"--since must be YYYY-MM-DD, got: {args.since}")

    output_path: Path | None = None
    if args.output:
        output_path = Path(args.output).expanduser()

    from .runner import run_reconciliation

    result = run_reconciliation(
        handles=handles,
        planes=planes,
        since_date=since_date,
        severity_filter=args.severity,
        delta_date=args.delta,
        linear_comment=args.linear_comment,
        linear_issue=args.linear_issue,
        output_path=output_path,
        dry_run=args.dry_run,
    )

    from .report import report_was_reused

    print(f"\nReport:      {result.report_path}")
    # Say so when the dedup fired. Printing a path that was NOT written today
    # with no further comment is what made four healthy runs look like a dead
    # job (LOS7-2004).
    if not args.dry_run and report_was_reused(result.report_path, output_path):
        print(
            "             ^ REUSED: findings are unchanged, so no new dated "
            "report was written today (LOS7-1857 dedup). This is normal."
        )
    print(f"Series:      {result.series_count}")
    print(f"Products:    {result.product_count}")
    print(f"Disagreements: {result.disagreement_count} total")
    for sev, count in sorted(result.by_severity.items()):
        if count:
            print(f"  {sev}: {count}")
    if result.open_claim_count:
        print(f"Open claims: {result.open_claim_count}")
    if result.errors:
        print(f"Errors:      {len(result.errors)}", file=sys.stderr)
        for err in result.errors[:5]:
            print(f"  {err}", file=sys.stderr)

    # Exit 3 = the run FAILED and its numbers mean nothing. This must be checked
    # before the R0-live test: a wholesale live-plane failure makes R0-live
    # unreachable by construction (diff.py gates it on `sho_val is not None`), so
    # deriving the status from the R0-live count alone made total failure exit 0 —
    # the one green day in the series was the completely broken one (LOS7-1585).
    # 3, not 2: argparse already owns 2 for usage errors (see DEPLOYMENT.md).
    if result.run_failed:
        reason = result.abort_reason or (
            f"{len(result.errors)} error(s) and 0 products scanned"
        )
        print(f"\nRUN FAILED: {reason}", file=sys.stderr)
        print(
            "Exit 3 — this run is NOT a measurement of zero disagreements. "
            "Do not read its report as clean.",
            file=sys.stderr,
        )
        return 3

    # Exit 1 is a FINDINGS signal, not a failure — the tri-state is
    # 0 = no R0-live, 1 = R0-live outstanding, 3 = the run itself failed.
    # Nothing said so, so a daily exit 1 sitting in `launchctl list` was read
    # as a daily crash and cost an investigation (LOS7-2004). Say it out loud.
    r0_live = sum(1 for d in result.disagreements if d.severity == "R0-live")
    if r0_live:
        print(
            f"\nExit 1 — {r0_live} R0-live disagreement(s) outstanding. The run "
            "COMPLETED NORMALLY; this is a findings signal, not a failure. "
            "(0 = none outstanding, 1 = R0-live outstanding, 3 = run failed.)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
