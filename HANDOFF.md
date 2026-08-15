# lc-facts-reconcile — HANDOFF

## 2026-08-15 — LOS7-2097: 87 of the 90 R0-live were stale drafts, because supersession asked the wrong question

**Built:** `38b871b`, pushed direct to `main`. `lc_facts_reconcile/planes/library.py` (`_superseded`) + `tests/test_library_applied_supersede.py`. 132 tests pass.

**This closes the open thread from the 2026-08-09 entry below.** That session correctly established exit 1 is a findings signal and the 90 were the real standing count. It did not ask whether the 90 were *right*. They were not: 87 were live copy nobody disputes, measured against May enrichment drafts that were never promoted.

**The defect.** LOS7-1929 already knew an enrichment draft is Layer 3 pre-audit staging and skipped one once an applied record covered it — keyed on the exact `(product.<handle>, field)`. The absence of a record was then read as "the draft is still authoritative". It does not mean that. A factual audit covers a SERIES and adjudicates every product in it: the ones it finds defective get an applied record, the ones it leaves alone were examined and found correct. Both outcomes date the draft. Same absence-is-not-a-negative class as LOS7-2078.

**Measured, not assumed:** 87 of 90 rows were product-level in series the LOS7-1864/1870 audit covered; the other 3 are `series.metaobject` and unaffected. `elrington-colliery` alone was 53 of the 90 — that apply rewrote 8 products and examined the other ~45, and each of those ~45 stale drafts graded as unbacked live exposure.

**Kept deliberately narrow.** Still per FIELD (an audit that rewrote `subject_description` says nothing about a `print_story` draft). `applied_plane=None` still suppresses nothing. And `_live_is_trim_of_library` stays PREFIX-only — `mckillops-bridge` drops a locality mid-string and is still flagged, because widening to substring is Brett's explicit 2026-07-20 ruling against (a library sentence carrying a negation could clear a live claim contradicting it). One existing test pinned the narrow key and was corrected rather than weakened; its real intent (a series no audit has touched still gets its drafts absorbed) is preserved by giving the applied plane a different FIELD.

**Verified end-to-end, and the guard still bites.** Full scheduled run after the change: 3 R0-live from the same 122 series / 1,961 products, so coverage did not shrink. `mount-russell-grain-silo` still fires and is GENUINE — its live metaobject claims "Inverell Shire, Northern Tablelands" where the research file says North West Slopes and never states the LGA (checked the whole file, not just the At-a-glance table: "Inverell Shire" appears 7 times but only as *Council*, in custodian context). That finding is the proof the fix did not blind the detector.

**Brett-action: one decision, in LOS7-2098.** mount-russell's live location either gets its LGA/region sourced into the research file with citations, or the unsourced terms come off the live metaobject. Both are almost certainly true facts, which is exactly the trap — Rule 0 makes the library the ceiling, not plausibility.

**Also logged in LOS7-2098, not fixed here:** `ashio-copper-mine` is a FALSE positive hiding a real parser bug — its research file carries two `| Location |` rows and live matches the `[S1]` one verbatim, but `_parse_at_a_glance` builds a plain dict so the second row silently overwrites the first. Any duplicated At-a-glance key discards a sourced row. The fix needs a small data-model change (a key holding candidate values, `_classify` agreeing if live matches ANY) rather than an arbitrary first-or-last, so it was not rushed into the same session as a supersession change to the Rule-0 guard.

## 2026-08-09 — LOS7-2004: the daily "failure" was two healthy features and a monitor watching the wrong artefact

**The reported defect does not exist. The reconciler has been running correctly every morning.** Both premises in the issue were false, and both were confirmed false by reproducing the real scheduled run (not by reading code alone):

