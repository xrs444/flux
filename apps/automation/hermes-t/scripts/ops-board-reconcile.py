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

Also reconciles `source: flux` cards (titles `Flux <Kind>/<name> — <reason>`,
created by the Flux notification-controller -> Windmill path, which never
sends a resolve): the card is archived only when a live lookup of that exact
Flux resource, via the mcp-kubernetes MCP service (the only path from this
pod to the API server), shows Ready=True. Any lookup error or non-True Ready
leaves the card alone (fail closed).

Read-only until the very last step (comment + archive); never touches
anything but `source: alertmanager` / `source: flux` triage cards on the
`ops` board.
"""

import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

MCP_K8S_URL = "http://mcp-kubernetes.mcp-tools.svc.cluster.local:8080/mcp"
FLUX_API = {
    "Kustomization": "kustomize.toolkit.fluxcd.io/v1",
    "GitRepository": "source.toolkit.fluxcd.io/v1",
    "HelmRelease": "helm.toolkit.fluxcd.io/v2",
    "HelmRepository": "source.toolkit.fluxcd.io/v1",
}
_FLUX_TITLE = re.compile(r"^Flux (\w+)/(\S+) ")
_READY_TRUE = re.compile(r"status: ['\"]?True['\"]?\s+type: Ready\b")

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


def flux_resource_ready(kind: str, name: str, namespace: str) -> bool:
    """True only if the Flux resource exists and its Ready condition is True.
    Any error (MCP down, RBAC, not found, unknown kind) returns False so the
    card is left alone."""
    api = FLUX_API.get(kind)
    if not api:
        return False
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

    def post(payload: dict, sid: str | None = None):
        h = dict(headers)
        if sid:
            h["Mcp-Session-Id"] = sid
        req = urllib.request.Request(MCP_K8S_URL, json.dumps(payload).encode(), h)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.headers.get("Mcp-Session-Id"), resp.read().decode()

    try:
        sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "ops-board-reconcile", "version": "1"}}})
        post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
        _, raw = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "resources_get",
            "arguments": {"apiVersion": api, "kind": kind, "name": name, "namespace": namespace}}}, sid)
        result = json.loads(raw.split("data: ", 1)[1])["result"]
        if result.get("isError"):
            return False
        return bool(_READY_TRUE.search(result["content"][0]["text"]))
    except Exception as exc:  # noqa: BLE001 — fail closed
        print(f"flux lookup failed for {kind}/{name}: {exc}", file=sys.stderr)
        return False


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
        task_id = card["id"]
        if body.startswith("source: flux"):
            m = _FLUX_TITLE.match(card["title"])
            ns = re.search(r"^namespace: (\S+)", body, re.M)
            if not m or not ns:
                continue
            kind, name = m.groups()
            if not flux_resource_ready(kind, name, ns.group(1)):
                continue
            note = (
                f"ops-board-reconcile: {kind}/{name} is Ready=True as of "
                f"{datetime.now(timezone.utc).isoformat()}. Archiving as resolved."
            )
        elif body.startswith("source: alertmanager"):
            key = _title_to_key(card["title"])
            if key is None or key in live_keys:
                continue
            note = (
                f"ops-board-reconcile: no matching active alert in Alertmanager "
                f"as of {datetime.now(timezone.utc).isoformat()} "
                f"(reconstructed key: {key}). Archiving as stale."
            )
        else:
            continue  # only ever touch alert/flux-sourced cards

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
