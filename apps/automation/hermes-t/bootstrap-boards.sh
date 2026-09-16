#!/bin/sh
# Bootstrap the two Hermes-T Kanban boards. Not a Flux resource — boards and
# profiles live on hermes-t's PVC (/opt/data/kanban/boards/<slug>/), not in
# git, so this script is disaster-recovery documentation: what to re-run if
# the PVC is ever lost, not something Flux applies. See KANBAN.md in this
# directory for the card conventions these boards assume.
#
# Run from a shell with kubectl access to the cluster:
#   kubectl -n hermes-t exec -it deploy/hermes-t -- sh < bootstrap-boards.sh
# or paste the two `hermes kanban boards create` lines directly into an
# `exec -it ... sh` session.
#
# Uses the full /opt/hermes/.venv/bin/hermes path, not bare "hermes" —
# kubectl exec's PATH resolves bare "hermes" to /opt/hermes/bin/hermes
# first, a privilege-drop shim that switches to the hermes user, whose
# home dir (/opt/data) gets clamped to mode 700 (no group bits) sometime
# after pod boot, breaking the shim's own .env read. Verified live
# 2026-09-16 — this exact bug is why the first live run of this pattern
# (via migrate-security-backlog.py) failed on every card.

set -eu

HERMES=/opt/hermes/.venv/bin/hermes

$HERMES kanban boards create ops \
  --name "HomeProd Ops" \
  --description "Alerts, CI failures, incidents — fed by Alertmanager, GitHub Actions, Flux notification-controller" \
  --icon "🚨" \
  --color "#ef4444"

$HERMES kanban boards create projects \
  --name "HomeProd Projects" \
  --description "User-entered work, upgrades, migrated security backlog — held until actioned" \
  --icon "🛠" \
  --color "#8b5cf6"

$HERMES kanban boards list
