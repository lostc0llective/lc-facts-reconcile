"""Fail-closed regression tests (LOS7-1585).

Reproduces the 2026-07-08 failure: all 125 Shopify reads died on a latin-1
header encode, the run scanned 0 products, found 0 disagreements, wrote a
report that read as clean, and exited 0. Because diff.py gates the R0-live
branch on `sho_val is not None`, a wholesale live-plane failure makes R0-live
unreachable by construction — so deriving the exit status from the R0-live
count alone guaranteed that total failure looked like success.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lc_facts_reconcile.planes.shopify import _assert_header_safe
from lc_facts_reconcile.runner import ReconciliationResult


def make_result(**kwargs) -> ReconciliationResult:
    base = dict(
        report_path=Path("/tmp/report.md"),
        disagreements=[],
        open_claims=[],
        series_count=125,
        product_count=0,
        disagreement_count=0,
        by_severity={},
        open_claim_count=0,
        errors=[],
    )
    base.update(kwargs)
    return ReconciliationResult(**base)


class TestRunFailed:
    def test_the_2026_07_08_shape_is_a_failure(self):
        """125 errors, 0 products, 0 disagreements — the exact shape that exited 0."""
        result = make_result(
            errors=[f"handle-{i}: Shopify read error — latin-1 codec" for i in range(125)],
            product_count=0,
        )
        assert result.run_failed is True

    def test_clean_run_is_not_a_failure(self):
        result = make_result(product_count=1963, errors=[])
        assert result.run_failed is False

    def test_healthy_run_with_a_few_errors_is_not_a_failure(self):
        """Partial errors while still reading live data is a normal degraded run,
        not a failed one. Only zero products alongside errors is fatal."""
        result = make_result(
            product_count=1900,
            errors=["one-handle: Shopify read error — timeout"],
        )
        assert result.run_failed is False

    def test_explicit_abort_is_a_failure_even_with_products_read(self):
        """An abort part-way through means the numbers are incomplete, so the run
        is unusable regardless of how many products were read before it tripped."""
        result = make_result(
            product_count=400,
            errors=["x: boom"],
            aborted=True,
            abort_reason="Live plane failed on 30 of 40 handles",
        )
        assert result.run_failed is True

    def test_zero_products_with_no_errors_is_not_a_failure(self):
        """An empty-but-clean run (e.g. a handle filter matching nothing) is not
        the failure mode this guards. Errors are what make zero suspicious."""
        result = make_result(product_count=0, errors=[])
        assert result.run_failed is False


class TestHeaderSafety:
    def test_em_dash_token_is_rejected(self):
        """The actual 2026-07-08 cause: an em dash in the token value."""
        with pytest.raises(RuntimeError) as exc:
            _assert_header_safe("shpat_abc—def")
        assert "not a valid HTTP header value" in str(exc.value)

    def test_error_never_leaks_the_token_value(self):
        """The original urllib error leaked a character of the credential into
        the log. This message must not carry any of the token."""
        token = "shpat_SECRETVALUE—MORESECRET"
        with pytest.raises(RuntimeError) as exc:
            _assert_header_safe(token)
        msg = str(exc.value)
        assert "SECRETVALUE" not in msg
        assert "MORESECRET" not in msg
        assert "—" not in msg
        assert "position" not in msg.lower()

    def test_error_reports_how_many_bad_characters(self):
        with pytest.raises(RuntimeError) as exc:
            _assert_header_safe("a—b’c")
        assert "2 non-latin-1 character(s)" in str(exc.value)

    def test_normal_token_passes(self):
        assert _assert_header_safe("shpat_0123456789abcdefABCDEF") is None
