"""Tests for the coverage audit module (LOS7-628).

All tests are pure-unit using synthetic fixture data.
No file system or Shopify API access required.
"""

from __future__ import annotations

import pytest

from lc_facts_reconcile.coverage import (
    STATUS_EMPTY,
    STATUS_NON_CONFORMING,
    STATUS_PRESENT,
    INCONSISTENCY_CLASS_LABELS,
    SCHEMA_FIELDS,
    FieldStatus,
    ProductCoverageRow,
    analyse_product,
    detect_cross_product_inconsistencies,
    render_coverage_report,
    run_coverage_audit,
    CoverageReport,
    _classify_field,
    _metafield_map,
    page_all_products,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def make_mf(namespace: str, key: str, value: str, type_: str = "single_line_text_field") -> dict:
    """Build a Shopify metafield node dict."""
    return {"namespace": namespace, "key": key, "value": value, "type": type_}


def make_product(
    handle: str = "test-product",
    title: str = "Test Product",
    metafields: list[dict] | None = None,
    seo_title: str = "",
    seo_desc: str = "",
    variants: list[dict] | None = None,
    tags: list[str] | None = None,
    featured_image_alt: str = "",
) -> dict:
    """Build a minimal Shopify product node dict matching the GQL response shape."""
    mf_edges = [{"node": mf} for mf in (metafields or [])]
    variant_edges = [{"node": v} for v in (variants or [])]
    fi = {"altText": featured_image_alt} if featured_image_alt else None
    return {
        "id": f"gid://shopify/Product/{abs(hash(handle))}",
        "handle": handle,
        "title": title,
        "seo": {"title": seo_title, "description": seo_desc},
        "tags": tags or [],
        "featuredImage": fi,
        "metafields": {"edges": mf_edges},
        "variants": {"edges": variant_edges},
    }


def make_variant(
    size: str,
    type_: str,
    colour: str = "",
    sku_handle: str = "test-product",
) -> dict:
    """Build a variant node matching the live LC abbreviated SKU format.

    Live format (verified 2026-06-22):
      Unframed: Colour=N/A, SKU suffix -UF
      Framed:   Colour=Raw/White/Black, SKU suffix -FR-R/-FR-W/-FR-B
      Acrylic:  Colour=N/A, SKU suffix -GL
    """
    colour_val = colour if colour else "N/A"
    options = [
        {"name": "Size", "value": size},
        {"name": "Type", "value": type_},
        {"name": "Colour", "value": colour_val},
    ]
    # Build abbreviated SKU
    type_abbrev = {"Unframed": "UF", "Acrylic": "GL"}.get(type_, type_)
    if type_ == "Framed" and colour:
        colour_abbrev = {"Raw": "R", "White": "W", "Black": "B"}.get(colour, colour[0])
        sku = f"LC-{sku_handle}-{size}-FR-{colour_abbrev}"
    else:
        sku = f"LC-{sku_handle}-{size}-{type_abbrev}"
    return {
        "id": f"gid://shopify/ProductVariant/{abs(hash(size + type_ + colour))}",
        "title": f"{size} / {type_}",
        "sku": sku,
        "selectedOptions": options,
    }


def make_complete_variants(handle: str = "test-product") -> list[dict]:
    """Return the full expected 25-variant set using live LC format."""
    variants: list[dict] = []
    for size in ("XS", "S", "M", "L", "XL"):
        variants.append(make_variant(size, "Unframed", sku_handle=handle))
        variants.append(make_variant(size, "Acrylic", sku_handle=handle))
        for colour in ("Raw", "White", "Black"):
            variants.append(make_variant(size, "Framed", colour, sku_handle=handle))
    return variants


# ---------------------------------------------------------------------------
# _classify_field tests
# ---------------------------------------------------------------------------

class TestClassifyField:
    def test_empty_when_no_metafield(self):
        status = _classify_field("custom", "print_story", "bespoke", None)
        assert status.status == STATUS_EMPTY

    def test_empty_when_value_is_blank(self):
        mf = make_mf("custom", "print_story", "")
        status = _classify_field("custom", "print_story", "bespoke", mf)
        assert status.status == STATUS_EMPTY

    def test_present_when_value_set(self):
        mf = make_mf("custom", "print_story", "A story about this photograph.")
        status = _classify_field("custom", "print_story", "bespoke", mf)
        assert status.status == STATUS_PRESENT
        assert status.value == "A story about this photograph."

    def test_paper_type_known_value(self):
        mf = make_mf("custom", "paper_type", "Ilford Galerie Smooth Cotton Rag 310 gsm")
        status = _classify_field("custom", "paper_type", "constant", mf)
        assert status.status == STATUS_PRESENT

    def test_paper_type_unknown_value(self):
        mf = make_mf("custom", "paper_type", "Hahnemuhle Photo Rag 308gsm")
        status = _classify_field("custom", "paper_type", "constant", mf)
        assert status.status == STATUS_NON_CONFORMING
        assert "paper_type" in (status.note or "")

    def test_capture_date_valid_iso(self):
        mf = make_mf("custom", "capture_date", "2019-04-15")
        status = _classify_field("custom", "capture_date", "per-photo", mf)
        assert status.status == STATUS_PRESENT

    def test_capture_date_year_only(self):
        mf = make_mf("custom", "capture_date", "2019")
        status = _classify_field("custom", "capture_date", "per-photo", mf)
        assert status.status == STATUS_PRESENT

    def test_capture_date_invalid_format(self):
        mf = make_mf("custom", "capture_date", "April 2019")
        status = _classify_field("custom", "capture_date", "per-photo", mf)
        assert status.status == STATUS_NON_CONFORMING

    def test_gps_lat_numeric(self):
        mf = make_mf("custom", "gps_lat", "-32.123456")
        status = _classify_field("custom", "gps_lat", "per-photo", mf)
        assert status.status == STATUS_PRESENT

    def test_gps_lat_non_numeric(self):
        mf = make_mf("custom", "gps_lat", "south")
        status = _classify_field("custom", "gps_lat", "per-photo", mf)
        assert status.status == STATUS_NON_CONFORMING

    def test_location_country_code_valid(self):
        mf = make_mf("custom", "location_country_code", "AU")
        status = _classify_field("custom", "location_country_code", "per-photo", mf)
        assert status.status == STATUS_PRESENT

    def test_location_country_code_invalid(self):
        mf = make_mf("custom", "location_country_code", "australia")
        status = _classify_field("custom", "location_country_code", "per-photo", mf)
        assert status.status == STATUS_NON_CONFORMING

    def test_global_title_tag_conforming(self):
        mf = make_mf("global", "title_tag", "Wangi Power Station A | Lost Collective")
        status = _classify_field("global", "title_tag", "google/global", mf)
        assert status.status == STATUS_PRESENT

    def test_global_title_tag_missing_suffix(self):
        mf = make_mf("global", "title_tag", "Wangi Power Station A")
        status = _classify_field("global", "title_tag", "google/global", mf)
        assert status.status == STATUS_NON_CONFORMING
        assert "suffix" in (status.note or "")

    def test_global_title_tag_too_long(self):
        long_title = "X" * 61 + " | Lost Collective"
        mf = make_mf("global", "title_tag", long_title)
        status = _classify_field("global", "title_tag", "google/global", mf)
        assert status.status == STATUS_NON_CONFORMING
        assert "length" in (status.note or "")

    def test_global_description_tag_too_long(self):
        mf = make_mf("global", "description_tag", "D" * 161)
        status = _classify_field("global", "description_tag", "google/global", mf)
        assert status.status == STATUS_NON_CONFORMING

    def test_global_description_tag_conforming(self):
        mf = make_mf("global", "description_tag", "A short description.")
        status = _classify_field("global", "description_tag", "google/global", mf)
        assert status.status == STATUS_PRESENT


# ---------------------------------------------------------------------------
# _metafield_map tests
# ---------------------------------------------------------------------------

class TestMetafieldMap:
    def test_builds_namespace_key_index(self):
        node = make_product(metafields=[
            make_mf("custom", "cat_number", "WPS-001"),
            make_mf("global", "title_tag", "Title | Lost Collective"),
        ])
        mf_map = _metafield_map(node)
        assert ("custom", "cat_number") in mf_map
        assert ("global", "title_tag") in mf_map
        assert mf_map[("custom", "cat_number")]["value"] == "WPS-001"

    def test_empty_product_returns_empty_map(self):
        node = make_product()
        mf_map = _metafield_map(node)
        assert mf_map == {}


# ---------------------------------------------------------------------------
# analyse_product tests
# ---------------------------------------------------------------------------

class TestAnalyseProduct:
    def _minimal_conforming_mfs(self, handle: str = "test-product") -> list[dict]:
        """Return a set of metafields that satisfy the schema for a product.

        Uses live field names verified 2026-06-22:
          custom.shutter_speed (not shutter)
          custom.focal_length_mm (not focal_length)
        """
        return [
            # Constant tier
            make_mf("custom", "paper_type", "Ilford Galerie Smooth Cotton Rag 310 gsm"),
            make_mf("custom", "print_technique", "giclée"),
            make_mf("custom", "certificate_included", "true"),
            make_mf("custom", "edition_size", "25"),
            make_mf("custom", "edition_notes", "Individually numbered."),
            make_mf("custom", "orientation", "landscape"),
            # Per-photo tier
            make_mf("custom", "cat_number", "WPS-001"),
            make_mf("custom", "gps_lat", "-32.9814"),
            make_mf("custom", "gps_lng", "151.5487"),
            make_mf("custom", "location", "Wangi Wangi, NSW"),
            make_mf("custom", "location_country", "Australia"),
            make_mf("custom", "location_country_code", "AU"),
            make_mf("custom", "camera_body", "Nikon D800"),
            make_mf("custom", "lens", "Nikkor 14-24mm"),
            make_mf("custom", "aperture", "8.0"),
            make_mf("custom", "iso", "100"),
            make_mf("custom", "shutter_speed", "1/60"),
            make_mf("custom", "focal_length_mm", "14"),
            make_mf("custom", "capture_date", "2019-04-15"),
            make_mf("custom", "alt_text", "The turbine hall at Wangi Power Station."),
            make_mf("custom", "subject_description", "A broad view of the turbine hall."),
            make_mf("custom", "lightroom_id", "lr-001"),
            make_mf("custom", "lr_sync_at", "2026-05-01T00:00:00Z"),
            # Bespoke tier
            make_mf("custom", "print_story", "This photograph was made on a winter morning."),
            make_mf("custom", "story_excerpt", "A winter morning at Wangi."),
            # Commerce tier
            make_mf("limited_edition", "limited_stock", '[{"vid":"1","qty":25}]'),
            # Google/global tier
            make_mf("global", "title_tag", "Wangi A | Lost Collective"),
            make_mf("global", "description_tag", "A fine art print of the turbine hall."),
            make_mf("google", "custom_product", "TRUE"),
            make_mf("google", "gmc_id", "shopify_AU_123"),
            make_mf("google", "google_product_type", "Home & Garden > Decor > Artwork"),
            make_mf("google", "condition", "new"),
        ]

    def test_fully_conforming_product_has_no_empty_or_nc_fields(self):
        mfs = self._minimal_conforming_mfs()
        product = make_product(
            handle="wangi-power-station-a",
            metafields=mfs,
            seo_title="Wangi A | Lost Collective",
            seo_desc="A fine art print.",
            variants=make_complete_variants("wangi-power-station-a"),
            featured_image_alt="The turbine hall.",
        )
        row = analyse_product(product)
        nc_fields = [f for f in row.fields.values() if f.status == STATUS_NON_CONFORMING]
        assert nc_fields == [], f"Expected 0 non-conforming fields; got: {[(f.namespace, f.key, f.note) for f in nc_fields]}"

    def test_product_with_no_metafields_is_all_empty(self):
        product = make_product(handle="empty-product")
        row = analyse_product(product)
        assert row.empty_count == len(SCHEMA_FIELDS)
        assert row.present_count == 0
        assert row.non_conforming_count == 0

    def test_extra_metafield_detected(self):
        mfs = [
            make_mf("custom", "paper_type", "Ilford Galerie Smooth Cotton Rag 310 gsm"),
            make_mf("custom", "unknown_future_field", "some value"),
        ]
        product = make_product(handle="test", metafields=mfs)
        row = analyse_product(product)
        assert ("custom", "unknown_future_field") in row.extra_keys

    def test_schema_fields_in_canonical_schema_are_not_extra(self):
        mfs = [make_mf("custom", "print_story", "A story.")]
        product = make_product(handle="test", metafields=mfs)
        row = analyse_product(product)
        assert ("custom", "print_story") not in row.extra_keys

    def test_seo_title_missing_flags(self):
        product = make_product(handle="test", seo_title="", seo_desc="Desc")
        row = analyse_product(product)
        assert any("title" in issue for issue in row.seo_issues)

    def test_seo_title_missing_suffix_flags(self):
        product = make_product(handle="test", seo_title="A title without suffix", seo_desc="Desc")
        row = analyse_product(product)
        assert any("suffix" in issue for issue in row.seo_issues)

    def test_seo_conforming_has_no_issues(self):
        product = make_product(
            handle="test",
            seo_title="Short Title | Lost Collective",
            seo_desc="A clear, concise description under 160 characters.",
        )
        row = analyse_product(product)
        assert row.seo_issues == [], f"Unexpected SEO issues: {row.seo_issues}"

    def test_featured_image_alt_present(self):
        product = make_product(handle="test", featured_image_alt="Turbine hall")
        row = analyse_product(product)
        assert row.featured_image_alt == "Turbine hall"

    def test_featured_image_alt_absent(self):
        product = make_product(handle="test", featured_image_alt="")
        row = analyse_product(product)
        assert row.featured_image_alt is None

    def test_complete_variant_matrix_has_no_missing_combos(self):
        product = make_product(
            handle="wangi-power-station-a",
            variants=make_complete_variants("wangi-power-station-a"),
        )
        row = analyse_product(product)
        assert row.missing_variant_combos == [], (
            f"Expected no missing combos; got: {row.missing_variant_combos[:5]}"
        )

    def test_missing_variants_detected(self):
        # Only supply Unframed variants -- Framed and Acrylic will be missing
        variants = [make_variant(sz, "Unframed", sku_handle="test") for sz in ("XS", "S", "M", "L", "XL")]
        product = make_product(handle="test", variants=variants)
        row = analyse_product(product)
        missing = row.missing_variant_combos
        assert any("Acrylic" in c for c in missing), f"Acrylic should be missing: {missing}"
        assert any("Framed" in c for c in missing), f"Framed should be missing: {missing}"

    def test_sku_violation_detected(self):
        v = make_variant("XS", "Unframed", sku_handle="test")
        v["sku"] = "WRONG-SKU-FORMAT"
        product = make_product(handle="test", variants=[v])
        row = analyse_product(product)
        assert row.sku_violations, f"Expected SKU violation; got none"

    def test_valid_sku_no_violation(self):
        # make_variant now generates abbreviated SKUs matching live format
        v = make_variant("XS", "Unframed", sku_handle="test-product")
        assert v["sku"] == "LC-test-product-XS-UF", f"Fixture SKU wrong: {v['sku']}"
        product = make_product(handle="test-product", variants=[v])
        row = analyse_product(product)
        assert row.sku_violations == [], f"Unexpected violations: {row.sku_violations}"

    def test_tags_captured(self):
        product = make_product(handle="test", tags=["limited-edition", "wangi"])
        row = analyse_product(product)
        assert "limited-edition" in row.tags
        assert row.has_limited_edition_tag

    def test_lr_sync_at_captured(self):
        product = make_product(handle="test", metafields=[
            make_mf("custom", "lr_sync_at", "2026-05-01T00:00:00Z"),
        ])
        row = analyse_product(product)
        assert row.lr_sync_at == "2026-05-01T00:00:00Z"

    def test_lr_sync_at_none_when_absent(self):
        product = make_product(handle="test")
        row = analyse_product(product)
        assert row.lr_sync_at is None


# ---------------------------------------------------------------------------
# detect_cross_product_inconsistencies tests
# ---------------------------------------------------------------------------

class TestCrossProductInconsistencies:
    def _row(
        self,
        handle: str,
        paper_type: str | None = None,
        print_technique: str | None = None,
        seo_issues: list[str] | None = None,
        extra_keys: list[tuple[str, str]] | None = None,
        sku_violations: list[str] | None = None,
        missing_variant_combos: list[str] | None = None,
        featured_image_alt: str | None = None,
        lr_sync_at: str | None = None,
    ) -> ProductCoverageRow:
        row = ProductCoverageRow(product_id=f"gid://1/{handle}", handle=handle, title=handle)
        row.seo_issues = seo_issues or []
        row.extra_keys = extra_keys or []
        row.sku_violations = sku_violations or []
        row.missing_variant_combos = missing_variant_combos or []
        row.featured_image_alt = featured_image_alt
        row.lr_sync_at = lr_sync_at

        if paper_type:
            row.fields[("custom", "paper_type")] = FieldStatus(
                namespace="custom", key="paper_type", tier="constant",
                status=STATUS_PRESENT, value=paper_type,
            )
        if print_technique:
            row.fields[("custom", "print_technique")] = FieldStatus(
                namespace="custom", key="print_technique", tier="constant",
                status=STATUS_PRESENT, value=print_technique,
            )
        return row

    def test_uniform_paper_type_no_inconsistency(self):
        rows = [
            self._row("p1", paper_type="Ilford Galerie Smooth Cotton Rag 310 gsm"),
            self._row("p2", paper_type="Ilford Galerie Smooth Cotton Rag 310 gsm"),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert result["paper_type_values"] == [], "Same paper type should not flag"

    def test_mixed_paper_types_flags(self):
        rows = [
            self._row("p1", paper_type="Ilford Galerie Smooth Cotton Rag 310 gsm"),
            self._row("p2", paper_type="Hahnemuhle Photo Rag 308gsm"),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert len(result["paper_type_values"]) == 2, (
            f"Expected 2 paper_type entries; got {result['paper_type_values']}"
        )

    def test_seo_issues_aggregated(self):
        rows = [
            self._row("p1", seo_issues=["seo.title empty"]),
            self._row("p2", seo_issues=["seo.title missing '| Lost Collective' suffix"]),
            self._row("p3"),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert len(result["seo_pattern_violations"]) == 2

    def test_extra_keys_aggregated(self):
        rows = [
            self._row("p1", extra_keys=[("custom", "mystery_field")]),
            self._row("p2"),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert any("mystery_field" in item for item in result["extra_metafield_keys"])

    def test_missing_featured_image_alt_aggregated(self):
        rows = [
            self._row("p1", featured_image_alt=None),
            self._row("p2", featured_image_alt="A proper alt text"),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert "p1" in result["missing_featured_image_alt"]
        assert "p2" not in result["missing_featured_image_alt"]

    def test_lr_sync_never_aggregated(self):
        rows = [
            self._row("p1", lr_sync_at=None),
            self._row("p2", lr_sync_at="2026-05-01T00:00:00Z"),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert "p1" in result["lr_sync_never"]
        assert "p2" not in result["lr_sync_never"]

    def test_sku_violations_aggregated(self):
        rows = [
            self._row("p1", sku_violations=["'WRONG' (variant: XS/Unframed)"]),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert result["sku_pattern_violations"], "Expected SKU violation entry"

    def test_missing_variants_aggregated(self):
        rows = [
            self._row("p1", missing_variant_combos=["XS/Acrylic", "S/Acrylic"]),
        ]
        result = detect_cross_product_inconsistencies(rows)
        assert any("p1" in item for item in result["missing_variant_combos"])


# ---------------------------------------------------------------------------
# render_coverage_report tests
# ---------------------------------------------------------------------------

class TestRenderCoverageReport:
    def _make_report(self, rows: list[ProductCoverageRow] | None = None) -> CoverageReport:
        from datetime import datetime, timezone
        return CoverageReport(
            run_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            trigger="coverage-audit limit=2",
            products_scanned=len(rows or []),
            products_with_errors=0,
            rows=rows or [],
            inconsistency_summary={k: [] for k in INCONSISTENCY_CLASS_LABELS},
        )

    def test_renders_header(self):
        report = self._make_report()
        rendered = render_coverage_report(report)
        assert "LC Product Metadata Coverage" in rendered

    def test_renders_per_product_matrix_row(self):
        row = ProductCoverageRow(
            product_id="gid://1/test",
            handle="test-handle",
            title="Test Product",
        )
        report = self._make_report([row])
        rendered = render_coverage_report(report)
        assert "test-handle" in rendered

    def test_renders_inconsistency_section(self):
        report = self._make_report()
        report.inconsistency_summary["seo_pattern_violations"] = ["test-handle: seo.title empty"]
        rendered = render_coverage_report(report)
        assert "SEO pattern violations" in rendered
        assert "test-handle" in rendered

    def test_renders_no_inconsistencies_message_when_clean(self):
        report = self._make_report()
        rendered = render_coverage_report(report)
        assert "No cross-product inconsistencies detected" in rendered

    def test_renders_non_conforming_detail(self):
        row = ProductCoverageRow(
            product_id="gid://1/test",
            handle="test-nc",
            title="Test NC",
        )
        row.fields[("custom", "paper_type")] = FieldStatus(
            namespace="custom", key="paper_type", tier="constant",
            status=STATUS_NON_CONFORMING, value="Wrong paper",
            note="unexpected paper_type",
        )
        report = self._make_report([row])
        rendered = render_coverage_report(report)
        assert "Non-conforming field detail" in rendered
        assert "test-nc" in rendered

    def test_renders_extra_keys_section(self):
        row = ProductCoverageRow(
            product_id="gid://1/test",
            handle="test-extra",
            title="Test Extra",
        )
        row.extra_keys = [("custom", "undocumented_key")]
        report = self._make_report([row])
        rendered = render_coverage_report(report)
        assert "Unknown/extra metafield keys" in rendered
        assert "undocumented_key" in rendered


# ---------------------------------------------------------------------------
# page_all_products + run_coverage_audit with a stub gql_fn
# ---------------------------------------------------------------------------

class TestCoverageAuditWithStub:
    """Test run_coverage_audit using a stub gql_fn (no live Shopify needed)."""

    def _make_gql_fn(self, products: list[dict]):
        """Return a callable that returns a single-page GQL response."""
        def gql_fn(query: str, variables: dict | None = None) -> dict:
            return {
                "data": {
                    "products": {
                        "edges": [{"cursor": str(i), "node": p} for i, p in enumerate(products)],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        return gql_fn

    def test_page_all_products_returns_all_nodes(self):
        products = [make_product(f"p{i}") for i in range(3)]
        gql_fn = self._make_gql_fn(products)
        result = page_all_products(gql_fn=gql_fn)
        assert len(result) == 3
        assert {p["handle"] for p in result} == {"p0", "p1", "p2"}

    def test_page_all_products_respects_limit(self):
        products = [make_product(f"p{i}") for i in range(10)]
        gql_fn = self._make_gql_fn(products)
        result = page_all_products(limit=3, gql_fn=gql_fn)
        assert len(result) == 3

    def test_run_coverage_audit_returns_report(self):
        products = [
            make_product(
                handle="wangi-turbine",
                title="Wangi Turbine",
                seo_title="Wangi Turbine | Lost Collective",
                seo_desc="Fine art print of the turbine.",
                metafields=[
                    make_mf("custom", "cat_number", "WPS-T-001"),
                ],
            ),
        ]
        gql_fn = self._make_gql_fn(products)
        report = run_coverage_audit(limit=5, dry_run=True, gql_fn=gql_fn)
        assert report.products_scanned == 1
        assert report.errors == []
        assert len(report.rows) == 1
        assert report.rows[0].handle == "wangi-turbine"

    def test_run_coverage_audit_handle_filter(self):
        products = [
            make_product(handle="wangi-a"),
            make_product(handle="kinugawa-b"),
        ]
        gql_fn = self._make_gql_fn(products)
        report = run_coverage_audit(handles=["wangi-a"], dry_run=True, gql_fn=gql_fn)
        assert report.products_scanned == 1
        assert report.rows[0].handle == "wangi-a"

    def test_run_coverage_audit_catches_shopify_error(self):
        def error_gql(query, variables=None):
            raise RuntimeError("Shopify down")

        report = run_coverage_audit(limit=5, dry_run=True, gql_fn=error_gql)
        assert report.products_scanned == 0
        assert report.errors, "Expected at least one error entry"
        assert any("Shopify" in e for e in report.errors)

    def test_full_audit_inconsistency_summary_populated(self):
        # Two products with different paper types should surface paper_type_values class
        products = [
            make_product(
                handle="p1",
                metafields=[make_mf("custom", "paper_type", "Ilford Galerie Smooth Cotton Rag 310 gsm")],
            ),
            make_product(
                handle="p2",
                metafields=[make_mf("custom", "paper_type", "Hahnemuhle Photo Rag 308gsm")],
            ),
        ]
        gql_fn = self._make_gql_fn(products)
        report = run_coverage_audit(dry_run=True, gql_fn=gql_fn)
        assert report.inconsistency_summary["paper_type_values"], (
            "Mixed paper types should trigger paper_type_values inconsistency"
        )


# ---------------------------------------------------------------------------
# Schema definition integrity check
# ---------------------------------------------------------------------------

def test_schema_fields_has_no_duplicates():
    """Each (namespace, key) pair should appear at most once in SCHEMA_FIELDS."""
    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    for ns, key, _ in SCHEMA_FIELDS:
        if (ns, key) in seen:
            duplicates.append((ns, key))
        seen.add((ns, key))
    assert duplicates == [], f"Duplicate schema fields: {duplicates}"


def test_all_inconsistency_class_labels_covered():
    """INCONSISTENCY_CLASS_LABELS must have an entry for every key
    detect_cross_product_inconsistencies can return."""
    report = CoverageReport(
        run_date="2026-06-22",
        trigger="test",
        products_scanned=0,
        products_with_errors=0,
    )
    result = detect_cross_product_inconsistencies([])
    for key in result:
        assert key in INCONSISTENCY_CLASS_LABELS, (
            f"inconsistency key {key!r} not in INCONSISTENCY_CLASS_LABELS"
        )
