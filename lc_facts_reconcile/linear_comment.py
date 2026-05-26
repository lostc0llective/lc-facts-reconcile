"""Optional --linear-comment: post R0-live summary to a Linear issue.

Uses LINEAR_API_KEY from env (loaded by CLI bootstrap or op run).
Only posts R0-live disagreements — per spec (resolved decision 3, 2026-05-26).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from .diff import Disagreement

log = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TOKEN_ENV = "LINEAR_API_KEY"

CREATE_COMMENT_MUTATION = """
mutation CreateComment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id url }
  }
}
"""


def post_r0_summary(
    issue_id: str,
    report_path: Path,
    disagreements: list[Disagreement],
    dry_run: bool = False,
) -> bool:
    """Post a one-line R0-live summary to the given Linear issue."""
    r0_live = [d for d in disagreements if d.severity == "R0-live"]

    if not r0_live:
        body = f"Reconciliation report at `{report_path}` — 0 R0-live disagreements. Library clean."
    else:
        handles = sorted({d.handle for d in r0_live})
        body = (
            f"Reconciliation report at `{report_path}` — "
            f"**{len(r0_live)} R0-live disagreement(s)** across {len(handles)} series: "
            f"{', '.join(f'`{h}`' for h in handles[:10])}"
            + (f" + {len(handles)-10} more" if len(handles) > 10 else "")
            + ". See the report for details."
        )

    if dry_run:
        log.info("dry-run: would post to %s: %s", issue_id, body[:120])
        return True

    return _post_comment(issue_id, body)


def _post_comment(issue_id: str, body: str) -> bool:
    token = os.environ.get(LINEAR_TOKEN_ENV)
    if not token:
        log.warning("post_linear_comment: %s not set; skipping.", LINEAR_TOKEN_ENV)
        return False

    payload = json.dumps({
        "query": CREATE_COMMENT_MUTATION,
        "variables": {"issueId": issue_id, "body": body},
    }).encode("utf-8")

    req = urllib.request.Request(
        LINEAR_API_URL,
        data=payload,
        headers={"Authorization": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        log.warning("post_linear_comment: HTTP error posting to %s: %s", issue_id, e)
        return False

    if data.get("errors"):
        log.warning("post_linear_comment: GraphQL errors: %s", data["errors"])
        return False

    result = (data.get("data") or {}).get("commentCreate") or {}
    if not result.get("success"):
        log.warning("post_linear_comment: success=false: %s", result)
        return False

    url = (result.get("comment") or {}).get("url", "")
    log.info("Linear comment posted: %s", url)
    return True