- **"Exits 1 daily"** — exit 1 is a designed FINDINGS signal, not a failure. `cli.py` returns a tri-state: `0` = no R0-live outstanding, `1` = R0-live outstanding, `3` = the run itself failed. There are 90 R0-live disagreements, so exit 1 is the correct and expected daily status. The wrapper's retry loop declining to retry it is also correct — there is nothing transient to retry.
- **"Has written no report since 2026-08-04"** — that is the LOS7-1857 dedup working exactly as designed. `write_report()` compares findings (report content minus the `**Run date:**` line) against the newest existing report and, when identical, returns that path instead of writing a churn duplicate. Findings have not changed since 08-04, so no new dated file. Reproduced live: a full run this session produced byte-identical findings and returned the 08-04 path.
- **The `LastExitStatus` flip-flop** (256 in the tidy sweep, 0 today) is a red herring: `launchctl print` showed `runs = 0, last exit code = (never exited)`. launchd resets `LastExitStatus` to 0 on reload/reboot, so a `0` there can mean "has not run since load", not "ran cleanly". It is not a usable health signal on its own.
- **The em-dash lead was a resolved historical issue, not the cause.** `shopify.py::_assert_header_safe()` documents it: on 2026-07-08 the em dash was in the **access token**, not in a Shopify field, and urllib encodes header values as latin-1. Those `.err` entries are dated **2026-07-02**, before the LOS7-1585 fix. `.env.tpl` no longer supplies `SHOPIFY_ACCESS_TOKEN`, auth falls through to App A client-credentials, and the error stopped — which is why `.err` has been silent since 07-31 and why the 08-01 disagreement count jumped (more products actually being scanned).
- **"Nothing caught it" was also false — and the opposite of the problem.** `automation-watchdog` HAS flagged `facts-reconcile` **STALE every day since 08-05** ("newest artefact 118.8h old, limit 26.0h"). It was crying wolf: it watched the dated-report glob, and since the LOS7-1857 dedup an unchanged-findings day legitimately writes no report. The same latent false positive sat in the reliability sweep (`sweep.py` flagged "Reconciler stalled" when `r0_latest_date == prev_r0_date`, i.e. whenever findings held steady for a week).

**What WAS real, and is fixed.** A report is an artefact of the FINDINGS; only a run heartbeat can answer "did it run":

- **Wrapper writes a RUN heartbeat** (`~/Claude/cowork/agents/logs/lc-facts-reconcile.heartbeat.json`) on every completed run: `finished_at`, `run_date`, `status`, `status_meaning`, `healthy` (exit 0/1 = healthy).
- **Wrapper now alerts on exit 3 and on any unexpected status.** Previously the ONLY alert fired when all three attempts died on *network* errors, so exit 3 (fail-closed: the run ran but its numbers mean nothing) reached nobody. Exit 1 deliberately does NOT alert — alerting on the normal daily state trains the alert to be ignored.
- **`ENABLE_NOTIFICATIONS=true` added to the launchd plist.** Without it `notify_actionable` console-echoes and returns 0, so even the pre-existing LOS7-1603 alert could never have reached Brett. Verified: ntfy topic resolves, both channels fire on exit 3 and 127, neither fires on exit 1.
- **`automation-watchdog` row repointed** from the report glob to the heartbeat, with a `healthy":false` content probe. Stale count went 3 -> 2; the row now reads `ok: facts-reconcile`.
- **`sweep.py` liveness rewritten** to read the heartbeat (48h tolerance). The `unchanged since the last sweep` false-positive clause is gone; report age survives only as a corroborating signal, and only when the heartbeat is also missing or unhealthy.
- **The daily log no longer lies.** The CLI now prints `^ REUSED: findings are unchanged...` when the dedup fires, and spells out what exit 1 means. Printing a path that was not written today with no further comment is precisely what cost this investigation. 3 new tests (`tests/test_report_reuse_signal.py`), suite 127 -> 131, all green.

**Done-when #2 from the issue ("a run writes a fresh dated report, and the exit code is 0") is rejected as premised on the bug that does not exist.** Forcing a fresh dated report would re-introduce exactly the churn LOS7-1857 removed, and exit 0 would require zero R0-live disagreements — a property of the catalogue's data, not something code can or should make true. Everything else in the issue is delivered.

**Verified live**, end to end: reloaded the plist and fired the real launchd job (`launchctl kickstart`). It ran against production Shopify, scanned 122 series / 1961 products, reused the 08-04 report, exited 1, wrote a correct heartbeat, and sent no alert.

**Found, not fixed:** the stale duplicate wrapper at `~/Claude/scheduled/launchd/scripts/lc-facts-reconcile-scheduled.sh` (flagged in the 2026-08-04 entry below) is still there and has now diverged further, since this session's changes landed only in the deployed `~/.claude/scripts/` copy that the plist actually points at. Also pre-existing and unrelated: `facts-library-reliability-sweep/test_cross_layer.py` fails one assertion (`respects the declared open-question allowlist`) — confirmed failing identically with `sweep.py` stashed, so not caused by this work. Both filed separately.

**Brett-actions** — none.

---

## 2026-08-04 — LOS7-1929: applied plane rewritten, rejoins the default; closes the LOS7-1912 diagnosis (commit `77b77d3`)

Picks up the "worth its own look" note at the bottom of the 2026-08-01 LOS7-1857 entry below: R0-live had jumped 104 -> 172 the day after LOS7-1870's 829-product apply. LOS7-1912 diagnosed it (root cause confirmed, not a revert); this issue is the fix.

