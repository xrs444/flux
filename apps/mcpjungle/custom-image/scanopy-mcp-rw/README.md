# Scanopy MCP Server (read/write)

Custom-built MCP server for [Scanopy](https://scanopy.net) — the self-hosted network
discovery/topology tool deployed at `flux/apps/services/scanopy/`. No upstream to vendor from
(no off-the-shelf Scanopy MCP server exists anywhere) — this is original code, modeled
directly on the shape of `../netbox-mcp-rw/` (the only other self-built MCP server in this
infra): one generic tool set covering every Scanopy resource type via a `object_type`
parameter, rather than a named tool per resource.

Built to let Claude cross-reference Scanopy's live-discovered network inventory (hosts,
VLANs, subnets, services, topology) against NetBox (`netbox-mcp-rw`) and
Firewalla/Omada (`mcp-firewalla`/`mcp-omada`) to find and fix drift between documented and
actual network state.

## Tools

- `scanopy_get_objects(object_type, filters)` — list/filter any resource type
- `scanopy_get_object_by_id(object_type, object_id)` — fetch one object by its UUID
- `scanopy_create_object(object_type, data)` — create
- `scanopy_update_object(object_type, object_id, data)` — partial update
- `scanopy_delete_object(object_type, object_id)` — delete
- `scanopy_bulk_create_objects` / `scanopy_bulk_update_objects` / `scanopy_bulk_delete_objects`
  — bulk variants (unverified against the real API — see `scanopy_client.py`'s docstring)

Valid `object_type` values: `credentials`, `daemons`, `dependencies`, `hosts`, `interfaces`,
`invites`, `ip-addresses`, `networks`, `organizations`, `ports`, `services`, `shares`,
`snapshots`, `subnets`, `tags`, `topologies`, `users`, `vlans`.

**`credentials` is read-only** — it holds SNMP community strings / SSH keys used for
authenticated scans. Every write tool (`create`/`update`/`delete`/`bulk_*`) validates against
a `SCANOPY_WRITABLE_TYPES` map that excludes it; an LLM shouldn't be minting or rotating scan
secrets. Everything else is full read/write.

## Configuration

Reads two environment variables at startup:

- `SCANOPY_URL` — e.g. `https://scanopy.xrs444.net`
- `SCANOPY_TOKEN` — a Scanopy **User API Key** (`Bearer` auth, format `scp_u_...`), minted in
  the Scanopy UI under Platform → API Keys. Scanopy doesn't support scoped/limited keys —
  any User API Key is full-account access, so use a key dedicated to this MCP server (not a
  personal admin key) purely so it's independently rotatable, not because it's lower
  privilege.

## Deployment

Vendored into the shared MCPJungle gateway image
(`flux/apps/mcpjungle/custom-image/Dockerfile`) alongside `netbox-mcp-rw`, built by
`.github/workflows/build-mcpjungle-image.yml`, and registered as a **stdio** upstream that
the `mcpjungle` pod spawns itself — no separate Kubernetes Deployment/Service, no pod-level
env vars on the gateway. `SCANOPY_URL`/`SCANOPY_TOKEN` are injected entirely at
`mcpjungle register` time.

See `flux/apps/mcpjungle/sealedsecret-scanopy-mcp-credentials.yaml`'s header comment for the
exact registration command — written down deliberately, since `netbox-mcp-rw`'s own
registration params are undocumented anywhere in this repo (a real gap: if the `mcpjungle`
PVC is ever rebuilt, there's nothing recorded to re-register it from).

## Local testing

```bash
SCANOPY_URL=https://scanopy.xrs444.net SCANOPY_TOKEN=scp_u_... uv run server.py
```
