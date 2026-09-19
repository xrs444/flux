#!/bin/sh
# Bootstrap the kanban-safe profile — a locked-down fallback assignee for
# kanban.default_assignee (see KANBAN.md, bug-975). Not a Flux resource:
# hermes profiles are PVC-only state (/opt/data/profiles/<name>/), same as
# boards — this script is disaster-recovery documentation, what to re-run
# if the PVC is ever lost, not something Flux applies.
#
# Run from a shell with kubectl access:
#   kubectl -n hermes-t exec -it deploy/hermes-t -- sh < bootstrap-kanban-safe-profile.sh
#
# Uses the full /opt/hermes/.venv/bin/hermes path — see KANBAN.md's CLI
# note for why bare "hermes" is unsafe under kubectl exec.
#
# Why this profile exists: at least two independent hermes-agent code
# paths can hand a kanban card an assignee without a human explicitly
# choosing one (the dashboard's auto-specify-on-drag-to-triage, and the
# dispatcher's own default_assignee sweep of unassigned ready cards).
# Rather than chase every path that can reach ready+assigned, this
# profile ensures that even when one does, the resulting worker cannot
# do damage: agent.disabled_toolsets strips every dangerous built-in
# toolset, verified against the exact function the dispatcher uses to
# build a worker's --toolsets pin (hermes_cli.tools_config.
# _get_platform_tools) — NOT the `hermes tools list` display command,
# which does not reflect real restrictions. `toolsets:` (top-level) is
# purely additive and cannot restrict anything; `tools.allowed/denied`
# is dead (never parsed). agent.disabled_toolsets is the only key that
# actually works.

set -eu

HERMES=/opt/hermes/.venv/bin/hermes

$HERMES profile create kanban-safe --no-skills --description \
  "Restricted fallback assignee for auto-specified/auto-decomposed kanban tasks. Read-only observability + kanban lifecycle tools only -- no terminal, no mcpjungle, no cronjob/delegation/computer_use. Exists so an unexpected auto-assignment can never do more than read state and comment/complete a card."

$HERMES -p kanban-safe config set model.default qwen3-30b-a3b
$HERMES -p kanban-safe config set model.provider custom
$HERMES -p kanban-safe config set model.base_url http://xcog1.lan:4000/v1
$HERMES -p kanban-safe config set model.api_key '${LITELLM_MASTER_KEY}'

# agent.disabled_toolsets and mcp_servers aren't settable via `config set`
# for nested/dict values in one shot -- edit the profile's config.yaml
# directly. This mirrors exactly what was applied live 2026-09-19.
python3 - <<'PY'
import yaml
path = "/opt/data/profiles/kanban-safe/config.yaml"
with open(path) as f:
    cfg = yaml.safe_load(f) or {}

cfg.setdefault("agent", {})
cfg["agent"]["disabled_toolsets"] = [
    "web", "browser", "terminal", "file", "code_execution", "vision",
    "image_gen", "tts", "skills", "todo", "session_search", "clarify",
    "delegation", "cronjob", "computer_use", "connections",
]

cfg["mcp_servers"] = {
    "mcp-loki": {"url": "http://mcp-loki.mcp-tools.svc.cluster.local:8080/mcp", "enabled": True},
    "mcp-prometheus": {"url": "http://mcp-prometheus.mcp-tools.svc.cluster.local:8080/mcp", "enabled": True},
    "mcp-kubernetes": {"url": "http://mcp-kubernetes.mcp-tools.svc.cluster.local:8080/mcp", "enabled": True},
}

with open(path, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
print("kanban-safe: agent.disabled_toolsets + mcp_servers written")
PY

echo "=== verify: resolved CLI toolsets should be exactly kanban, memory, mcp-loki, mcp-prometheus, mcp-kubernetes ==="
python3 - <<'PY'
import sys
sys.path.insert(0, "/opt/hermes")
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools

token = set_hermes_home_override("/opt/data/profiles/kanban-safe")
try:
    cfg = load_config()
    toolsets = sorted(_get_platform_tools(cfg, "cli"))
    print("resolved CLI toolsets:", toolsets)
    dangerous = {"terminal", "code_execution", "computer_use", "delegation", "cronjob", "browser"}
    leaked = dangerous & set(toolsets)
    print("DANGEROUS TOOLS PRESENT:" , leaked if leaked else "none")
finally:
    reset_hermes_home_override(token)
PY
