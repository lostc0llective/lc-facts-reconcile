# lc-facts-reconcile — deployment

**Status (2026-05-31).** Iterate-2 shipped (cross-surface matcher). Deployed to **Mac launchd** 2026-05-31, replacing an earlier broken plist (see below).

Launchd test-fire on 2026-05-31: 71 series scanned, 1784 products, **75 R0-live disagreements** surfaced (catalogue-wide `series.metaobject.location` drift between live Shopify metaobjects and the R2 research files), report written, ~$0 (no LLM loop). The `op run` Shopify auth path worked headlessly under launchd.

---

## Execution context

Read-only diff engine. **No agent loop, no Anthropic key.** It needs `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET` (to mint a Shopify Admin token via OAuth `client_credentials`), and `LINEAR_API_KEY` only for `--linear-comment`. All three are 1Password `op://` references resolved at runtime by `op run --env-file`.

The binding dependency is therefore the **1Password CLI (`op`)** plus the service-account token. `op` exists on the Mac, not in the Cowork sandbox. See `~/Claude/cowork/agents/notes/2026-05-31_sdk-plumbing-pattern.md` ("Execution contexts") for the three-environment model.

---

## Canonical deployment — Mac launchd

### Wrapper script

`~/.claude/scripts/lc-facts-reconcile-scheduled.sh` (chmod 755). launchd does not source `~/.zprofile`, so the wrapper:

- sets `PATH` (Python 3.13 framework bin + homebrew + system) and `HOME`
- sources `OP_SERVICE_ACCOUNT_TOKEN` from `~/.config/op/service-account-token` (so `op run` auths without Touch ID)
- `cd`s to the repo and `exec`s `op run --env-file=$HOME/Claude/code-projects/lost-collective-dawn/.env.tpl -- lc-facts-reconcile`

### plist

`~/Library/LaunchAgents/com.lostcollective.facts-reconcile.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lostcollective.facts-reconcile</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/brettpatman/.claude/scripts/lc-facts-reconcile-scheduled.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>6</integer>
        <key>Minute</key><integer>43</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/brettpatman/Claude/cowork/agents/logs/lc-facts-reconcile.out</string>
    <key>StandardErrorPath</key>
    <string>/Users/brettpatman/Claude/cowork/agents/logs/lc-facts-reconcile.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>/Users/brettpatman</string>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>/Users/brettpatman/Claude/code-projects/agents/lc-facts-reconcile</string>
</dict>
</plist>
```

Schedule: **daily 06:43 local**, offset 30 minutes after Agent 4's 06:13 (Wave 2 synthesis recommendation). `RunAtLoad=false`.

### Install

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lostcollective.facts-reconcile.plist
launchctl enable gui/$(id -u)/com.lostcollective.facts-reconcile
```

(Reinstall after a plist edit: `launchctl bootout gui/$(id -u)/com.lostcollective.facts-reconcile` first.)

### Test-fire now

```bash
launchctl kickstart -k gui/$(id -u)/com.lostcollective.facts-reconcile
```

Expected: ~3 min wall time, ~$0. A fresh `_reconciliation/<year>/reconciliation-report-<date>.md` is written.

### Exit codes (read before treating a non-zero exit as a failure)

`lc-facts-reconcile` exits **1 when any R0-live finding exists** (a CI-style signal), 0 when there are none, and 2 on an argparse error. The catalogue routinely carries R0-live drift, so a **daily exit code of 1 in `launchctl list` is EXPECTED** and means the report was written with findings — not a crash. Genuine failures (auth, network, GraphQL) surface in the `.err` log. There is no `KeepAlive` on this job, so a non-zero exit never triggers a respawn.

---

## Manual CLI — pre-flight for any tov-batch / journal sprint

Before a sprint rewrites a series, run the reconciler scoped to that handle to surface drift **before** you rewrite it in:

```bash
op run --env-file=$HOME/Claude/code-projects/lost-collective-dawn/.env.tpl -- \
  lc-facts-reconcile --only <handle1,handle2,...>
```

Other flags: `--since=YYYY-MM-DD`, `--severity=R0-live`, `--delta=YYYY-MM-DD` (diff against a prior report), `--planes=library,shopify`, `--linear-comment --linear-issue=LOS7-XXX` (post the R0-live summary to a Linear issue). From an interactive terminal `op` and the SA token are already in the environment, so the wrapper is not needed for ad-hoc runs.

---

## Why not Cowork scheduled-tasks?

The Cowork (claude.ai) scheduled-tasks runner executes in a Linux sandbox **without the 1Password CLI**. This agent mints its Shopify Admin token from `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET`, which are `op://` references resolved by `op run`. With no `op` in the sandbox, the Shopify plane cannot authenticate and the reconciliation produces no live findings (the pre-iterate-2 Wave 1 Session D "artificially-empty" failure mode). Same execution-context mismatch as Agent 4 — the missing dependency is `op` rather than the keychain + SDK.

**A prior Mac launchd plist for this agent existed but was broken** and is now replaced: it invoked `lc-facts-reconcile --linear-comment` **without** the required `--linear-issue` (argparse error, exit 2), and it did **not** source the service-account token (so `op run` would hit a headless biometric wall). It was scheduled Monday 09:01. Replaced 2026-05-31 with the wrapper-based daily 06:43 deployment above (bare `lc-facts-reconcile`, report-only; add `--linear-comment --linear-issue=...` manually when a specific issue should receive the summary).

---

## Report path

`~/Claude/cowork/brand-voice/facts-library/_reconciliation/<year>/reconciliation-report-<YYYY-MM-DD>.md`

The report is overwritten on a same-day re-run (the filename is date-keyed).

---

## Troubleshooting

- **Logs:** `~/Claude/cowork/agents/logs/lc-facts-reconcile.out` and `.err`.
- **launchd state:** `launchctl print gui/$(id -u)/com.lostcollective.facts-reconcile` or `launchctl list | grep lostcollective`.
- **Re-fire manually:** `launchctl kickstart -k gui/$(id -u)/com.lostcollective.facts-reconcile`.
- **Empty report / Shopify reads fail?** Check the `.err` log for `op` auth errors or `Shopify GQL HTTP` failures. Verify `~/.config/op/service-account-token` is readable and `~/Claude/code-projects/lost-collective-dawn/.env.tpl` exists. The `gql()` error guard (iterate-1) surfaces GraphQL drift loudly rather than silently.

---

## Spec + repo

- Spec: `~/Claude/cowork/brand-voice/agents-spec-staging/05-facts-library-reconciler.md`
- README (usage, severity grades, tests): `README.md` at the repo root.
- Repo: `github.com/lostc0llective/lc-facts-reconcile` (private).
- KG node: `LCFactsReconcileAgent` (status: active).
