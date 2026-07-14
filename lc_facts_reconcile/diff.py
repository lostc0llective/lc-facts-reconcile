"""Core disagreement detection engine.

Four severity grades (spec 2026-05-26):
  R0-live     — live Shopify surface has a claim the library does not back.
  R0-pending  — applied record has a claim the library doesn't back, not confirmed live.
  drift       — library is behind a known correction (live is correct, library stale).
  caption-conflict — captions store and research file disagree. Caption wins.
  internal    — two facts library files disagree with each other.
  stale-claim — research file carries a claim primary sourcing has superseded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Disagreement:
    severity: str
    series: str
    handle: str
    surface: str
    field: str
    library_says: str
    applied_says: str | None
    shopify_says: str | None
    caption_says: str | None
    resolution_rule: str
    recommended_action: str


@dataclass
class PlaneData:
    """Comparable data from one input plane, keyed by (surface, field)."""
    values: dict[tuple[str, str], str] = field(default_factory=dict)

    def get(self, surface: str, field_name: str) -> str | None:
        return self.values.get((surface, field_name))

    def keys(self) -> set[tuple[str, str]]:
        return set(self.values.keys())


@dataclass
class OpenClaim:
    handle: str
    surface: str
    claim_text: str
    source_file: str


_RESOLUTION_RULES = {
    "R0-live": "No claim outside library — strip from live or evidence-research-then-add to library.",
    "R0-pending": "Applied record not yet confirmed live. Verify live surface then escalate to R0-live or close.",
    "drift": "Live surface is correct, library is stale. Back-propagate the correction to the library.",
    "caption-conflict": "Caption wins per standing rule (2026-05-19). Patch library to match caption.",
    "internal": "Two library files disagree. Surface to Brett — no auto-resolution.",
    "stale-claim": "Supersede with the newer cite. Remove or update the stale claim.",
}

_RECOMMENDED_ACTIONS = {
    "R0-live": "Run Agent 1 to source evidence for the live claim, or run an apply sprint to strip it.",
    "R0-pending": "Verify the live surface via Shopify Admin, then reclassify as R0-live or close.",
    "drift": "Add a library-update sprint task: back-propagate the correction from the applied record.",
    "caption-conflict": "Update the library research file to match the IPTC caption value.",
    "internal": "Brett to choose canonical version; update the non-canonical file.",
    "stale-claim": "Update the research file to reference the newer source.",
}


def compute_disagreements(
    handle: str,
    series: str,
    library: PlaneData,
    applied: PlaneData | None = None,
    shopify: PlaneData | None = None,
    captions: PlaneData | None = None,
    internal_conflicts: list[Disagreement] | None = None,
) -> list[Disagreement]:
    """Compare all planes and return a list of Disagreement findings."""
    results: list[Disagreement] = []

    if internal_conflicts:
        results.extend(internal_conflicts)

    all_keys: set[tuple[str, str]] = set(library.keys())
    if applied:
        all_keys |= applied.keys()
    if shopify:
        all_keys |= shopify.keys()
    if captions:
        all_keys |= captions.keys()

    for surface, field_name in sorted(all_keys):
        lib_val = library.get(surface, field_name)
        app_val = applied.get(surface, field_name) if applied else None
        sho_val = shopify.get(surface, field_name) if shopify else None
        cap_val = captions.get(surface, field_name) if captions else None

        d = _classify(handle, series, surface, field_name, lib_val, app_val, sho_val, cap_val)
        if d:
            results.append(d)

    return results


def _classify(
    handle: str,
    series: str,
    surface: str,
    field_name: str,
    lib_val: str | None,
    app_val: str | None,
    sho_val: str | None,
    cap_val: str | None,
) -> Disagreement | None:
    """Return a Disagreement or None for a single (surface, field) tuple.

    Only compares when the library has an entry for this surface/field key.
    Shopify fields with no library counterpart are skipped — backing requires
    a matching key. Semantic backing-detection (does Shopify prose match any
    library fact?) is a v2 feature.
    """
    severity: str | None = None

    if lib_val is None and cap_val is None:
        return None

    if cap_val is not None and lib_val is not None and not _values_agree(cap_val, lib_val):
        severity = "caption-conflict"
    elif sho_val is not None and lib_val is not None and not _values_agree(sho_val, lib_val):
        if app_val is not None and _values_agree(app_val, sho_val):
            severity = "drift"
        else:
            severity = "R0-live"
    elif app_val is not None and lib_val is not None and not _values_agree(app_val, lib_val) and sho_val is None:
        severity = "R0-pending"

    if severity is None:
        return None

    return Disagreement(
        severity=severity,
        series=series,
        handle=handle,
        surface=surface,
        field=field_name,
        library_says=lib_val or "(no entry)",
        applied_says=app_val,
        shopify_says=sho_val,
        caption_says=cap_val,
        resolution_rule=_RESOLUTION_RULES[severity],
        recommended_action=_RECOMMENDED_ACTIONS[severity],
    )


def _values_agree(a: str, b: str) -> bool:
    """Normalised comparison — ignores dash variants, case, extra whitespace."""
    return _normalise(a) == _normalise(b)


# Any whole "[Sx ...]" citation bracket, not just a bare numeric id: covers
# "[S1]", non-numeric ids ("[S-GPS]", "[S-Geo]"), and compound/multi-source
# refs with page numbers ("[S1; S2 p. 8-9]"). Mirrors the JS sibling's
# CITATION_BRACKET in prototyping-workbench/lib/metadata-generation/facts-pack.mjs
# -- confirmed live 2026-07-14 that the narrower \[S\d+\] pattern missed both
# of these variants (mckillops-bridge's "[S1; S2 p. 8-9]", mount-russell-grain-
# silo's "[S-GPS][S-Geo]"), leaving them as false-positive R0-live findings.
_CITATION_TAG_RE = re.compile(r"\[S[-\w]+[^\]]*\]")


def _normalise(s: str) -> str:
    # Strip library-only citation tags ([S3], [S12][S14]) and markdown
    # bold/italic/code markers before comparing \u2014 the library's raw markdown
    # carries these, Shopify's plain-text metafield values never do, and
    # comparing them unstripped produced false-positive R0-live findings on
    # every cited fact in the library (LOS7-1382, 2026-07-14).
    s = _CITATION_TAG_RE.sub("", s)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    s = s.lower().strip()
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = " ".join(s.split())
    # Removing a tag/marker can leave a dangling space before the punctuation
    # that followed it ("2040 [S12]; on land" -> "2040 ; on land" once the tag
    # is gone) -- collapse it. Confirmed live 2026-07-14: 4 of 8 residual
    # R0-live "location" rows post-fix were this exact artifact
    # (abandoned-bakery, abandoned-shoe-factory, terminus-hotel,
    # white-bay-power-station), not a real content disagreement.
    s = re.sub(r"\s+([,;:.!?])", r"\1", s)
    s = s.rstrip(".").strip()
    return s
