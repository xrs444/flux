#!/opt/hermes/.venv/bin/python3
"""gh-actions-watch — deterministic, no-agent replacement for the original
gh-actions-watch.sh + agent-prompt combo (see git history / KANBAN.md for
the old install).

Why this replaced the agent-mode version (2026-10-14): `kanban_create` has
no `board` parameter — it relies on whatever board is ambient-selected for
the session, which KANBAN.md already documented as occasionally drifting/
reverting. Pairing that with an LLM asked in English to "create on the
ops-board" produced two failure modes over the following weeks: (1) a large
fraction of cards landed on `projects` instead of `ops`, with zero error
surfaced, and (2) the model free-texted a slightly different title/key each
run instead of a stable machine-derived one, so idempotency-key matching
never collapsed them — 36 near-duplicate cards across 3 different title
conventions by the time this was noticed. It was also hard-depending the
entire watch on an LLM backend (xcog1's qwen3-30b-a3b via litellm) that was
mid-outage (bug-991) at the same time, silently dropping ticks.

This version removes the LLM from the loop entirely: it is the deterministic
drift-catcher pattern already used by ops-board-reconcile.py (`--no-agent`,
runs as the job itself, no agent turn, immune to any LLM backend being
down). The CLI's own `--idempotency-key` on `kanban create` already dedupes
(returns the existing id instead of creating a duplicate), so this script
does not need its own list-then-diff logic — it just calls `create` for
every currently-failing run on every tick; already-existing cards are a
no-op.

Monitor-script contract note (inherited, no longer load-bearing here): this
runs as a plain --no-agent script now, not --monitor-script, so the
stable-stdout requirement that applied to the old .sh version doesn't apply
— stdout here is a human-readable summary, logged verbatim by hermes cron.
"""

import json
import subprocess
import sys
import urllib.request

REPOS = ("xrs444/nix", "xrs444/flux")
HERMES = "/opt/hermes/.venv/bin/hermes"
GITHUB_TOKEN = None  # set via env if either repo goes private; see old .sh's header comment


def fetch_failing_runs(repo: str) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/runs?status=failure&per_page=10",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    return data.get("workflow_runs", [])


def hermes_kanban(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [HERMES, "kanban", "--board", "ops", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    created, upserted, failed = [], [], []

    for repo in REPOS:
        try:
            runs = fetch_failing_runs(repo)
        except Exception as exc:  # noqa: BLE001 — top-level entrypoint
            print(f"FAILED to fetch runs for {repo}: {exc}", file=sys.stderr)
            failed.append(repo)
            continue

        for run in runs:
            workflow = run.get("name", "?")
            run_number = run.get("run_number", "?")
            html_url = run.get("html_url", "")
            key = f"github:{repo}:{workflow}:{run_number}"
            title = f"{repo} | {workflow} | run {run_number}"
            body = f"source: cron\n\n{html_url}"

            result = hermes_kanban(
                "create", title,
                "--idempotency-key", key,
                "--triage",
                "--body", body,
                "--json",
            )
            if result.returncode != 0:
                print(f"FAILED upsert for {key}: {result.stderr.strip()}", file=sys.stderr)
                failed.append(key)
                continue
            try:
                payload = json.loads(result.stdout)
                (created if payload.get("created") else upserted).append(key)
            except (json.JSONDecodeError, AttributeError):
                upserted.append(key)  # created/updated either way; just don't know which

    print(f"Created {len(created)} new card(s), confirmed {len(upserted)} existing, {len(failed)} failure(s).")
    if created:
        print("New: " + ", ".join(created))
    if failed:
        print("Failed: " + ", ".join(failed), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
