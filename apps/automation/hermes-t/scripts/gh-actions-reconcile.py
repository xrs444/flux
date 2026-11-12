#!/opt/hermes/.venv/bin/python3
"""gh-actions-reconcile — belt-and-suspenders for gh-actions-watch.py.

gh-actions-watch.py creates one triage card per currently-failing GitHub
Actions run (idempotency key `github:<repo>:<workflow>:<run_number>`) and has
no way to close anything — every failing run it has ever seen stays on the
board forever. Build/test-style workflows that fail intermittently across
many commits accumulate a near-duplicate card per failing run, long after a
later run (success OR another failure) has superseded it (confirmed live
2026-11-11: 25 of 27 CI cards on the ops board were stale this way, oldest
over a month old).

This script is the drift-catcher for that gap, mirroring
ops-board-reconcile.py's pattern exactly: runs as an hourly --no-agent
`hermes cron` job (no LLM involved), read-only until the final comment+
archive step, and only ever touches `source: cron` triage cards (the tag
gh-actions-watch.py sets on every card it creates — never alert-sourced
cards, which ops-board-reconcile.py already owns).

A card is archived when its run number is no longer the most recent run of
that exact workflow — regardless of whether the newer run succeeded (this
specific failure is resolved) or failed again (gh-actions-watch.py has
already created, or will create on its own next tick, a fresh card for
that newer run; this one is just a stale duplicate). If the title doesn't
parse, or the workflow/run can't be resolved via the GitHub API, the card
is left alone rather than guessed at — same policy as
ops-board-reconcile.py's `_title_to_key`.

Grouping prefers `workflow_id` out of the card's body (stable across runs,
added 2026-11-11 to gh-actions-watch.py) over the title's `workflow` text,
because GitHub's Dependabot Updates check emits a unique dynamic display
name per run (e.g. "uv in <path> for <packages> - Update #<id>") that never
matches itself across runs — a title-only lookup would leave every single
Dependabot-sourced card stuck forever (confirmed live 2026-11-11: 3 such
cards, weeks old, survived this script's first version untouched for
exactly that reason). Cards created before workflow_id existed fall back to
the by-name `/actions/workflows` lookup, which is correct for any
normally-named workflow (Build and Deploy, version-drift, etc.) but would
mis-group Dependabot runs if it were the only path.
"""

import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

HERMES = "/opt/hermes/.venv/bin/hermes"
GITHUB_TOKEN = None  # set via env if either repo goes private; see gh-actions-watch.py's header

# Mirrors gh-actions-watch.py's own title format exactly:
#   f"{repo} | {workflow} | run {run_number}"
TITLE_RE = re.compile(r"^(?P<repo>\S+) \| (?P<workflow>.+) \| run (?P<run>\d+)$")
WORKFLOW_ID_RE = re.compile(r"^workflow_id: (?P<id>\d+)$", re.MULTILINE)


def _gh_get(path: str) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def _latest_run_for_workflow_id(repo: str, workflow_id: str) -> int | None:
    """Max run_number among the most recent runs — NOT runs[0]. Confirmed
    live (2026-11-11): GitHub's own ordering is by created_at/internal id,
    not run_number, and two runs from the same batch (e.g. a single
    Dependabot Updates invocation covering multiple ecosystems) can share
    an identical created_at down to the second, landing in either order.
    per_page=1 alone returned run 36 ahead of the actually-latest run 37
    for exactly this reason, which left both cards alive instead of
    archiving 36. per_page=5 is a comfortable buffer against ties without
    a second API call."""
    runs = _gh_get(
        f"/repos/{repo}/actions/workflows/{workflow_id}/runs?per_page=5"
    ).get("workflow_runs", [])
    numbers = [r["run_number"] for r in runs if r.get("run_number") is not None]
    return max(numbers) if numbers else None


def latest_run_number(repo: str, workflow_name: str, workflow_id: str | None) -> int | None:
    """Fetch the single most recent run for this workflow. Prefers the stable
    workflow_id (from the card body) when present; otherwise resolves the
    display name (as carded in the title) to an id via /actions/workflows
    first. None if the workflow or any run can't be found — the caller
    leaves the card alone in that case."""
    if workflow_id is not None:
        return _latest_run_for_workflow_id(repo, workflow_id)

    workflows = _gh_get(f"/repos/{repo}/actions/workflows?per_page=100").get("workflows", [])
    match = next((w for w in workflows if w.get("name") == workflow_name), None)
    if match is None:
        return None
    return _latest_run_for_workflow_id(repo, str(match["id"]))


def hermes_kanban(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [HERMES, "kanban", "--board", "ops", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    listed = hermes_kanban("list", "--status", "triage", "--json")
    if listed.returncode != 0:
        print(f"FAILED to list triage cards: {listed.stderr}", file=sys.stderr)
        return 1
    cards = json.loads(listed.stdout)

    latest_cache: dict[tuple[str, str], int | None] = {}
    reconciled, failed = [], []
    for card in cards:
        body = card.get("body") or ""
        if not body.startswith("source: cron"):
            continue  # only ever touch gh-actions-watch.py's own cards

        match = TITLE_RE.match(card["title"])
        if not match:
            continue
        repo, workflow, run = match["repo"], match["workflow"], int(match["run"])
        id_match = WORKFLOW_ID_RE.search(body)
        workflow_id = id_match["id"] if id_match else None

        key = (repo, workflow_id or workflow)
        if key not in latest_cache:
            try:
                latest_cache[key] = latest_run_number(repo, workflow, workflow_id)
            except Exception as exc:  # noqa: BLE001 — top-level entrypoint
                print(f"FAILED to fetch latest run for {repo} | {workflow}: {exc}", file=sys.stderr)
                latest_cache[key] = None
        latest = latest_cache[key]
        if latest is None or run >= latest:
            continue  # unknown, or this card IS the latest run — leave it

        task_id = card["id"]
        note = (
            f"gh-actions-reconcile: run {run} is superseded by run {latest} "
            f"as of {datetime.now(timezone.utc).isoformat()}. Archiving as stale."
        )
        commented = hermes_kanban("comment", task_id, note)
        if commented.returncode != 0:
            print(f"comment failed for {task_id} (non-fatal): {commented.stderr}", file=sys.stderr)
        archived = hermes_kanban("archive", task_id)
        if archived.returncode != 0:
            print(f"archive FAILED for {task_id}: {archived.stderr}", file=sys.stderr)
            failed.append(task_id)
            continue
        reconciled.append(task_id)

    if reconciled:
        print(f"Archived {len(reconciled)} superseded card(s): {', '.join(reconciled)}")
    else:
        print("No superseded triage cards found.")
    if failed:
        print(f"Failed to archive: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