**Root cause:** `library.py::_absorb_enrichment()` projects enrichment-drafts' `proposed_subject_description` into the library plane unconditionally. Enrichment-drafts are Layer 3 pre-audit staging — nothing regenerates them once a later factual audit corrects and applies different text straight to Shopify. `applied.py` was supposed to be the plane that catches exactly this ("this live value diverges from the library on purpose, per a logged correction"), but it was opt-out by default (LOS7-1587) because its free-form regex parser reliably produced garbage — confirmed again this session against both the archived tone-of-voice-rollout corpus (91 "entries", all junk, matching LOS7-1587's own finding) and the one hand-written sprint report since landed in the live `applied/` folder (same shape, same result). So with `applied` off, the reconciler had no way to tell "live changed on purpose" from "live drifted."

**Fix, both halves shipped (the issue's own recommended (a)+(b), not the (c) stopgap):**
- `applied.py` rewritten to parse ONLY the structured shape factual-audit applies actually write — one file per series, one `### \`product-handle\`` block per product with its own Before/After blockquote — globbing `cowork/brand-voice/{applied,audits/*/applied}/`. Anything that doesn't match the structured shape is skipped, never guessed at. Entries sort by `**Applied:**` date so the chronologically latest record wins a repeat key (`root.rglob()` order is filesystem-dependent, not chronological). The archived tone-of-voice-rollout root is no longer walked at all.
- `library.py::read_library()` takes an optional `applied_plane` (passed in by `runner.py`, computed per-series before the library read now instead of after); `_absorb_enrichment()` skips any (product, field) an applied record already covers.
- Default `--planes` (cli.py) and `run_reconciliation()`'s fallback (runner.py) both changed from `library,shopify` to `library,shopify,applied`. `captions` stays opt-in (unchanged, editorial call).

**Verified live**, not just in tests (127 pass, was 113): ran the real scheduled wrapper against production Shopify. **172 -> 90 R0-live**, which is BELOW the 104 pre-apply baseline — the same enrichment-draft-staleness bug was already producing 14 of the original 104 for corrections applied before 07-31 too, not just the reported 68-row spike (82 resolved total: 68 + 14). Zero new rows introduced (`comm -13` on the full before/after row set is empty). Spot-checked several resolved rows against their applied record's After text and live Shopify directly (`ashio-copper-mine-crusher`, `mv-cape-don-wharf`, the `awaba-colliery` 13-vs-15-vs-13 pattern across the 07-31/08-01/08-04 reports) — all genuine, all correctly explained by an applied correction matching live. Report: `cowork/brand-voice/facts-library/_reconciliation/2026/reconciliation-report-2026-08-04.md`, committed separately in the `brand-voice` repo (`6f29593`, unpushed per the LOS7-1520 commit-only convention).

**The issue's "immediate cleanup" step (fix option (c): mechanically refresh the 18 affected series' enrichment-draft JSONs) turned out unnecessary.** It was explicitly framed as a stopgap for if the code fix wasn't landing immediately. Since (a)+(b) shipped in this same session, the count already dropped via the read side (supersession) — no JSON files were edited. Worth doing as its own hygiene pass eventually (the drafts genuinely are stale at rest), but it's no longer load-bearing for the reconciler's accuracy, so left alone here.

**Found, not fixed, filed separately:** the deployed launchd wrapper (`~/.claude/scripts/lc-facts-reconcile-scheduled.sh`, the one the plist actually points at) has a stale duplicate at `~/Claude/scheduled/launchd/scripts/lc-facts-reconcile-scheduled.sh` — missing the LOS7-1603 retry logic and the LOS7-1520 auto-commit step entirely (still ends in a bare `exec`, pre-dating both). Ran the stale copy once for this session's live verification before noticing; harmless (same underlying CLI, just skipped the auto-commit, which I did by hand). Filed as its own Linear issue rather than fixed here — out of LOS7-1929's scope.

**Brett-actions** — none.

---

## 2026-08-01 — LOS7-1857: stopped daily churn on informationless reports (commit `cdac779`)

`write_report()` unconditionally created `reconciliation-report-YYYY-MM-DD.md` on every launchd run. Filed and premise-checked in `prototyping-workbench` first: measured 2026-07-21 through 2026-07-31, every report was exactly 44002 bytes and consecutive days differed by exactly one line (`**Run date:**`). Two committed files a day apart, zero information. **Decided source of the fix is here, not the downstream index** — the downstream `content/facts-library*.index.json` files in prototyping-workbench derive `reportDate` from the filename, so churn there is a symptom, not the defect.

