# lc-facts-reconcile (Agent 5)

Read-only diff engine for the facts library. It compares four planes (research files, applied records, live Shopify metafields and metaobjects, the captions store) and writes a disagreement report. It never writes to the library, Shopify or applied records.

## Where and how to run
- Repo `lostc0llective/lc-facts-reconcile` (public; docs must not name token files or 1Password items), `main`. `README.md` is the contract (there is no separate spec); `DEPLOYMENT.md` covers the launchd job.
- Runs daily under launchd as `com.lostcollective.facts-reconcile` and commits the dated report to `~/Claude/cowork/brand-voice/facts-library/_reconciliation/YYYY/reconciliation-report-YYYY-MM-DD.md`. Manual: `lc-facts-reconcile` (flags: `--only=<handle>`, `--planes=`, `--since=`, `--severity=R0-live`, `--delta=`, `--output=`), with Shopify credentials supplied by `op run` and an env template. Needs Python 3.11+ and `op`; run it on this Mac, not the Cowork sandbox.
- Tests: `pytest` (150 passed at 2026-10-18).

## Reading the report
- Exit codes: 0 no R0-live outstanding, 1 R0-live outstanding (normal), 3 the run failed. A report that scanned 0 products is a failed run. Report age is not liveness; the heartbeat file `~/Claude/cowork/agents/logs/lc-facts-reconcile.heartbeat.json` is.
- Read the per-field decomposition, not the headline. Report values are truncated for display. Full notes: `~/Claude/cowork/brand-voice/REFERENCE.md`.

## Open state (2026-10-18)
- `tests/test_coverage.py` (around line 262) still builds a `custom.lightroom_id` metafield in its fixture; harmless since the coverage list dropped it, but a leftover.
- A stale duplicate wrapper script under `~/Claude/scheduled/launchd/scripts/` is noted in `HANDOFF.md` as still to remove.
