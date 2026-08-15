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
    """Comparable data from one input plane, keyed by (surface, field).

    A source may state the same key more than once and mean two different
    things by it — ashio-copper-mine's research file carries one `| Location |`
    row for the Tsudō dressing plant Brett photographed and another for the
    wider Ashio mine, each separately sourced. `values` holds the first stated
    value as the display primary; `alternates` holds EVERY stated value in
    source order whenever there is more than one (LOS7-2098).

    Read candidates through `candidates()`, never `values` directly, anywhere a
    claim is being tested for backing: agreement with any one of them is
    agreement with the library. Picking a single winner first-or-last is
    arbitrary either way, and picking wrong reports a backed live claim as
    Rule 0 exposure on the strength of a row the parser happened to discard.
    """
    values: dict[tuple[str, str], str] = field(default_factory=dict)
    alternates: dict[tuple[str, str], list[str]] = field(default_factory=dict)

    def get(self, surface: str, field_name: str) -> str | None:
        return self.values.get((surface, field_name))

    def candidates(self, surface: str, field_name: str) -> list[str]:
        """Every value this plane states for the key, in source order."""
        alts = self.alternates.get((surface, field_name))
        if alts:
            return list(alts)
        val = self.values.get((surface, field_name))
        return [val] if val is not None else []

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

        lib_candidates = library.candidates(surface, field_name)

        d = _classify(
            handle, series, surface, field_name, lib_val, app_val, sho_val, cap_val,
            lib_candidates,
        )
        if d:
            results.append(d)

        # A caption conflict and a live Rule-0 exposure are DIFFERENT findings
        # needing different actions, and a row can legitimately be both. Emit the
        # caption conflict alongside, never instead of, the live grade.
        #
        # This matters: when the captions plane was repaired (LOS7-1587) the
        # original precedence — caption-conflict tested first, early return —
        # would have reclassified 102 of the 162 live R0-live rows into
        # caption-conflict. The headline would have fallen 162 -> ~60 and read as
        # a large improvement while actually hiding 63% of live Rule-0 exposure
        # behind a quieter grade. Masking live exposure is exactly the
        # false-green failure this engine exists to prevent.
        if (
            d is not None
            and d.severity != "caption-conflict"
            and cap_val is not None
            and lib_val is not None
            and not _agrees_with_any(cap_val, lib_candidates)
        ):
            results.append(
                Disagreement(
                    severity="caption-conflict",
                    series=series,
                    handle=handle,
                    surface=surface,
                    field=field_name,
                    library_says=_render_library_says(lib_candidates, lib_val),
                    applied_says=app_val,
                    shopify_says=sho_val,
                    caption_says=cap_val,
                    resolution_rule=_RESOLUTION_RULES["caption-conflict"],
                    recommended_action=_RECOMMENDED_ACTIONS["caption-conflict"],
                )
            )

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
    lib_candidates: list[str] | None = None,
) -> Disagreement | None:
    """Return a Disagreement or None for a single (surface, field) tuple.

    Only compares when the library has an entry for this surface/field key.
    Shopify fields with no library counterpart are skipped — backing requires
    a matching key. Semantic backing-detection (does Shopify prose match any
    library fact?) is a v2 feature.

    lib_candidates is every value the library states for this key (LOS7-2098).
    Backing is agreement with ANY of them, because a key stated twice is two
    separately sourced claims, not one claim and one mistake. Defaults to
    [lib_val] so a caller comparing a single value behaves exactly as before.
    """
    severity: str | None = None

    if lib_val is None and cap_val is None:
        return None

    candidates = list(lib_candidates) if lib_candidates else (
        [lib_val] if lib_val is not None else []
    )

    # LIVE EXPOSURE IS TESTED FIRST AND ALWAYS WINS THE PRIMARY GRADE.
    # Caption-conflict used to be tested first with an early return, which was
    # harmless only while the captions plane was silently empty. Once it was
    # repaired (LOS7-1587) that ordering would have demoted 102 of 162 live
    # R0-live rows to caption-conflict. A wrong fact on the public site outranks
    # an internal caption/library disagreement, so R0-live/drift is graded first;
    # compute_disagreements appends any caption-conflict as a SEPARATE finding.
    if (
        sho_val is not None
        and lib_val is not None
        and not _agrees_with_any(sho_val, candidates)
        # A live value that is a library value with a trailing tail removed
        # states nothing the library does not back, so it is not R0-live.
        and not any(_live_is_trim_of_library(sho_val, c) for c in candidates)
    ):
        if app_val is not None and _values_agree(app_val, sho_val):
            severity = "drift"
        else:
            severity = "R0-live"
    elif cap_val is not None and lib_val is not None and not _agrees_with_any(cap_val, candidates):
        severity = "caption-conflict"
    elif (
        app_val is not None
        and lib_val is not None
        and not _agrees_with_any(app_val, candidates)
        and sho_val is None
    ):
        severity = "R0-pending"

    if severity is None:
        return None

    return Disagreement(
        severity=severity,
        series=series,
        handle=handle,
        surface=surface,
        field=field_name,
        library_says=_render_library_says(candidates, lib_val),
        applied_says=app_val,
        shopify_says=sho_val,
        caption_says=cap_val,
        resolution_rule=_RESOLUTION_RULES[severity],
        recommended_action=_RECOMMENDED_ACTIONS[severity],
    )


