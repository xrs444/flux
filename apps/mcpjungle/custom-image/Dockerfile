# Custom MCPJungle image with netbox-mcp-rw's and scanopy-mcp-rw's source baked
# in as stdio backends. No code change to either is needed at runtime —
# MCPJungle spawns each directly via `uv run server.py` (transport=stdio), the
# same way netbox-mcp-rw is invoked locally today (run-netbox-mcp.sh). Base
# image already ships uv/uvx/npx/node/python3 (Debian trixie), so
# arr/homeassistant/jellyfin (npx-based) don't need this custom image at all —
# only servers whose source isn't part of the upstream mcpjungle image do.
#
# netbox-mcp-rw source: vendored copy of https://github.com/alexkiwi1/netbox-mcp-rw
# (a fork of netboxlabs/netbox-mcp-server with write/CRUD tools added).
#
# scanopy-mcp-rw source: original code, written for this infra — no upstream
# Scanopy MCP server exists anywhere to vendor from.
#
# nodered-mcp-rw source: vendored + patched copy of
# https://github.com/karavaev-evgeniy/node-red-mcp-server. Patched because
# the HA "Node-RED" add-on (hassio-addons/addon-node-red, auth_api: true) has
# no native adminAuth/token — its direct-access admin API is gated by an
# nginx front door doing HTTP Basic Auth against real Home Assistant user
# credentials (WWW-Authenticate: Basic realm="Home Assistant Authentication").
# Upstream only ever sends `Authorization: Bearer <token>`, which that front
# door rejects. See lib/utils.mjs buildAuthHeaders/buildHttpsAgent for the
# patch (adds NODE_RED_USERNAME/NODE_RED_PASSWORD Basic-auth support, plus an
# opt-in NODE_RED_INSECURE_TLS since the add-on's direct-access cert was
# found expired 2026-08-29 — fix the cert, don't lean on that flag).
FROM ghcr.io/mcpjungle/mcpjungle:0.4.6-stdio

COPY netbox-mcp-rw /opt/netbox-mcp-rw
RUN cd /opt/netbox-mcp-rw && uv sync --frozen

COPY scanopy-mcp-rw /opt/scanopy-mcp-rw
RUN cd /opt/scanopy-mcp-rw && uv sync --frozen

COPY nodered-mcp-rw /opt/nodered-mcp-rw
RUN cd /opt/nodered-mcp-rw && npm install --omit=dev
