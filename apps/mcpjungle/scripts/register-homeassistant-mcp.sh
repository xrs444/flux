#!/usr/bin/env bash
#
# (Re-)registers the "homeassistant" stdio MCP server in mcpjungle.
#
# Why this exists: mcpjungle server registration is imperative state living
# in mcpjungle's own SQLite DB on its PVC, not a Kubernetes object Flux can
# reconcile (see the comment block in ../deployment-mcpjungle.yaml and
# ../sealedsecret-homeassistant-mcp-credentials.yaml). If that PVC is ever
# lost/reset, or Home Assistant's native MCP Server integration changes its
# tool-naming scheme again (already happened once — flat names like
# "GetDateTime" became domain-namespaced ones like "llm__GetDateTime" between
# HA versions), this script re-runs the fix without having to reconstruct it
# from scratch. Safe to re-run any time: `register --force` deregisters any
# existing "homeassistant" entry first.
#
# Does NOT touch mcp-client --allow lists — that's a separate one-time step,
# see the sealed secret's comment block if a client ever needs re-granting.

set -o errexit
set -o pipefail
set -o nounset

namespace="mcp-gateway"
secret_name="sealedsecret-homeassistant-mcp-credentials"

pod="$(kubectl get pod -n "$namespace" -l app=mcpjungle -o jsonpath='{.items[0].metadata.name}')"
if [[ -z "$pod" ]]; then
  echo "ERROR - no mcpjungle pod found in namespace $namespace" >&2
  exit 1
fi

token="$(kubectl get secret "$secret_name" -n "$namespace" -o jsonpath='{.data.token}' | base64 -d)"
if [[ -z "$token" ]]; then
  echo "ERROR - could not read token from secret $secret_name" >&2
  exit 1
fi

local_conf="$(mktemp)"
trap 'rm -f "$local_conf"' EXIT

cat > "$local_conf" <<EOF
{
  "name": "homeassistant",
  "transport": "stdio",
  "description": "Home Assistant (hass.xrs444.net) native MCP Server integration, bridged SSE→stdio via supergateway (mcpjungle 0.4.6 does not proxy sse upstreams live — see github.com/mcpjungle/MCPJungle#100)",
  "command": "npx",
  "args": ["-y", "supergateway", "--sse", "https://hass.xrs444.net/mcp_server/sse", "--oauth2Bearer", "$token"],
  "env": {}
}
EOF

remote_conf="/tmp/homeassistant-mcp-register.json"
echo "INFO - copying config into pod $pod"
kubectl cp "$local_conf" "$namespace/$pod:$remote_conf"

echo "INFO - registering homeassistant server (--force)"
kubectl exec -n "$namespace" "deploy/mcpjungle" -- /mcpjungle register -c "$remote_conf" --force

kubectl exec -n "$namespace" "deploy/mcpjungle" -- rm -f "$remote_conf"

echo "INFO - done. Verify with:"
echo "  kubectl exec -n $namespace deploy/mcpjungle -- /mcpjungle invoke homeassistant__llm__GetDateTime"