**Fix:** `write_report()` now strips the run-date line and compares against the most recent existing report in the same year directory. If content matches, it returns the existing report's path instead of writing a new one — no new file, no new commit. `--delta` bypasses this (`skip_if_unchanged=False`) because it appends a section to the returned path after the fact, and appending to a reused historical file would corrupt it. An explicit `--output` always writes regardless.

4 new tests (`tests/test_report_dedup.py`), suite 109 -> 113, full suite green.

**Not touched:** dawn's `banned_terms.json` cross-repo write — LOS7-1857 premise-checked that separately and found it innocent (content-comparison guard already added 2026-06-11, `74ee6104`). That half of the issue was just a stale committed hash, fixed via a dawn PR, not a reconciler change.

**Aside, out of scope for LOS7-1857:** today's run (2026-08-01) shows R0-live jumping 104 -> 172 across several series (ansto-hifar, ashio-copper-mine, awaba-colliery and others) — a genuine content change, not churn, so the new dedup logic correctly did not suppress it. Worth its own look; not investigated here.

**Brett-actions** — NONE.

---

## 2026-07-14 (continued) : LOS7-1382 — third bug found + last 3 real disagreements resolved

Brett asked to resolve the 3 remaining genuine `location` disagreements (ashio-copper-mine, mckillops-bridge, mount-russell-grain-silo), leaving `the-woolshed` alone (confirmed by Brett: a general nature collection with no single location, permanently unresolvable, not a defect).

**Third citation-regex bug found while resolving these:** `_CITATION_TAG_RE` (`\[S\d+\]`) only matched purely-numeric ids. Missed `[S-GPS]`/`[S-Geo]` (non-numeric ids) and compound refs like `[S1; S2 p. 8-9]` -- both already in live use. Broadened to `\[S[-\w]+[^\]]*\]`, mirroring the JS sibling's `CITATION_BRACKET` in `prototyping-workbench/lib/metadata-generation/facts-pack.mjs`. Commit `72f6c02`, 2 new regression tests, 84/84 pass.

**Content resolutions (each verified live before/after):**
- **ashio-copper-mine** -- the research file had two "At a glance" sections (Tsudō Ore-Dressing Plant, the specific photographed subject, first; Ashio Copper Mine parent operation, wider context, second). The parser picks up the LAST such section as canonical, which was the broader "Ashio, Tochigi Prefecture" location -- but the live Shopify metaobject already correctly used the specific "Tsudō" location matching the actual photographed subject. Corrected the library's second table to match (both are already-sourced facts in the same file; no new claim invented, no Shopify write needed).
- **mckillops-bridge** -- Shopify's live value was a stub ("Deddick Valley, Australia"). Library had the fuller sourced detail. Pushed a concise version of the library's location text to the live metaobject (`gid://shopify/Metaobject/438040494246`) via `shopify store execute --allow-mutations`, then updated the library text to match exactly what's now live (both sides in sync).
- **mount-russell-grain-silo** -- Shopify already had richer regional detail ("Inverell Shire, Northern Tablelands") than the library's location field, but that detail was ALREADY sourced elsewhere in the same research file (the "Nearest centres" and "Traditional custodians" rows, [S1][S2][S4][S17], plus an explicit note at [S20] correcting Brett's own loose "central NSW" Facebook caption). Back-propagated it into the library's Location field (no new claim) and pushed the missing postcode ("NSW 2360") to the live metaobject (`gid://shopify/Metaobject/435918930086`) to match.

**Final live-verified state:** full catalogue re-run after all fixes: **108 R0-live** (was 170 at session start). 107 `subject_description` (separate, pre-existing, out-of-scope semantic-backing gap) + 1 `location` (`the-woolshed`, confirmed permanent/expected). Dashboard indexes resynced (`prototyping-workbench` commit `bced0318`) to reflect the corrected research files.

---

## 2026-07-14 : LOS7-1382 follow-up — live-verified, second bug found and fixed

Ran the fix from 2026-07-13 against live Shopify data (`op run --env-file=lost-collective-dawn/.env.tpl`, App A client-credentials, headless via SA token). Full catalogue: **170 -> 111 R0-live**, in two steps:

