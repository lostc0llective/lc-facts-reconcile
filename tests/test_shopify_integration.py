"""Integration tests for the Shopify plane.

Skipped by default. Run with `pytest -m integration` after sourcing
Shopify credentials via `op run --env-file=...env.tpl --`.
"""

from __future__ import annotations

import os

import pytest

from lc_facts_reconcile.planes.shopify import read_shopify


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("SHOPIFY_CLIENT_ID") or not os.environ.get("SHOPIFY_CLIENT_SECRET"),
    reason="Shopify credentials not in env",
)
def test_shopify_read_returns_products():
    """Live integration test against wangi-power-station.

    Wangi has 51 products on the live store; a working read must return >0.
    This test would have caught the silent-failure bug that shipped 2026-05-26.

    Run: op run --env-file=~/Claude/code-projects/lost-collective-dawn/.env.tpl -- pytest -m integration
    """
    result = read_shopify("wangi-power-station")
    assert result.error is None, f"Shopify read errored: {result.error}"
    assert result.product_count > 0, (
        f"Expected >0 products for wangi-power-station; got {result.product_count}"
    )
