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

set -eu

hermes kanban boards create ops \
  --name "HomeProd Ops" \
  --description "Alerts, CI failures, incidents — fed by Alertmanager, GitHub Actions, Flux notification-controller" \
  --icon "🚨" \
  --color "#ef4444"

hermes kanban boards create projects \
  --name "HomeProd Projects" \
  --description "User-entered work, upgrades, migrated security backlog — held until actioned" \
  --icon "🛠" \
  --color "#8b5cf6"

hermes kanban boards list