- First fix alone (citation-tag/markdown stripping) took 170 -> 115.
- Live-diffed 5 of the residual "location" rows directly against Shopify (bypassing the report's 80-char truncation) and found a second bug: removing a tag/marker can leave a dangling space before the punctuation that followed it ("2040 [S12]; on land" -> "2040 ; on land"), and `rstrip(".")` can expose a trailing space after stripping a trailing period. Fixed in commit `c3cdb41`: collapse whitespace before punctuation, strip trailing whitespace after the period-strip. Verified against all 4 affected handles (abandoned-bakery, abandoned-shoe-factory, terminus-hotel, white-bay-power-station) -- each now normalises identically to Shopify. 115 -> 111.

**Remaining 111 R0-live, broken down and verified, not just counted:**
- **107 `subject_description`** -- a separate, pre-existing category: library research prose vs. Shopify's visual photo captions. These were never meant to match verbatim (the tool's own docstring already calls this "semantic backing-detection... a v2 feature"). Out of scope for LOS7-1382; not touched.
- **4 `location`** -- individually verified as genuine content differences, not artifacts: `ashio-copper-mine` (Shopify names a different sub-locality), `mckillops-bridge` (Shopify has far less detail), `mount-russell-grain-silo` (Shopify has an extra regional descriptor), `the-woolshed` (a "(collection metafield)" editorial annotation in the library text -- a different noise category from citation brackets, a legitimate separate finding if Brett wants it cleaned up later).

Today's report at `_reconciliation/2026/reconciliation-report-2026-07-14.md` now reflects the corrected, live-verified state (regenerated for real, not dry-run).

**Next session priorities:** none outstanding for this fix. If the `the-woolshed`-style "(collection metafield)" annotation pattern recurs elsewhere, it's a distinct, smaller follow-up (not citation brackets) -- scope it separately rather than silently folding into `_normalise()`.

---

Last updated: 2026-07-27. No functional change since 2026-07-22 — the only intervening commits (`a666040` on 2026-07-26, and this one) are HANDOFF `Last updated` housekeeping raised by the daily workspace-hygiene scan, not reconciler work. The substantive state below is current as written. Prior note follows verbatim from 2026-07-22 (superseding the 2026-07-19 note below, kept for the history trail). Since 2026-07-19: LOS7-1585 (fail-closed exit-3 on a wholesale live-plane failure, commit `6ec0348`), LOS7-1587 (captions plane repaired + precedence fixed so live exposure is never demoted, commit `8241bb6`), LOS7-1586 (a strict-prefix live value is no longer graded R0-live, commit `8df28d1`), and LOS7-1588/1589 (the 6 remaining R0-live rows resolved data-side across `hotel-motel-101`, `jamison-hotel`, `bathurst-gasworks-purifier-shed-roof`; no reconciler code change) — full detail in the three "2026-07-20" sections below. Net effect: R0-live 56 → 0 on the affected series, suite 91 → 109 tests. 2026-07-19 note follows verbatim: Since 2026-07-14: `b1580a3` (LOS7-1520) made the scheduled wrapper auto-commit its reconciliation reports so nightly runs no longer leave the report file uncommitted; the other intervening commits (`c80efa8`, `72f6c02`, `04ac899`, `c3cdb41`, `56fc0ae`, `2ed33e9`) are the LOS7-1382 citation-tag/regex fixes and `location`-disagreement resolutions already recorded in the two sections at the top of this file. That 2026-07-14 work (see those sections): third citation-regex bug fixed, last 3 genuine `location` disagreements resolved, R0-live count 170 → 108. Intervening commit before that, since 2026-06-27: `fc939ee` (2026-07-07) was docs-only workspace-migration housekeeping (lc-master-context rename, rollout archive, Pairing header) — no functional change. Prior history: `502712a` ran the LOS7-628 store-wide product metadata coverage and consistency audit; `2766dbc` switched the Shopify auth path to a static Admin Token to bypass the client_credentials scope gap (the first functional change since 2026-06-13); `a156821` hardened `DEPLOYMENT.md` against the 2026-06-23 restoration issues (plist loss, pip-editable breakage, `read_metaobjects` scope failure); `9c747f0` and `fcf5f5d` were spec-pointer and HANDOFF housekeeping. Matcher widening (2026-05-31) remains the latest substantive matcher state. Earlier 2026-06-13 doc commits: `d85f1fc` added a repo `CLAUDE.md` and fixed a spec pointer (drift-audit str-07/agents-04); `9c14f59` updated `DEPLOYMENT.md` and this `HANDOFF.md` with session WIP notes (LOS7-517 git-hygiene cleanup).

---

## Built this session (2026-07-13 — LOS7-1382 citation-tag normalisation fix)

