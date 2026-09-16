#!/usr/bin/env python3
"""One-time migration: .wolf/security-backlog.md open items -> `projects`
board cards. Not a Flux resource, not re-run on a schedule — a disaster-
recovery / setup script, same category as bootstrap-boards.sh.

Reuses the exact classification heuristic already established in
.claude/skills/security-backlog-triage.md (title-text-only, no semantic
parsing of body content):
  - title contains "RESOLVED" or "DONE"  -> closed, skip
  - title contains "DEFERRED"            -> open, lower urgency
  - no status suffix                     -> open, needs triage

Sections "DONE (reference)" and "LOW / INFO / REPORT-ONLY" are excluded
entirely — the file's own headings mark them non-actionable, so migrating
their items would just be noise on a fresh board.

Safe to re-run: every card is created with
--idempotency-key security-backlog:<ID>, so a partial run followed by a
second run creates nothing twice (hermes_cli/kanban_db.py's create_task()
does the dedup — see kanban_card_upsert.ts's header comment in
flux/windmill-workspace/f/sre/alert-ingest__flow/ for the same mechanism).

DRY RUN BY DEFAULT. Pass --apply to actually create cards. Review the
dry-run output before applying — this is a one-shot, hard-to-cleanly-
reverse write against a live board most people haven't used yet.

Usage:
    python3 migrate-security-backlog.py                  # dry run
    python3 migrate-security-backlog.py --apply           # create cards
    python3 migrate-security-backlog.py --file /path/to/security-backlog.md
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

EXCLUDED_SECTIONS = {"DONE (REFERENCE)", "LOW / INFO / REPORT-ONLY (DOCUMENTED, NO ACTION PLANNED)"}

# "### C2 — Seal seven plaintext Kubernetes Secrets"
# "### H2 — Narrow NFS `no_root_squash` grants — DONE (batch 1 + batch 2)"
# "### N3 + N4 + N5 + N7 + N8 + N9 + N10 — nix network hardening & cleanup bundle — DEFERRED"
ITEM_RE = re.compile(r"^###\s+(?P<id>[A-Z0-9-]+(?:\s*\+\s*[A-Z0-9-]+)*)\s+—\s+(?P<rest>.+)$")
SECTION_RE = re.compile(r"^##\s+(?P<name>.+)$")


def severity_priority(section_name: str) -> int:
    # Higher hermes priority = higher tiebreaker; matches the file's own
    # CRITICAL > HIGH > MEDIUM > LOW ordering used by security-backlog-triage.md.
    s = section_name.upper()
    if "CRITICAL" in s:
        return 30
    if "HIGH" in s:
        return 20
    if "MEDIUM" in s:
        return 10
    return 0


def parse_items(text: str) -> list[dict]:
    lines = text.splitlines()
    items = []
    current_section = ""
    current = None

    def flush():
        if current is not None:
            body = "\n".join(current["body_lines"]).strip()
            items.append({**current, "body": body})

    for line in lines:
        sec_m = SECTION_RE.match(line)
        if sec_m:
            flush()
            current = None
            current_section = sec_m.group("name").strip()
            continue
        item_m = ITEM_RE.match(line)
        if item_m:
            flush()
            current = {
                "id": item_m.group("id").strip(),
                "title": item_m.group("rest").strip(),
                "section": current_section,
                "body_lines": [],
            }
            continue
        if current is not None:
            current["body_lines"].append(line)
    flush()
    return items


def is_open(item: dict) -> bool:
    if item["section"].strip().upper() in EXCLUDED_SECTIONS:
        return False
    title_upper = item["title"].upper()
    if "RESOLVED" in title_upper or "DONE" in title_upper:
        return False
    return True


def hermes_kanban(args: list[str], dry_run: bool) -> subprocess.CompletedProcess | None:
    # Full path, not bare "hermes" — kubectl exec (no shell) resolves PATH to
    # /opt/hermes/bin/hermes first, a "docker exec privilege-drop shim" that
    # switches to the hermes user, whose home dir (/opt/data) gets clamped to
    # mode 700 (no group bits) sometime after pod boot. The .venv path
    # bypasses the shim and runs as whatever identity invoked kubectl exec.
    # Verified live 2026-09-16 — this exact bug caused every create call in
    # the first --apply run to fail.
    cmd = [
        "kubectl", "-n", "hermes-t", "exec", "deploy/hermes-t", "--",
        "/opt/hermes/.venv/bin/hermes", "kanban", "--board", "projects", *args,
    ]
    if dry_run:
        print("  [dry-run] " + " ".join(repr(c) if " " in c else c for c in cmd))
        return None
    return subprocess.run(cmd, capture_output=True, text=True, timeout=90)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=str(Path(__file__).resolve().parents[4] / ".wolf" / "security-backlog.md"))
    ap.add_argument("--apply", action="store_true", help="Actually create cards (default: dry run)")
    args = ap.parse_args()

    backlog_path = Path(args.file)
    text = backlog_path.read_text(encoding="utf-8")
    items = parse_items(text)
    open_items = [i for i in items if is_open(i)]

    print(f"Parsed {len(items)} total items, {len(open_items)} open (non-RESOLVED/DONE, "
          f"non-reference-section) — migrating these to `projects`.\n")

    for item in open_items:
        title = f"{item['id']} — {item['title']}"
        idempotency_key = f"security-backlog:{item['id']}"
        priority = severity_priority(item["section"])
        print(f"[{item['section']}] {title}")
        result = hermes_kanban(
            [
                "create", title,
                "--body", item["body"],
                "--priority", str(priority),
                "--idempotency-key", idempotency_key,
                "--created-by", "security-backlog-migration",
                "--json",
            ],
            dry_run=not args.apply,
        )
        if result is not None and result.returncode != 0:
            print(f"  FAILED: {result.stderr.strip()}", file=sys.stderr)

    if not args.apply:
        print("\nDry run only — no cards created. Re-run with --apply once you've reviewed the "
              "list above and the `projects` board exists (see bootstrap-boards.sh).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
