"""A live value that merely stops earlier is not Rule 0 exposure (LOS7-1586).

The LOS7-1401/1402 slop remediation trimmed trailing series boilerplate off live
subject_description. Exact-equality comparison then flagged all 51 trimmed
products as R0-live on 2026-07-15 — a ~90% false-positive spike at the very
moment the live site had got safer. R0-live means "live carries a claim the
library does not back"; a strict prefix asserts nothing new.

Prefix only, never general substring (Brett's call 2026-07-20): substring would
let a library sentence carrying a negation clear a live claim contradicting it.
"""

from __future__ import annotations

from lc_facts_reconcile.diff import PlaneData, _live_is_trim_of_library, compute_disagreements


LIB_TIN_CITY = (
    "Sand drifts between the corrugated-iron shacks at the centre of Tin City, "
    "banking against the walls in smooth curves. Part of the Tin City series."
)
LIVE_TIN_CITY = (
    "Sand drifts between the corrugated-iron shacks at the centre of Tin City, "
    "banking against the walls in smooth curves."
)


class TestTrimDetection:
    def test_real_trimmed_boilerplate_is_a_trim(self):
        assert _live_is_trim_of_library(LIVE_TIN_CITY, LIB_TIN_CITY) is True

    def test_identical_values_are_not_a_trim(self):
        """Equality is handled by _values_agree; a trim must be strictly shorter."""
        assert _live_is_trim_of_library(LIB_TIN_CITY, LIB_TIN_CITY) is False

    def test_live_adding_text_is_not_a_trim(self):
        """The appin-motel case: live inserts 'titled as a project conceit but'."""
        lib = "The Appin Motel photographed at night, part of the 2018 series."
        live = "The Appin Motel photographed at night, titled as a conceit, part of the 2018 series."
        assert _live_is_trim_of_library(live, lib) is False

    def test_divergent_text_is_not_a_trim(self):
        lib = "A purifier vessel at the former Bathurst Gasworks, streaked with grime."
        live = "The roof of the purifier shed at the Bathurst Gasworks, seen from above."
        assert _live_is_trim_of_library(live, lib) is False

    def test_midword_truncation_is_NOT_cleared(self):
        """'ran until 199' must not be excused against 'ran until 1990' — the
        boundary check is what stops a truncated number reading as a trim."""
        lib = "The coal-fired station was commissioned in 1926 and ran until 1990."
        live = "The coal-fired station was commissioned in 1926 and ran until 199"
        assert _live_is_trim_of_library(live, lib) is False

    def test_negation_is_not_cleared_because_substring_is_not_used(self):
        """The reason prefix-only was chosen. 'did not close in 1990' CONTAINS
        'close in 1990', so a substring rule would clear a live claim that
        directly contradicts the library. A prefix rule cannot."""
        lib = "The station did not close in 1990; generation continued until 1994."
        live = "close in 1990"
        assert _live_is_trim_of_library(live, lib) is False

    def test_short_stub_is_not_cleared(self):
        """A near-empty live value is a missing/stub metafield, not a deliberate trim."""
        lib = "The Terminus Hotel's beer garden has grown over so thoroughly it could be mistaken for bushland."
        assert _live_is_trim_of_library("The", lib) is False

    def test_empty_live_is_not_cleared(self):
        assert _live_is_trim_of_library("", "Some library text that is long enough.") is False


class TestGradingEndToEnd:
    def _grade(self, live: str, library: str) -> list[str]:
        key = ("product.tin-city-city-centre", "subject_description")
        lib_plane = PlaneData(); lib_plane.values[key] = library
        sho_plane = PlaneData(); sho_plane.values[key] = live
        ds = compute_disagreements(handle="tin-city", series="Tin City",
                                   library=lib_plane, shopify=sho_plane)
        return [d.severity for d in ds]

    def test_trimmed_live_no_longer_grades_r0_live(self):
        assert self._grade(LIVE_TIN_CITY, LIB_TIN_CITY) == []

    def test_live_adding_a_claim_still_grades_r0_live(self):
        live = LIB_TIN_CITY + " The shacks were built by fishermen in the 1930s."
        assert "R0-live" in self._grade(live, LIB_TIN_CITY)

    def test_divergent_live_still_grades_r0_live(self):
        assert "R0-live" in self._grade(
            "An entirely different description of somewhere else altogether.",
            LIB_TIN_CITY,
        )