- **Root cause fixed**: `_normalise()` in `diff.py` compared raw library markdown (carrying `[S3]`-style citation tags and `**bold**` markers) against Shopify's plain-text metafield values with no stripping. Every cited fact registered as a mismatch — the 2026-07-14 reconciliation report had 170/170 rows graded R0-live, all differing only by trailing citation brackets.
- **Fix**: `_normalise()` now strips `[S\d+]` citation tags and markdown bold/italic/code markers before the existing case/whitespace/dash normalisation. Commit `616287d`.
- **Tests**: 3 new regression tests in `test_diff.py` (reproduces the exact wangi-power-station false positive, a multi-tag/bold case, and confirms a real disagreement under a citation tag still surfaces). 78/78 tests pass.
- **Not verified live**: a full re-run against Shopify to confirm the R0-live count drops from 170 requires this repo's Shopify credentials via `lost-collective-dawn/.env.tpl` — that shared token is the one flagged revoked/dead in the 2026-07-07 CLAUDE.md correction (tracked separately as LOS7-1230, open). Re-run once LOS7-1230 re-points the credential.

---

## Built this session (iterate-2 — cross-surface matcher)

- **Enrichment-draft read fixed**: `_absorb_enrichment` previously iterated as if the JSON were `{handle: {field: value}}` and silently dropped every entry from the canonical 2026-05-06 nested schema (`{drafts: [{handle, proposed_subject_description, ...}]}`). The fix reads the `drafts` array and re-keys each entry's `proposed_*` field onto `(product.<handle>, <metafield_key>)` so the structural diff fires against Shopify product metafield reads. Back-compat path preserved for legacy flat-shape drafts.
- **Series-to-metaobject projection**: every at-a-glance and `_master.md` fact is mirrored onto the `series.metaobject` surface. Matcher now compares library R2 facts structurally against Shopify metaobject reads without an LLM fan-out.
- **Cardinality analysis**: full-catalogue projection produces ~28K key iterations (78 series × ~360 average all-keys). Well under the 500K threshold; no `--handle` gate required.
- **Live re-qualification (4 series)**: 132 products scanned, **4 R0-live disagreements** surfaced — one per series on `series.metaobject.location`. Drift between live Shopify metaobject and R2 research file location values. Spec gate (≥1 R0-live or drift finding) met.
- **Tests**: 9 new tests in `tests/test_matcher_widening.py`. 16 total unit tests pass; integration test deselected by default.
- **Captions-store data gap surfaced** (Task 2e): 4 of 73 R2 series have IPTC captions (5.5% coverage). Caption-conflict severity grade is muted across ~95% of the library. Recommend a follow-on Lightroom-side captions backfill sprint (out of scope here).

---

## Status

| Item | State |
|---|---|
| Install | Working (`pip3 install -e .`) |
| Smoke test (bathurst-gasworks) | Pass — 1 R0-live finding |
| 4-series live scan (wangi/kinugawa/tin-city/bathurst-gasworks) | Pass — 4 R0-live, 132 products |
| Enrichment-draft read | **Fixed** — was reading 0 entries from the canonical schema |
| Series-to-metaobject projection | **Live** |
| Integration test | Pass against live Shopify Admin |
| `gql()` raises on `errors[]` | Active (iterate-1) |
| `--verbose` plane DEBUG logs | Active (iterate-1) |
| Captions plane coverage | 4 / 73 series (5.5%) — data gap, not an agent defect |

---

## CC tasks — next sprint candidates

- **Captions-store backfill sprint**: 69 series have no captions; the LR caption-exporter plugin already exists (`LostCollective.lrplugin` Export captions for selected collection). Bulk export from already-edited JPGs would lift coverage from 5.5% → 100% in a single sprint. Caption-conflict severity grade becomes useful library-wide.
- **Image-stem mapping** to fire caption-conflict on `(product.<handle>, alt_text.<stem>)` automatically. Requires a stem-to-product join (image filename → product handle) that the catalogue currently doesn't expose cleanly. Defer until backfill sprint completes.
- **Daily scheduled task**: gated on three clean cross-series re-qualifications + Brett pre-approval of scheduled-task tool permissions.

Repo: `~/Claude/code-projects/agents/lc-facts-reconcile/`
Env: `~/Claude/code-projects/lost-collective-dawn/.env.tpl`
Run: `op run --env-file=$HOME/Claude/code-projects/lost-collective-dawn/.env.tpl -- lc-facts-reconcile --only <handle1,handle2,...>`

---

## Cowork tasks

- Review the 4 R0-live `series.metaobject.location` findings — decide whether the Shopify metaobject text or the R2 research file is canonical, then either back-propagate R2 to metaobject or update R2.
- Decide caption-backfill priority vs other agent work.

