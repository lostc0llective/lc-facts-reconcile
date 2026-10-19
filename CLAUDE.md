# lc-facts-reconcile (Agent 5)

Read-only diff engine for the facts library. It compares four planes (research files, applied records, live Shopify metafields and metaobjects, the captions store) and writes a disagreement report. It never writes to the library, Shopify or applied records.

## Where and how to run
- Repo `lostc0llective/lc-facts-reconcile` (public; docs must not name token files or 1Password items), `main`. `README.md` is the contract (there is no separate spec); `DEPLOYMENT.md` covers the launchd job.
- Runs daily under launchd as `com.lostcollective.facts-reconcile` and commits the dated report to `~/Claude/cowork/brand-voice/facts-library/_reconciliation/YYYY/reconciliation-report-YYYY-MM-DD.md`. Manual: `lc-facts-reconcile` (flags: `--only=<handle>`, `--planes=`, `--since=`, `--severity=R0-live`, `--delta=`, `--output=`), with Shopify credentials supplied by `op run` and an env template. Needs Python 3.11+ and `op`; run it on this Mac, not the Cowork sandbox.
- Tests: `pytest` (150 passed at 2026-10-20).

## Reading the report
- Exit codes: 0 no R0-live outstanding, 1 R0-live outstanding (normal), 3 the run failed. A report that scanned 0 products is a failed run. Report age is not liveness; the heartbeat file `~/Claude/cowork/agents/logs/lc-facts-reconcile.heartbeat.json` is.
- Read the per-field decomposition, not the headline. Report values are truncated for display. Full notes: `~/Claude/cowork/brand-voice/REFERENCE.md`.

## Open state (2026-10-20)
- The `custom.lightroom_id` fixture leftover in `tests/test_coverage.py` was already removed (`35a2eb2`); nothing of it remains in code or tests.
- The stale duplicate wrapper under `~/Claude/scheduled/launchd/scripts/` was the `lc-kg-maintainer` one, now archived and removed (LOS7-3199); the reconcile wrapper there matches the deployed copy.
- Failure alerts say what to do: re-run the job, then read the error log (LOS7-3199).