def _values_agree(a: str, b: str) -> bool:
    """Normalised comparison — ignores dash variants, case, extra whitespace."""
    return _normalise(a) == _normalise(b)


def _agrees_with_any(value: str, candidates: list[str]) -> bool:
    """True when the value matches any one of the library's stated values."""
    return any(_values_agree(value, c) for c in candidates)


# Separator between library candidates in a finding's library_says. report.py's
# _cell escapes bare pipes to &#124; so this survives the markdown table.
_CANDIDATE_JOIN = "  ||  "


def _render_library_says(candidates: list[str], lib_val: str | None) -> str:
    """Show the human EVERY value the library states, not just the primary.

    Whoever adjudicates a flag on a key the library states twice needs both
    rows in front of them — seeing one of two sourced claims is how a backed
    live value gets read as unbacked.
    """
    if len(candidates) > 1:
        return _CANDIDATE_JOIN.join(candidates)
    return lib_val or (candidates[0] if candidates else "(no entry)")


# A live value shorter than this is treated as a stub, not a deliberate trim, and
# is never cleared by the prefix rule below.
_MIN_TRIM_PREFIX_CHARS = 20


def _live_is_trim_of_library(live: str, library: str) -> bool:
    """True when the live value is the library value with a trailing tail removed.

    R0-live means "live carries a claim the library does not back". A live value
    that is a strict prefix of the library value asserts nothing new, so it is
    not Rule 0 exposure — it is the same statement, stopping earlier.

    This exists because the LOS7-1401/1402 slop remediation trimmed trailing
    series boilerplate off live subject_description ("... Part of the Tin City
    series.", "... It is one of 101 New South Wales roadside motels Brett Patman
    photographed across 2018."). Comparing with exact equality then flagged all
    51 trimmed products as R0-live on 2026-07-15 — a 90%-false-positive spike
    while the site had in fact got safer (LOS7-1586). Verified against live
    Shopify: of 21 rows sampled, 19 were strict prefixes and 0 added any text.

    PREFIX ONLY, never general substring containment (Brett's call, 2026-07-20).
    Substring would let a library sentence carrying a negation clear a live claim
    that contradicts it — "did not close in 1990" contains "close in 1990".

    The tail must break at a word boundary, so a mid-word truncation
    ("... ran until 199" against "... ran until 1990") is still graded.
    """
    nl, nb = _normalise(live), _normalise(library)
    if not nl or len(nl) < _MIN_TRIM_PREFIX_CHARS:
        return False
    if nl == nb or not nb.startswith(nl):
        return False
    tail = nb[len(nl):]
    # Boundary check: the library must continue with punctuation or a space, not
    # with more of the word the live value stopped inside.
    return not tail[:1].isalnum()


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
