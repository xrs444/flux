#!/usr/bin/env bash
# hermes cron --monitor-script source for GitHub Actions failure watching
# across both xrs444/nix and xrs444/flux. Not deployed by Flux — cron jobs
# and their scripts live on hermes-t's PVC (/opt/data/scripts/), same as
# boards/profiles. See KANBAN.md for the one-time install + `hermes cron
# create` invocation.
#
# Monitor-script contract (hermes cron create --monitor-script): stdout is
# hashed byte-exact between ticks — unchanged output suppresses the agent
# run entirely, changed output injects a diff into the agent's prompt. So
# this MUST print nothing that varies between ticks unless the actual set
# of failing runs changed (no timestamps, no run URLs with query params,
# stable sort order).
#
# `nix/` and `flux/` are separate GitHub repos with their own remotes (see
# .infrastructure-reference.md) — both queried here regardless of which
# repo is currently checked out, since this runs unattended on a schedule.
#
# Auth: unauthenticated GitHub API calls are rate-limited to 60/hr, which
# comfortably covers 2 repos every 30 minutes. If xrs444/nix or xrs444/flux
# are private, set GITHUB_TOKEN in this script's environment (there is no
# per-job env-var option in `hermes cron create` today — bake it into a
# copy of this script on the PVC, or export it before curl below).

set -euo pipefail

REPOS=("xrs444/nix" "xrs444/flux")

for repo in "${REPOS[@]}"; do
  auth_header=()
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    auth_header=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
  fi
  curl -s "${auth_header[@]}" \
    "https://api.github.com/repos/${repo}/actions/runs?status=failure&per_page=10" \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
runs = data.get('workflow_runs', [])
lines = []
for r in runs:
    lines.append(f\"${repo} | {r.get('name','?')} | run {r.get('run_number','?')} | {r.get('conclusion','?')} | branch {r.get('head_branch','?')}\")
for line in sorted(lines):
    print(line)
"
done
