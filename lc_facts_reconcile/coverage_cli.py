"""CLI entry point for lc-coverage-audit (LOS7-628)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the lc-coverage-audit command."""
    parser = argparse.ArgumentParser(
        prog="lc-coverage-audit",
        description=(
            "Store-wide product metadata coverage + consistency audit (LOS7-628). "
            "Pages all store products and builds a per-product present/empty/non-conforming "
            "matrix against the canonical LC schema. Read-only; never writes to Shopify."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Stop after fetching N products (for sampling). "
            "Omit to scan the full store (~1894 products)."
        ),
    )
    parser.add_argument(
        "--handles",
        default=None,
        metavar="HANDLES",
        help=(
            "Comma-separated product handles to include. "
            "Combined with --limit: fetch up to --limit products then filter to these handles."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Override default report output path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write the report file; print the report to stdout instead.",
    )
    parser.add_argument(
        "--print-report",
        action="store_true",
        help="Print the full rendered report to stdout in addition to writing the file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    handles: list[str] | None = None
    if args.handles:
        handles = [h.strip() for h in args.handles.split(",") if h.strip()]

    output_path: str | None = args.output

    from .coverage import run_coverage_audit, render_coverage_report

    report = run_coverage_audit(
        limit=args.limit,
        handles=handles,
        output_path=output_path,
        dry_run=args.dry_run,
    )

    # Always render for the summary printout
    rendered = render_coverage_report(report)

    if args.dry_run or args.print_report:
        print(rendered)
    else:
        # Print compact summary to stdout
        print(f"\nProducts scanned:  {report.products_scanned}")
        schema_field_count = 0
        if report.rows:
            schema_field_count = report.rows[0].schema_field_count
        print(f"Schema fields/product: {schema_field_count}")
        total_present = sum(r.present_count for r in report.rows)
        total_empty = sum(r.empty_count for r in report.rows)
        total_nc = sum(r.non_conforming_count for r in report.rows)
        total = total_present + total_empty + total_nc
        pct = (total_present / total * 100) if total else 0
        print(f"Present:           {total_present} ({pct:.1f}%)")
        print(f"Empty:             {total_empty}")
        print(f"Non-conforming:    {total_nc}")

        incon = report.inconsistency_summary
        total_incon = sum(len(v) for v in incon.values())
        print(f"Inconsistency findings: {total_incon}")
        for class_key, items in incon.items():
            if items:
                from .coverage import INCONSISTENCY_CLASS_LABELS
                label = INCONSISTENCY_CLASS_LABELS.get(class_key, class_key)
                print(f"  {label}: {len(items)}")

        if report.errors:
            print(f"Errors: {len(report.errors)}", file=sys.stderr)
            for err in report.errors[:5]:
                print(f"  {err}", file=sys.stderr)

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
