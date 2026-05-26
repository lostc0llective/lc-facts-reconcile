# lc-facts-reconcile

Agent 5 of the Lost Collective agents programme. Reads four input planes and produces a structured disagreement report. Read-only — never writes to Shopify, the facts library, or applied records.

## Spec

`~/Claude/cowork/brand-voice/agents-spec-staging/05-facts-library-reconciler.md`

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

| Grade | Meaning |
|---|---|
| R0-live | Live Shopify surface has a claim the library doesn't back. Rule 0 exposure. |
| R0-pending | Applied record has a claim the library doesn't back, not confirmed live. |
| drift | Library is behind a known correction (live is correct, library stale). |
| caption-conflict | Captions store and research file disagree. Caption wins. |
| internal | Two library files disagree with each other. Brett to resolve. |
| stale-claim | Research file carries a superseded claim. |

## Pre-flight

- `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` — via `op run --env-file=...env.tpl`
- `LINEAR_API_KEY` — from LCAutomation vault via `op run` for `--linear-comment`
- No Anthropic API key needed — this is a diff engine with no agent loop.

## Report path

`~/Claude/cowork/brand-voice/facts-library/_reconciliation/YYYY/reconciliation-report-YYYY-MM-DD.md`

## Tests

```
pytest tests/ -v
```

All five spec fixtures (drift, R0-live, caption-conflict, internal, open-claims) plus edge cases.
