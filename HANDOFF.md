# lc-facts-reconcile HANDOFF
Last updated: 2026-10-20

## Current state
- Repo `~/Claude/code-projects/agents/lc-facts-reconcile/`, branch `main`, clean tree level with origin. `pytest`: 150 passed, 1 deselected, 0 failed (checked 2026-10-18).
- 2026-10-20 (LOS7-3199): checked the `custom.lightroom_id` fixture (already gone since `35a2eb2`) and the git-backed wrapper (identical to the deployed copy); alert wording now names an action. No code change.
- Last code change: 2026-10-16 `62b588d` dropped `custom.lightroom_id` from `PER_PHOTO_METAFIELDS` in `lc_facts_reconcile/coverage.py` (Brett retired the field; the catalogue number is the one product link).
- R0-live thread closed: the last three survivors (ashio-copper-mine, mount-russell location, mckillops) were all resolved in LOS7-2098 (R0-live on `location` 3 to 0).
- 2026-09-30 (LOS7-3081): the repo is public, so its docs no longer name the token file or any 1Password item. The scheduled run loads the read-only token (no read-write fallback) and a per-job env template that lives in the private scheduled repo. Three code strings still point at dawn's `.env.tpl` for manual runs.
- Manual run: `op run --env-file=$HOME/Claude/code-projects/lost-collective-dawn/.env.tpl -- lc-facts-reconcile --only <handle1,handle2,...>`.
- Captions plane coverage was 4 of 73 series when last measured (data gap, not an agent defect). Detail and older sessions: `HANDOFF-archive-2026-10-20.md`.

## Next steps
- `facts-library-reliability-sweep/test_cross_layer.py` failure (outside this repo) has not been re-run.
- Captions-store backfill sprint (69 series have none) would make caption-conflict grading useful library-wide.

## Blocked on Brett
NONE