---

## Blockers / dependencies

- Image-stem mapping to enable caption-conflict on alt_text comparisons (requires catalogue join).
- Captions-store data gap (4 / 73 series) — backfill sprint required before caption-conflict severity grade is library-wide useful.

---

## ENV / config

No changes this iterate. Uses `.env.tpl` from `lost-collective-dawn/` for Shopify API credentials.

Key code locations:

- `lc_facts_reconcile/planes/library.py` — enrichment-draft read + series-to-metaobject projection.
- `lc_facts_reconcile/planes/shopify.py` — singular metafield aliases (iterate-1) + gql errors guard.
- `lc_facts_reconcile/diff.py` — six severity grades + caption-wins precedence.
- `tests/test_matcher_widening.py` — 9 new iterate-2 tests.

---

## 2026-07-20 — LOS7-1585 + LOS7-1587: fail-closed, captions plane repaired, dead planes de-scoped

Both from the LOS7-1571 sweep triage.

**LOS7-1585 — fail closed (commit `6ec0348`).** On 2026-07-08 all 125 Shopify reads died on a latin-1 header encode; the run scanned 0 products, wrote a clean-looking report and **exited 0**. `diff.py` gates the R0-live branch on `sho_val is not None`, so a wholesale live-plane failure makes R0-live unreachable by construction — deriving the exit status from the R0-live count alone guaranteed total failure looked like success. Unnoticed 12 days.
- `ReconciliationResult.run_failed` (errors + 0 products, or explicit abort). `cli.py` returns **exit 3** on it, checked BEFORE the R0-live test. 3 not 2 — argparse owns 2 (see DEPLOYMENT.md exit-code table).
- Runner aborts once the live plane fails on >20% of handles attempted (min 5 tried).
- `planes/shopify.py::_assert_header_safe()` validates the token at the single point it is obtained. Reports only THAT it is malformed and how many bad chars — never the char, position, or any part of the value (the original urllib error leaked a credential char into the log). Test asserts no leak.
- `~/.claude/scripts/lc-facts-reconcile-scheduled.sh` was auto-committing the report regardless of status; now labels a failed run's commit `FAILED RUN — not a measurement (exit 3)`. Still commits it — the 07-08 report on disk is what made this diagnosable.

**LOS7-1587 — captions repaired, precedence fixed, planes de-scoped (commit `8241bb6`).** All 3,762 graded rows ever produced were R0-live; applied+captions were `(none)` on every one while headers advertised four planes.
- Captions had TWO stacked bugs: parser iterated the export's TOP level (manufacturing values from `series_handle`/`generated_at`) instead of the payload under `captions`; and keyed them `("captions.iptc", stem)`, which `diff.py` can never correlate. Now `("product.<handle>-<slug>", "subject_description")`, joined via `f"{handle}-{caption_key}"`. Covers 20/21 wangi, 5/5 kinugawa.
- **Precedence was the dangerous one.** `_classify` tested caption-conflict first with an early return. With captions repaired that would have demoted **102 of 162** live R0-live rows, headline 162 -> ~60, reading as improvement while hiding 63% of live Rule-0 exposure. Live now grades first, never demoted; a row that is both emits BOTH. Verified all 162 preserved. No test covered this — there are now four.
- Default planes now `library,shopify`. Report header reports planes that CONTRIBUTED, not those requested.
- `applied` documented unusable: regex-scrapes retired tone-of-voice-rollout prose, extracts junk handles (`'links (5 → 15 total). lc-map placeholder HTML comment in the Now section.'`). `drift`/`R0-pending` stay unreachable. `stale-claim` defined but never assigned.
- Captions stays OPT-IN: enabling adds ~299 findings vs 24 agreements, mostly two valid descriptions of the same photo. Editorial call, not a code one.

Suite 91 -> 98 tests (`tests/test_fail_closed.py`, `tests/test_captions_plane.py`).

