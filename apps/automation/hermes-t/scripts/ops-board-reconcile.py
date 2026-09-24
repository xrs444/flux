#!/opt/hermes/.venv/bin/python3
"""ops-board-reconcile — belt-and-suspenders for the alert-ingest resolve path.

kanban_card_upsert.ts (flux/windmill-workspace/f/sre/alert-ingest__flow/) now
archives an `ops` board card when Alertmanager sends a `resolved` webhook.
That covers the normal case, but it depends on Alertmanager actually sending
one — and it won't if Alertmanager itself loses in-memory state (a pod
restart, e.g. the one on 2026-09-21T20:17Z that orphaned every card fired
before it). This script is the drift-catcher for that case: it runs hourly as
a --no-agent `hermes cron` job (no LLM involved — deterministic, boring, safe
to run unattended) directly inside the hermes-t pod, and archives any
`ops`-board `triage` card whose alert is no longer active in Alertmanager.

Key derivation mirrors kanban_card_upsert.ts EXACTLY (same exclusions, same
join format) so a card's title can be turned back into the same idempotency
key that created it, and checked for membership in Alertmanager's currently
active groups. If the two ever drift apart, this script silently reconciles
nothing rather than archiving live cards — see _title_to_key's docstring.

Read-only until the very last step (comment + archive); never touches
anything but `source: alertmanager` triage cards on the `ops` board.
"""

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

ALERTMANAGER_URL = (
    "http://kube-prometheus-stack-alertmanager.monitoring.svc.cluster.local:9093"
    "/api/v2/alerts/groups"
)
HERMES = "/opt/hermes/.venv/bin/hermes"
NEVER_CARD_ALERTNAMES = {"Watchdog", "InfoInhibitor"}  # kept in sync with kanban_card_upsert.ts


def fetch_live_keys() -> set[str]:
    """Build the set of idempotency keys for every currently-active Alertmanager
    group, using the exact same derivation as kanban_card_upsert.ts's
    idempotencyKey (see that file's header comment for the full rationale)."""
    with urllib.request.urlopen(ALERTMANAGER_URL, timeout=15) as resp:
        groups = json.load(resp)

    live: set[str] = set()
    for group in groups:
        labels = group.get("labels") or {}
        alertname = labels.get("alertname")
        if not alertname or alertname in NEVER_CARD_ALERTNAMES:
            continue
        # A group with no active (non-resolved) alert left is not live.
        alerts = group.get("alerts") or []
        if not any(a.get("status", {}).get("state") == "active" for a in alerts):
            continue
        is_ksm = labels.get("job") == "kube-state-metrics"
        parts = sorted(
            f"{k}={v}"
            for k, v in labels.items()
            if k != "alertname" and not (is_ksm and k == "instance")
        )
        key = f"alert:{alertname}" + (":" + ",".join(parts) if parts else "")
        live.add(key)
    return live


def _title_to_key(title: str) -> str | None:
    """Reconstruct a card's idempotency key from its title. Returns None if the
    title doesn't look like one kanban_card_upsert.ts would have produced
    (title = f"{alertname} — {keyParts.join(', ')}" or bare alertname) — in
    that case the card is left alone rather than guessed at."""
    if " — " in title:
        alertname, rest = title.split(" — ", 1)
        parts = sorted(p.strip().replace(" ", "") for p in rest.split(","))
        return f"alert:{alertname}:{','.join(parts)}"
    return f"alert:{title}"


def hermes_kanban(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [HERMES, "kanban", "--board", "ops", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    try:
        live_keys = fetch_live_keys()
    except Exception as exc:  # noqa: BLE001 — this is the top-level entrypoint
        print(f"FAILED to fetch Alertmanager alert groups: {exc}", file=sys.stderr)
        return 1

    listed = hermes_kanban("list", "--status", "triage", "--json")
    if listed.returncode != 0:
        print(f"FAILED to list triage cards: {listed.stderr}", file=sys.stderr)
        return 1
    cards = json.loads(listed.stdout)

    reconciled = []
    for card in cards:
        body = card.get("body") or ""
        if not body.startswith("source: alertmanager"):
            continue  # only ever touch alert-sourced cards
        key = _title_to_key(card["title"])
        if key is None or key in live_keys:
            continue

        task_id = card["id"]
        note = (
            f"ops-board-reconcile: no matching active alert in Alertmanager "
            f"as of {datetime.now(timezone.utc).isoformat()} "
            f"(reconstructed key: {key}). Archiving as stale."
        )
        commented = hermes_kanban("comment", task_id, note)
        if commented.returncode != 0:
            print(f"comment failed for {task_id} (non-fatal): {commented.stderr}", file=sys.stderr)
        archived = hermes_kanban("archive", task_id)
        if archived.returncode != 0:
            print(f"archive FAILED for {task_id}: {archived.stderr}", file=sys.stderr)
            continue
        reconciled.append(task_id)

    if reconciled:
        print(f"Archived {len(reconciled)} orphaned card(s): {', '.join(reconciled)}")
    else:
        print("No orphaned triage cards found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
