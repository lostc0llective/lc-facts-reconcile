"""Store-wide product metadata coverage + consistency audit (LOS7-628).

Checks every store product against the canonical LC schema (gold standard = Wangi PDP)
and produces a per-product present / empty / non-conforming matrix.

Three schema tiers
------------------
1. Constant/formulaic   -- uniform or size-derived; same value expected on all products.
2. Per-photo            -- sourced from Lightroom/EXIF; unique per product.
3. Bespoke (authored)   -- hand-written rich text.
4. Commerce             -- variant matrix, SKUs, stock flags, tags (checked separately).

This module classifies only. No writes to Shopify or the facts library.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

# Field status values
STATUS_PRESENT = "present"
STATUS_EMPTY = "empty"
STATUS_NON_CONFORMING = "non-conforming"
STATUS_UNKNOWN = "unknown"   # field key exists but type unexpected

# Schema tier labels
TIER_CONSTANT = "constant"
TIER_PER_PHOTO = "per-photo"
TIER_BESPOKE = "bespoke"
TIER_COMMERCE = "commerce"

# Maximum acceptable length for SEO title (chars)
SEO_TITLE_MAX_LEN = 60
# Maximum acceptable length for SEO description (chars)
SEO_DESC_MAX_LEN = 160
# Brand suffix expected in SEO titles  e.g. " | Lost Collective"
SEO_TITLE_SUFFIX_PATTERN = re.compile(r"\|\s*Lost Collective\s*$", re.IGNORECASE)
# Expected paper type values
EXPECTED_PAPER_TYPES = {
    "ilford galerie smooth cotton rag 310gsm",
    "ilford galerie smooth cotton rag 310 gsm",
    "ilford galerie metallic gloss 260gsm",
    "ilford galerie metallic gloss 260 gsm",
}
# Expected print technique (live store uses "Giclée" with accent; accept both)
EXPECTED_PRINT_TECHNIQUES = {"giclée", "giclee", "pigment ink"}

# Canonical size labels for variant check
CANONICAL_SIZES = {"XS", "S", "M", "L", "XL"}
CANONICAL_TYPES = {"Unframed", "Framed", "Acrylic"}

# SKU pattern matching the live LC abbreviated format:
#   LC-<product-handle>-<SIZE>-UF                  (Unframed, Colour=N/A)
#   LC-<product-handle>-<SIZE>-FR-R/W/B            (Framed, Raw/White/Black)
#   LC-<product-handle>-<SIZE>-GL                  (Acrylic/Glass, Colour=N/A)
SKU_PATTERN = re.compile(
    r"^LC-[a-z0-9-]+-(?:XS|S|M|L|XL)-(?:UF|FR-[RWB]|GL)$"
)

# Metafield keys that must be present (per-photo tier).
# Key names match what is live on the store (verified 2026-06-22 against
# terminus-hotel and wangi-power-station collections):
#   custom.focal_length_mm  (not focal_length)
#   custom.shutter_speed    (not shutter)
PER_PHOTO_METAFIELDS = [
    ("custom", "cat_number"),
    ("custom", "gps_lat"),
    ("custom", "gps_lng"),
    ("custom", "location"),
    ("custom", "location_country"),
    ("custom", "location_country_code"),
    ("custom", "camera_body"),
    ("custom", "lens"),
    ("custom", "aperture"),
    ("custom", "iso"),
    ("custom", "shutter_speed"),
    ("custom", "focal_length_mm"),
    ("custom", "capture_date"),
    ("custom", "alt_text"),
    ("custom", "subject_description"),
    ("custom", "lightroom_id"),
    ("custom", "lr_sync_at"),
]

# Constant/formulaic metafields
CONSTANT_METAFIELDS = [
    ("custom", "paper_type"),
    ("custom", "print_technique"),
    ("custom", "certificate_included"),
    ("custom", "edition_size"),
    ("custom", "edition_notes"),
    ("custom", "orientation"),
]

# Google Merchant Center metafields (present on all fully-built products)
GOOGLE_METAFIELDS = [
    ("google", "custom_product"),
    ("google", "gmc_id"),
    ("google", "google_product_type"),
    ("google", "condition"),
]

# Global SEO metafields
GLOBAL_METAFIELDS = [
    ("global", "title_tag"),
    ("global", "description_tag"),
]

# Commerce/limited-edition metafields
COMMERCE_METAFIELDS = [
    ("limited_edition", "limited_stock"),
]

# Bespoke authored fields
BESPOKE_METAFIELDS = [
    ("custom", "print_story"),
    ("custom", "story_excerpt"),
]

# All schema fields with their tier
SCHEMA_FIELDS: list[tuple[str, str, str]] = (
    [(ns, key, TIER_CONSTANT) for ns, key in CONSTANT_METAFIELDS]
    + [(ns, key, TIER_PER_PHOTO) for ns, key in PER_PHOTO_METAFIELDS]
    + [(ns, key, TIER_BESPOKE) for ns, key in BESPOKE_METAFIELDS]
    + [(ns, key, TIER_COMMERCE) for ns, key in COMMERCE_METAFIELDS]
    + [(ns, key, "google/global") for ns, key in GOOGLE_METAFIELDS + GLOBAL_METAFIELDS]
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FieldStatus:
    """Status of one schema field on one product."""
    namespace: str
    key: str
    tier: str
    status: str   # STATUS_* constant
    value: str | None = None
    note: str | None = None   # non-conforming reason


@dataclass
class ProductCoverageRow:
    """Per-product coverage result."""
    product_id: str
    handle: str
    title: str
    # Schema field statuses keyed by (namespace, key)
    fields: dict[tuple[str, str], FieldStatus] = field(default_factory=dict)
    # Extra/unknown metafield keys found on this product (not in schema)
    extra_keys: list[tuple[str, str]] = field(default_factory=list)
    # Variant coverage
    variant_count: int = 0
    missing_variant_combos: list[str] = field(default_factory=list)
    sku_violations: list[str] = field(default_factory=list)
    # SEO issues
    seo_title: str | None = None
    seo_description: str | None = None
    seo_issues: list[str] = field(default_factory=list)
    # Featured image alt text
    featured_image_alt: str | None = None
    # LR sync status
    lr_sync_at: str | None = None
    # Tags
    tags: list[str] = field(default_factory=list)
    has_limited_edition_tag: bool = False

    @property
    def present_count(self) -> int:
        return sum(1 for f in self.fields.values() if f.status == STATUS_PRESENT)

    @property
    def empty_count(self) -> int:
        return sum(1 for f in self.fields.values() if f.status == STATUS_EMPTY)

    @property
    def non_conforming_count(self) -> int:
        return sum(1 for f in self.fields.values() if f.status == STATUS_NON_CONFORMING)

    @property
    def schema_field_count(self) -> int:
        return len(self.fields)


@dataclass
class CoverageReport:
    """Store-wide coverage audit result."""
    run_date: str
    trigger: str
    products_scanned: int
    products_with_errors: int
    rows: list[ProductCoverageRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Aggregated inconsistency classes found across all products
    inconsistency_summary: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shopify GraphQL fetcher (store-wide product pager)
# ---------------------------------------------------------------------------

# Reuse auth from the existing shopify plane
def _get_gql():
    """Import gql from the shopify plane (avoids duplicating auth logic)."""
    from .planes.shopify import gql
    return gql


# The coverage audit fetches more metafields than the reconcile plane.
# We fetch every metafield namespace via the metafields connection so we can
# detect UNKNOWN / extra keys (schema inconsistency class 4 in the spec).
COVERAGE_PRODUCT_QUERY = """
query CoverageProducts($after: String) {
  products(first: 10, after: $after) {
    edges {
      cursor
      node {
        id
        title
        handle
        seo { title description }
        tags
        featuredImage { altText }
        metafields(first: 100) {
          edges {
            node {
              namespace
              key
              value
              type
            }
          }
        }
        variants(first: 30) {
          edges {
            node {
              id
              title
              sku
              selectedOptions { name value }
            }
          }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def fetch_products_page(after: str | None, gql_fn: Any) -> dict:
    """Fetch one page of products from Shopify."""
    variables: dict = {}
    if after:
        variables["after"] = after
    return gql_fn(COVERAGE_PRODUCT_QUERY, variables)


def page_all_products(limit: int | None = None, gql_fn: Any = None) -> list[dict]:
    """Page through all store products. Returns raw node dicts.

    Args:
        limit: If set, stop after fetching this many products (for sampling).
        gql_fn: Callable for GraphQL requests. Defaults to planes.shopify.gql.
    """
    if gql_fn is None:
        gql_fn = _get_gql()

    products: list[dict] = []
    cursor: str | None = None

    while True:
        resp = fetch_products_page(cursor, gql_fn)
        conn = (resp.get("data") or {}).get("products") or {}
        edges = conn.get("edges") or []

        for edge in edges:
            node = edge.get("node") or {}
            if node:
                products.append(node)
            if limit is not None and len(products) >= limit:
                return products

        page_info = conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

        # Polite pause between pages to avoid rate-limit pressure
        time.sleep(0.2)

    return products


# ---------------------------------------------------------------------------
# Per-product analysis
# ---------------------------------------------------------------------------

def _metafield_map(node: dict) -> dict[tuple[str, str], dict]:
    """Build a (namespace, key) -> metafield dict from a product node."""
    result: dict[tuple[str, str], dict] = {}
    for edge in (node.get("metafields") or {}).get("edges") or []:
        mf = edge.get("node") or {}
        ns = mf.get("namespace", "")
        key = mf.get("key", "")
        if ns and key:
            result[(ns, key)] = mf
    return result


def _classify_field(ns: str, key: str, tier: str, mf: dict | None) -> FieldStatus:
    """Classify one schema field on one product."""
    if mf is None or not mf.get("value"):
        return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_EMPTY)

    value = mf["value"]
    note: str | None = None

    # Conformance checks per field
    if ns == "custom" and key == "paper_type":
        norm = value.strip().lower()
        if norm not in EXPECTED_PAPER_TYPES:
            note = f"unexpected paper_type: {value!r}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)

    if ns == "custom" and key == "print_technique":
        norm = value.strip().lower()
        if norm not in EXPECTED_PRINT_TECHNIQUES:
            note = f"unexpected print_technique: {value!r}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)

    if ns == "custom" and key == "capture_date":
        # Expect ISO date YYYY-MM-DD or YYYY
        if not re.match(r"^\d{4}(-\d{2}-\d{2})?$", value.strip()):
            note = f"capture_date format unexpected: {value!r}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)

    if ns == "custom" and key in ("gps_lat", "gps_lng"):
        try:
            float(value.strip())
        except ValueError:
            note = f"{key} not numeric: {value!r}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)

    if ns == "custom" and key == "location_country_code":
        # Expect ISO 3166-1 alpha-2 (2 uppercase letters)
        if not re.match(r"^[A-Z]{2}$", value.strip()):
            note = f"location_country_code not ISO-2: {value!r}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)

    if ns == "global" and key == "title_tag":
        if len(value) > SEO_TITLE_MAX_LEN:
            note = f"title_tag length {len(value)} > {SEO_TITLE_MAX_LEN}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)
        if not SEO_TITLE_SUFFIX_PATTERN.search(value):
            note = f"title_tag missing '| Lost Collective' suffix: {value!r}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)

    if ns == "global" and key == "description_tag":
        if len(value) > SEO_DESC_MAX_LEN:
            note = f"description_tag length {len(value)} > {SEO_DESC_MAX_LEN}"
            return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_NON_CONFORMING, value=value, note=note)

    return FieldStatus(namespace=ns, key=key, tier=tier, status=STATUS_PRESENT, value=value)


def _check_seo(node: dict, row: ProductCoverageRow) -> None:
    """Populate SEO fields and flag issues on the row."""
    seo = node.get("seo") or {}
    title = (seo.get("title") or "").strip()
    desc = (seo.get("description") or "").strip()
    row.seo_title = title or None
    row.seo_description = desc or None

    if not title:
        row.seo_issues.append("seo.title empty")
    else:
        if len(title) > SEO_TITLE_MAX_LEN:
            row.seo_issues.append(f"seo.title length {len(title)} > {SEO_TITLE_MAX_LEN}")
        if not SEO_TITLE_SUFFIX_PATTERN.search(title):
            row.seo_issues.append("seo.title missing '| Lost Collective' suffix")

    if not desc:
        row.seo_issues.append("seo.description empty")
    else:
        if len(desc) > SEO_DESC_MAX_LEN:
            row.seo_issues.append(f"seo.description length {len(desc)} > {SEO_DESC_MAX_LEN}")


def _check_variants(node: dict, row: ProductCoverageRow) -> None:
    """Check variant matrix completeness and SKU conformance.

    Live LC variant structure (verified 2026-06-22):
      Size x Type x Colour options always present.
      Unframed: Colour = N/A; Acrylic: Colour = N/A; Framed: Colour = Raw/White/Black.

    Expected 25-variant matrix:
      5 sizes x (Unframed/N/A + Acrylic/N/A + Framed/Raw + Framed/White + Framed/Black)
      = 5 x 5 = 25 variants.

    SKU abbreviated format: LC-<handle>-<SIZE>-UF / FR-R / FR-W / FR-B / GL
    """
    variant_edges = (node.get("variants") or {}).get("edges") or []
    row.variant_count = len(variant_edges)

    seen_combos: set[str] = set()
    for edge in variant_edges:
        variant = edge.get("node") or {}
        sku = variant.get("sku") or ""
        options = {o["name"]: o["value"] for o in (variant.get("selectedOptions") or [])}
        size = options.get("Size", "")
        vtype = options.get("Type", "")
        colour = options.get("Colour", options.get("Color", ""))

        # Normalise: treat N/A colour as absent for the combo key
        colour_norm = colour if colour and colour != "N/A" else ""
        combo = f"{size}/{vtype}"
        if colour_norm:
            combo += f"/{colour_norm}"
        seen_combos.add(combo)

        if sku and not SKU_PATTERN.match(sku):
            display = f"{size}/{vtype}" + (f"/{colour}" if colour else "")
            row.sku_violations.append(f"{sku!r} (variant: {display})")

    # Expected combos -- Colour=N/A variants use the no-colour form
    expected: set[str] = set()
    for size in CANONICAL_SIZES:
        expected.add(f"{size}/Unframed")   # Colour N/A -- omit from key
        expected.add(f"{size}/Acrylic")    # Colour N/A -- omit from key
        for colour in ("Raw", "White", "Black"):
            expected.add(f"{size}/Framed/{colour}")

    missing = sorted(expected - seen_combos)
    row.missing_variant_combos = missing


def _check_extra_keys(
    mf_map: dict[tuple[str, str], dict],
    schema_keys: set[tuple[str, str]],
    row: ProductCoverageRow,
) -> None:
    """Flag metafield keys present on the product but not in the canonical schema."""
    for ns_key in mf_map:
        if ns_key not in schema_keys:
            row.extra_keys.append(ns_key)


def analyse_product(node: dict) -> ProductCoverageRow:
    """Produce a ProductCoverageRow for one Shopify product node."""
    product_id = node.get("id", "")
    handle = node.get("handle", "")
    title = node.get("title", "")

    row = ProductCoverageRow(
        product_id=product_id,
        handle=handle,
        title=title,
    )

    mf_map = _metafield_map(node)
    schema_keys: set[tuple[str, str]] = set()

    for ns, key, tier in SCHEMA_FIELDS:
        schema_keys.add((ns, key))
        mf = mf_map.get((ns, key))
        status = _classify_field(ns, key, tier, mf)
        row.fields[(ns, key)] = status

    _check_extra_keys(mf_map, schema_keys, row)
    _check_seo(node, row)
    _check_variants(node, row)

    # Featured image alt text
    fi = node.get("featuredImage") or {}
    row.featured_image_alt = (fi.get("altText") or "").strip() or None

    # Tags
    row.tags = list(node.get("tags") or [])
    row.has_limited_edition_tag = any("limited" in t.lower() for t in row.tags)

    # LR sync_at convenience field
    lr_mf = mf_map.get(("custom", "lr_sync_at"))
    if lr_mf:
        row.lr_sync_at = lr_mf.get("value")

    return row


# ---------------------------------------------------------------------------
# Inconsistency detection across the full product set
# ---------------------------------------------------------------------------

INCONSISTENCY_CLASS_LABELS = {
    "paper_type_values": "Paper type values (constant tier -- should be uniform)",
    "print_technique_values": "Print technique values (constant tier -- should be uniform)",
    "seo_pattern_violations": "SEO pattern violations (title/description format)",
    "extra_metafield_keys": "Unknown/extra metafield keys (not in canonical schema)",
    "sku_pattern_violations": "SKU pattern violations",
    "missing_featured_image_alt": "Products missing featured image alt text",
    "missing_variant_combos": "Products with missing variant combinations",
    "lr_sync_never": "Products never LR-synced (lr_sync_at empty)",
}


def detect_cross_product_inconsistencies(rows: list[ProductCoverageRow]) -> dict[str, list[str]]:
    """Find inconsistency classes that span multiple products.

    Returns a dict of class_label -> [description string per affected product].
    """
    result: dict[str, list[str]] = {k: [] for k in INCONSISTENCY_CLASS_LABELS}

    # Collect all paper_type values to detect drift
    paper_type_values: dict[str, list[str]] = {}
    print_technique_values: dict[str, list[str]] = {}

    for row in rows:
        # SEO pattern
        if row.seo_issues:
            result["seo_pattern_violations"].append(
                f"{row.handle}: {'; '.join(row.seo_issues)}"
            )

        # Extra keys
        for ns, key in row.extra_keys:
            result["extra_metafield_keys"].append(f"{row.handle}: {ns}.{key}")

        # SKU violations
        for violation in row.sku_violations:
            result["sku_pattern_violations"].append(f"{row.handle}: {violation}")

        # Featured image alt
        if not row.featured_image_alt:
            result["missing_featured_image_alt"].append(row.handle)

        # Variant completeness
        if row.missing_variant_combos:
            combos_str = ", ".join(row.missing_variant_combos[:5])
            if len(row.missing_variant_combos) > 5:
                combos_str += f" (+{len(row.missing_variant_combos) - 5} more)"
            result["missing_variant_combos"].append(f"{row.handle}: missing {combos_str}")

        # LR sync
        if not row.lr_sync_at:
            result["lr_sync_never"].append(row.handle)

        # Collect values for cross-product uniformity check
        pt_field = row.fields.get(("custom", "paper_type"))
        if pt_field and pt_field.value:
            paper_type_values.setdefault(pt_field.value.strip(), []).append(row.handle)

        ptech_field = row.fields.get(("custom", "print_technique"))
        if ptech_field and ptech_field.value:
            print_technique_values.setdefault(ptech_field.value.strip(), []).append(row.handle)

    # Paper type uniformity: flag if more than one distinct value exists
    if len(paper_type_values) > 1:
        for val, handles in paper_type_values.items():
            result["paper_type_values"].append(f"{val!r}: {len(handles)} products")

    # Print technique uniformity
    if len(print_technique_values) > 1:
        for val, handles in print_technique_values.items():
            result["print_technique_values"].append(f"{val!r}: {len(handles)} products")

    return result


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_coverage_report(report: CoverageReport) -> str:
    """Render the coverage audit report as markdown."""
    lines: list[str] = []

    lines.append("# LC Product Metadata Coverage + Consistency Audit")
    lines.append("")
    lines.append(f"**Run date:** {report.run_date}")
    lines.append(f"**Trigger:** {report.trigger}")
    lines.append(f"**Products scanned:** {report.products_scanned}")
    if report.products_with_errors:
        lines.append(f"**Products with errors:** {report.products_with_errors}")
    lines.append("")

    # Summary table
    total_fields = sum(r.schema_field_count for r in report.rows)
    total_present = sum(r.present_count for r in report.rows)
    total_empty = sum(r.empty_count for r in report.rows)
    total_nc = sum(r.non_conforming_count for r in report.rows)
    pct_present = (total_present / total_fields * 100) if total_fields else 0

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Schema fields per product: {len(SCHEMA_FIELDS)}")
    lines.append(f"- Total field assessments: {total_fields}")
    lines.append(f"- Present: {total_present} ({pct_present:.1f}%)")
    lines.append(f"- Empty: {total_empty}")
    lines.append(f"- Non-conforming: {total_nc}")
    lines.append("")

    # Inconsistency summary
    lines.append("## Inconsistency classes")
    lines.append("")
    lines.append("These classes surface format-level issues, cross-product drift, and unknown fields.")
    lines.append("")
    any_inconsistency = False
    for class_key, label in INCONSISTENCY_CLASS_LABELS.items():
        items = report.inconsistency_summary.get(class_key) or []
        if items:
            any_inconsistency = True
            lines.append(f"### {label}")
            lines.append("")
            for item in items[:20]:
                lines.append(f"- {item}")
            if len(items) > 20:
                lines.append(f"- ... and {len(items) - 20} more")
            lines.append("")
    if not any_inconsistency:
        lines.append("No cross-product inconsistencies detected.")
        lines.append("")

    # Per-product matrix
    lines.append("## Per-product matrix")
    lines.append("")
    lines.append(
        "| Handle | Present | Empty | Non-conform | Extra keys | Variants | SEO issues | Featured alt |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")

    for row in report.rows:
        extra_k = len(row.extra_keys)
        missing_v = len(row.missing_variant_combos)
        seo_ok = "OK" if not row.seo_issues else f"{len(row.seo_issues)} issue(s)"
        featured_alt = "yes" if row.featured_image_alt else "MISSING"
        lines.append(
            f"| {row.handle} "
            f"| {row.present_count} "
            f"| {row.empty_count} "
            f"| {row.non_conforming_count} "
            f"| {extra_k} "
            f"| {missing_v} missing "
            f"| {seo_ok} "
            f"| {featured_alt} |"
        )
    lines.append("")

    # Detailed non-conforming field notes
    nc_rows = [r for r in report.rows if r.non_conforming_count > 0]
    if nc_rows:
        lines.append("## Non-conforming field detail")
        lines.append("")
        for row in nc_rows:
            nc_fields = [f for f in row.fields.values() if f.status == STATUS_NON_CONFORMING]
            if nc_fields:
                lines.append(f"### {row.handle}")
                lines.append("")
                for f in nc_fields:
                    note = f.note or ""
                    lines.append(f"- `{f.namespace}.{f.key}` ({f.tier}): {note}")
                lines.append("")

    # Extra key detail (schema unknowns)
    extra_key_rows = [r for r in report.rows if r.extra_keys]
    if extra_key_rows:
        lines.append("## Unknown/extra metafield keys")
        lines.append("")
        lines.append("Keys found on products that are NOT in the canonical schema.")
        lines.append("")
        for row in extra_key_rows:
            keys_str = ", ".join(f"{ns}.{k}" for ns, k in sorted(row.extra_keys))
            lines.append(f"- **{row.handle}**: {keys_str}")
        lines.append("")

    if report.errors:
        lines.append("## Errors")
        lines.append("")
        for err in report.errors:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_coverage_audit(
    limit: int | None = None,
    handles: list[str] | None = None,
    output_path: str | None = None,
    dry_run: bool = False,
    gql_fn: Any = None,
) -> CoverageReport:
    """Run the store-wide coverage audit.

    Args:
        limit: Max products to fetch (None = all; use a small number for sampling).
        handles: If given, filter to these product handles after fetching.
        output_path: Where to write the markdown report (None = default path).
        dry_run: If True, do not write the report file.
        gql_fn: Optional GraphQL callable override (for testing).

    Returns:
        CoverageReport with rows, inconsistency summary, and errors.
    """
    from datetime import date, datetime, timezone

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    trigger_parts = ["coverage-audit"]
    if limit is not None:
        trigger_parts.append(f"limit={limit}")
    if handles:
        trigger_parts.append(f"handles={','.join(handles)}")
    trigger = " ".join(trigger_parts)

    logger.info("Coverage audit starting: limit=%s handles=%s", limit, handles)

    products: list[dict] = []
    errors: list[str] = []

    try:
        products = page_all_products(limit=limit, gql_fn=gql_fn)
    except Exception as exc:
        errors.append(f"Failed to fetch products from Shopify: {exc}")
        return CoverageReport(
            run_date=run_date,
            trigger=trigger,
            products_scanned=0,
            products_with_errors=0,
            errors=errors,
        )

    # Filter by handle if requested
    if handles:
        handle_set = set(handles)
        products = [p for p in products if p.get("handle") in handle_set]

    rows: list[ProductCoverageRow] = []
    error_count = 0

    for node in products:
        try:
            row = analyse_product(node)
            rows.append(row)
        except Exception as exc:
            handle = node.get("handle", "unknown")
            errors.append(f"{handle}: analysis error -- {exc}")
            error_count += 1

    inconsistency_summary = detect_cross_product_inconsistencies(rows)

    report = CoverageReport(
        run_date=run_date,
        trigger=trigger,
        products_scanned=len(rows),
        products_with_errors=error_count,
        rows=rows,
        errors=errors,
        inconsistency_summary=inconsistency_summary,
    )

    if not dry_run:
        _write_coverage_report(report, output_path)

    return report


def _write_coverage_report(report: CoverageReport, output_path: str | None) -> str:
    """Write the markdown coverage report and return the path."""
    from datetime import date
    from pathlib import Path

    if output_path:
        path = Path(output_path).expanduser()
    else:
        report_root = Path.home() / "Claude/cowork/brand-voice/facts-library/_reconciliation"
        year_dir = report_root / str(date.today().year)
        year_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        path = year_dir / f"coverage-audit-{today}.md"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_coverage_report(report), encoding="utf-8")
    logger.info("Coverage report written to %s", path)
    return str(path)
