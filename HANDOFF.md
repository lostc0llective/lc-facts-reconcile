# lc-facts-reconcile — HANDOFF

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

Last updated: 2026-07-13. Intervening commit since 2026-06-27: `fc939ee` (2026-07-07) was docs-only workspace-migration housekeeping (lc-master-context rename, rollout archive, Pairing header) — no functional change. Prior history: `502712a` ran the LOS7-628 store-wide product metadata coverage and consistency audit; `2766dbc` switched the Shopify auth path to a static Admin Token to bypass the client_credentials scope gap (the first functional change since 2026-06-13); `a156821` hardened `DEPLOYMENT.md` against the 2026-06-23 restoration issues (plist loss, pip-editable breakage, `read_metaobjects` scope failure); `9c747f0` and `fcf5f5d` were spec-pointer and HANDOFF housekeeping. Matcher widening (2026-05-31) remains the latest substantive matcher state. Earlier 2026-06-13 doc commits: `d85f1fc` added a repo `CLAUDE.md` and fixed a spec pointer (drift-audit str-07/agents-04); `9c14f59` updated `DEPLOYMENT.md` and this `HANDOFF.md` with session WIP notes (LOS7-517 git-hygiene cleanup).

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