**Brett-actions** — NONE. (LOS7-1586's gate was answered same session: prefix-only approved, captions stay opt-in.)

**Next session priorities**
1. ~~LOS7-1586 — DONE (commit `8df28d1`).~~ Original note kept for context: Verified 21 of 51 rows against live Shopify: **19 = live is a strict PREFIX of library** (remediation trimmed trailing series boilerplate), **0 add text**, 2 genuinely divergent. R0-live means "live carries a claim the library doesn't back", so a trim CANNOT create exposure — ~90% of the +51 are false positives of exact-string matching. Both directions the issue proposed are wrong: updating the library would DELETE real sourced facts ("one of 101 New South Wales roadside motels ... across 2018"); re-pushing would reintroduce the boilerplate LOS7-1401/1402 removed. Proposed fix: treat a live value that is a strict prefix of the library value as not-R0-live. **Prefix-only, NOT substring** — a negation in a library sentence could wrongly clear a contradicting live claim. Real findings that survive: `hotel-motel-101-appin-motel` (live adds "titled as a project conceit but") and `bathurst-gasworks-purifier-shed-roof`.
2. Caption-key naming divergence: 46 of 67 caption files have ZERO correlation to library products. `hotel-motel-101` covers 5/49 because caption keys carry location suffixes (`3-explorers-motel-katoomba`) the product handles lack. Worth its own issue if the plane should fully cover.
3. Whether the token that broke 2026-07-08 is still malformed — not checked (requires reading the credential). The next scheduled run will now say so loudly instead of exiting 0.

**Decisions made**
- Exit 3, not 2, for a failed run — argparse owns 2.
- Live exposure always outranks caption-conflict; both emitted rather than one replacing the other.
- Captions and applied opt-in rather than deleted — honest de-scope over false coverage.
- Stopped at the LOS7-1586 gate rather than changing Rule 0 grading semantics unilaterally.


---

## 2026-07-20 (cont.) — LOS7-1586 closed: a trimmed live value is not Rule 0 exposure

Brett approved prefix-only; captions stay opt-in (so LOS7-1587's default is unchanged).

**Built** (commit `8df28d1`): `diff.py::_live_is_trim_of_library()`. A live value that is a strict PREFIX of the library value asserts nothing the library doesn't back, so it is no longer graded R0-live. Three guards: prefix-only (never substring — "did not close in 1990" CONTAINS "close in 1990", so substring would clear a contradicting claim); word-boundary check (mid-word truncation "ran until 199" vs "ran until 1990" stays graded); 20-char floor (a stub metafield is not a deliberate trim). 11 tests, suite 109.

**Verified against LIVE Shopify**, scoped run over the 8 affected series, `--output` to a temp path so it could not overwrite the dated report: 389 products, **R0-live 56 -> 6**. Both rows predicted from the 21-row sample survived, plus 4 unsampled.

**Filed LOS7-1588** for the 6 survivors — they are one coherent cluster: live asserts the Hotel Motel 101 title is "a project conceit" and that chain-branded properties are included, neither in the research file. Plus `bathurst-gasworks-purifier-shed-roof` (genuine divergence, not a trim).

**Note for whoever runs the reconciler manually:** use `--output` to a temp path. `report.py` names by date with no run id, so a manual run silently overwrites that day's scheduled report — this is how the 2026-07-14 06:43 run (R0-live 169) was replaced on disk by the 11:08 manual run (108). Recorded on LOS7-1585.

**Next session priorities**
1. **LOS7-1588** — decide whether the "project conceit" framing is Brett's own (library gains it, sourced) or generated hedging (comes off live). Recurs across 5 products with variations, which reads as generated, but that is a read not a finding.
2. Caption-key naming divergence: 46 of 67 caption files have zero correlation to library products (unchanged from above).

---

## 2026-07-20 (cont.) — LOS7-1588/1589: library-side outcome, no reconciler code change

No code change in this repo. Recorded here because it is what the engine now reports.

The 6 R0-live rows the LOS7-1586 trim rule left standing were resolved on the data side (`cowork/brand-voice` commits `ef91dbd`, `e0ed3a0`), and the direction ran BOTH ways:
- **hotel-motel-101 (5 products)** — live was wrong: subject_description asserted the series title is "a project conceit", framed against the count. Stripped from live via `metafieldsSet`.
- **jamison-hotel and bathurst-gasworks-purifier-shed-roof** — the LIBRARY was wrong. Bathurst's live text is verbatim Brett's IPTC caption; captions are Tier 1 and override, so the library entry was aligned to it.

**Root cause:** the LOS7-182 correction of 2026-05-15 landed only in `research/locations/hotel-motel-101.md`. `series/_master.md` and the enrichment draft's `.facts_library` blob (fed straight to copy generation) still carried "the actual count is 102 motels" and "Chain motels excluded" for two months. LOS7-1589 tracks a deterministic cross-layer check.

**Verified:** live scoped run, hotel-motel-101 + bathurst-gasworks, 125 products, **R0-live 6 -> 0**, exit 0.

Note the validation of LOS7-1587: bathurst is textbook `caption-conflict`, the grade that repair made reachable. With a working captions plane it would have surfaced as a caption conflict rather than hiding inside an R0-live row.
