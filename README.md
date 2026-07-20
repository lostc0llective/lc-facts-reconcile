# lc-facts-reconcile

Agent 5 of the Lost Collective agents programme. Reads four input planes and produces a structured disagreement report. Read-only — never writes to Shopify, the facts library, or applied records.

## Spec

No separate spec file — this README is the contract. (The `~/Claude/cowork/agents/specs/` 01-06 set predates Agent 5; slot 05 is the outcome-auditor.)

## What it does

1. Reads the LC facts library (research files, master, enrichment drafts, captions).
2. Reads applied records under `tone-of-voice-rollout/applied/`.
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
| caption-conflict | Captions store and research file disagree. Caption wins. | only with `--planes …,captions` |
| R0-pending | Applied record has a claim the library doesn't back, not confirmed live. | no — `applied` plane unusable |
| drift | Library is behind a known correction (live is correct, library stale). | no — `applied` plane unusable |
| stale-claim | Research file carries a superseded claim. | no — defined but never assigned |

**Read this before trusting the grade set (LOS7-1587).** For the reconciler's entire operating history to 2026-07-20 — 31 reports, 3,762 graded rows — **every single row was R0-live**, and the `applied` and `captions` columns were `(none)` on all of them, while every report header advertised four planes. Three grades were mechanically unreachable rather than merely rare.

- **`captions` — repaired, opt-in.** Two stacked bugs: the parser read the top level of the export (manufacturing values out of `series_handle`, `generated_at`) instead of the payload under `captions`, and it keyed them `("captions.iptc", stem)`, a namespace `diff.py` can never correlate against `("product.<handle>", "subject_description")`. Both fixed; the join is `f"{handle}-{caption_key}"`. It is **not on by default** because switching it on adds ~299 findings against only 24 agreements, and most are two valid descriptions of the same photograph rather than defects. Whether `caption ≠ library` constitutes a defect is an editorial decision, not a code one. Run `--planes library,shopify,captions` to see them.
- **`applied` — unusable, opt-in.** It regex-scrapes free-form sprint prose from the retired tone-of-voice-rollout (archived, frozen, nothing writes new records). It "parses" 91 entries but extracts junk: one record yielded `handles=['links (5 → 15 total). lc-map placeholder HTML comment in the Now section.']`. Those handles match nothing, which is why per-handle lookups returned zero. Reliable extraction from prose is not achievable with regex; the records would need a structured format.
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
