# lc-facts-reconcile — HANDOFF

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
