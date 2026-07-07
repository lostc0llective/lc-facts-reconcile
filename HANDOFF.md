# lc-facts-reconcile — HANDOFF

Last updated: 2026-06-27. Intervening commits since 2026-06-15: `502712a` ran the LOS7-628 store-wide product metadata coverage and consistency audit; `2766dbc` switched the Shopify auth path to a static Admin Token to bypass the client_credentials scope gap (the first functional change since 2026-06-13); `a156821` hardened `DEPLOYMENT.md` against the 2026-06-23 restoration issues (plist loss, pip-editable breakage, `read_metaobjects` scope failure); `9c747f0` and `fcf5f5d` were spec-pointer and HANDOFF housekeeping. Matcher widening (2026-05-31) remains the latest substantive matcher state. Earlier 2026-06-13 doc commits: `d85f1fc` added a repo `CLAUDE.md` and fixed a spec pointer (drift-audit str-07/agents-04); `9c14f59` updated `DEPLOYMENT.md` and this `HANDOFF.md` with session WIP notes (LOS7-517 git-hygiene cleanup).

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
