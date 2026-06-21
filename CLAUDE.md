# lc-facts-reconcile (Agent 5)

Diff engine for the LC facts library: reconciles four planes (research files, applied records, live Shopify metafields, IPTC captions) into a structured disagreement report. Sonnet 4.6. Read-only, never writes.

- CLI: `lc-facts-reconcile`. Requires Python 3.11+ and the `op` CLI; run on the local machine, not the Cowork sandbox.
- Spec: no separate spec file (the `cowork/agents/specs/` 01-06 set predates this agent; slot 05 is the outcome-auditor). `README.md` is the contract.

Part of the LC agents programme (`~/Claude/cowork/agents/`). Status: shipped 2026-05-26.
