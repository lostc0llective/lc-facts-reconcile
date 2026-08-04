# lc-facts-reconcile

Agent 5 of the Lost Collective agents programme. Reads four input planes and produces a structured disagreement report. Read-only — never writes to Shopify, the facts library, or applied records.

## Spec

No separate spec file — this README is the contract. (The `~/Claude/cowork/agents/specs/` 01-06 set predates Agent 5; slot 05 is the outcome-auditor.)

## What it does

1. Reads the LC facts library (research files, master, enrichment drafts, captions).
2. Reads applied records under `~/Claude/cowork/brand-voice/{applied,audits/*/applied}/`.
3. Reads live Shopify metafields and metaobjects.
4. Reads IPTC captions store.
5. Diffs the four planes and writes a structured disagreement report.
6. Optionally posts an R0-live summary to a Linear issue.

## What it does NOT do

- Write to facts library files.
- Write to Shopify.
- Write to applied records.
- Source-research (that is Agent 1's job).
- Sprint prompt generation (Agent 3).

## Install

```
pip install -e .[dev]
```

## Usage

```
# Full scan, all series
lc-facts-reconcile

# Scoped to one series
op run --env-file=~/Claude/code-projects/lost-collective-dawn/.env.tpl -- \
  lc-facts-reconcile --only=bathurst-gasworks --planes=library,shopify

# Incremental: only applied records changed since a date
lc-facts-reconcile --since=2026-05-20

# Filter to R0-live findings only
lc-facts-reconcile --severity=R0-live

# Delta against previous report
lc-facts-reconcile --delta=2026-05-20

# Post R0-live summary to Linear
lc-facts-reconcile --linear-comment --linear-issue=LOS7-XXX

# Override report path
lc-facts-reconcile --output=path/to/report.md
```

## Severity grades

| Grade | Meaning | Reachable? |
|---|---|---|
| R0-live | Live Shopify surface has a claim the library doesn't back. Rule 0 exposure. | yes (default) |
| internal | Two library files disagree with each other. Brett to resolve. | yes (default) |
| drift | Library is behind a known correction (live is correct, library stale). | yes (default, `applied` plane) |
| caption-conflict | Captions store and research file disagree. Caption wins. | only with `--planes …,captions` |
| R0-pending | Applied record has a claim the library doesn't back, not confirmed live. | yes (default), but only when Shopify has no value for that exact product/field — e.g. `--planes` scoped without `shopify`, or the product/field is unset live |
| stale-claim | Research file carries a superseded claim. | no — defined but never assigned |

**Read this before trusting the grade set (LOS7-1587, amended LOS7-1929).** For the reconciler's entire operating history to 2026-07-20 — 31 reports, 3,762 graded rows — **every single row was R0-live**, and the `applied` and `captions` columns were `(none)` on all of them, while every report header advertised four planes. Three grades were mechanically unreachable rather than merely rare. `applied` was fixed and rejoined the default 2026-08-04 (below); `captions` stays a deliberate opt-in.

- **`captions` — repaired, opt-in.** Two stacked bugs: the parser read the top level of the export (manufacturing values out of `series_handle`, `generated_at`) instead of the payload under `captions`, and it keyed them `("captions.iptc", stem)`, a namespace `diff.py` can never correlate against `("product.<handle>", "subject_description")`. Both fixed; the join is `f"{handle}-{caption_key}"`. It is **not on by default** because switching it on adds ~299 findings against only 24 agreements, and most are two valid descriptions of the same photograph rather than defects. Whether `caption ≠ library` constitutes a defect is an editorial decision, not a code one. Run `--planes library,shopify,captions` to see them.
- **`applied` — rewritten, back in the default (LOS7-1929, 2026-08-04).** The original regex-scraped free-form sprint prose from the retired tone-of-voice-rollout project (archived, frozen, nothing writes new records there) and, separately, from ad-hoc sprint-report docs that have since landed in the live `applied/` folder. Tested against both: 91 "parsed" entries, all junk — e.g. one yielded `handles=['links (5 → 15 total). lc-map placeholder HTML comment in the Now section.']`, matching no real handle. Reliable extraction from prose is not achievable with regex. Factual-audit applies (LOS7-1870 onward) write a **structured** per-series record instead — one `### \`product-handle\`` block per product with its own Before/After blockquote — and the rewrite parses that shape only, skipping anything that doesn't match it rather than guessing. Confirmed against the live LOS7-1870 corpus: 829 entries, 101 series, all clean product handles. The archived tone-of-voice-rollout corpus is no longer walked at all (frozen, and per the finding above, contained nothing extractable anyway). See `planes/applied.py`'s module docstring.
  - **Why this also touches `library.py`.** An enrichment-draft (`facts-library/enrichment-drafts/*.json`) is Layer 3 pre-audit staging — nothing re-generates it once a later factual audit corrects and applies different text straight to Shopify. Once `applied` could actually resolve real data, `read_library()` started checking it: a draft's `proposed_subject_description` is skipped rather than absorbed into the library plane for any (product, field) an applied record already covers, since comparing a live correction against a draft it has already superseded is comparing against a claim nobody is standing behind. This is what turned LOS7-1870's 68-row R0-live spike (LOS7-1912) into either `drift` (draft genuinely needs resyncing) or nothing at all (draft's claim retired), never a live Rule-0 false alarm.
- **`stale-claim`** has resolution text and an entry in `SEVERITY_ORDER` but no assignment site anywhere in the codebase. Defined but unimplemented.

**Grade precedence:** live exposure is graded first and is never demoted. A row that is both a live disagreement and a caption conflict emits **both** findings. This matters: with the naive precedence (caption-conflict tested first, early return) repairing the captions plane would have reclassified 102 of the 162 live R0-live rows, dropping the headline to ~60 and reading as a large improvement while hiding 63% of live Rule-0 exposure.

## Pre-flight

- `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` — via `op run --env-file=...env.tpl`
- `LINEAR_API_KEY` — from LCAutomation vault via `op run` for `--linear-comment`
- No Anthropic API key needed — this is a diff engine with no agent loop.

## Report path

`~/Claude/cowork/brand-voice/facts-library/_reconciliation/YYYY/reconciliation-report-YYYY-MM-DD.md`

## Tests

```
# Default — unit tests only (integration tests skipped via pytest marker)
pytest

# Include the live Shopify integration test (requires creds)
op run --env-file=~/Claude/code-projects/lost-collective-dawn/.env.tpl -- \
  pytest -m integration
```

All five spec fixtures (drift, R0-live, caption-conflict, internal, open-claims) plus edge cases. The integration suite (`tests/test_shopify_integration.py`) hits the live Shopify Admin API and would have caught the silent-failure bug that shipped 2026-05-26 — the `metafields(identifiers:[...])` PRODUCTS_QUERY shape that the current API rejects. Iterate-1 (2026-05-31) rewrote the query to the singular `metafield(namespace, key)` aliased shape and added `gql()` error guards so any future GraphQL drift surfaces loud instead of silent.
