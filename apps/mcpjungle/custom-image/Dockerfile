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
FROM ghcr.io/mcpjungle/mcpjungle:0.4.6-stdio

COPY netbox-mcp-rw /opt/netbox-mcp-rw
RUN cd /opt/netbox-mcp-rw && uv sync --frozen

COPY scanopy-mcp-rw /opt/scanopy-mcp-rw
RUN cd /opt/scanopy-mcp-rw && uv sync --frozen
