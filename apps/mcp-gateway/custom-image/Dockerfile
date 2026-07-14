# Custom MCPJungle image with netbox-mcp-rw's source baked in as a stdio
# backend. No code change to netbox-mcp-rw itself is needed — MCPJungle
# spawns it directly via `uv run server.py` (transport=stdio), the same way
# it's invoked locally today (run-netbox-mcp.sh). Base image already ships
# uv/uvx/npx/node/python3 (Debian trixie), so arr/homeassistant/jellyfin
# (npx-based) don't need this custom image at all — only netbox-mcp-rw does,
# since its source isn't part of the upstream mcpjungle image.
#
# netbox-mcp-rw source: vendored copy of https://github.com/alexkiwi1/netbox-mcp-rw
# (a fork of netboxlabs/netbox-mcp-server with write/CRUD tools added).
FROM ghcr.io/mcpjungle/mcpjungle:0.4.5-stdio

COPY netbox-mcp-rw /opt/netbox-mcp-rw
RUN cd /opt/netbox-mcp-rw && uv sync --frozen
