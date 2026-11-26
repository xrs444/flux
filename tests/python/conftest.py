"""Shared pytest setup: make the in-repo modules importable and stub required env vars.

The modules under test live in app directories (some with hyphenated names), not in an
installable package, so each is put on sys.path explicitly.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

for rel in (
    "apps/mcpjungle/custom-image/netbox-mcp-rw",
    "apps/mcpjungle/custom-image/scanopy-mcp-rw",
    "apps/observability/monitoring/firewalla-exporter",
):
    sys.path.insert(0, str(ROOT / rel))

# exporter.py reads these at import time.
os.environ.setdefault("FIREWALLA_MSP_ID", "example.firewalla.net")
os.environ.setdefault("FIREWALLA_MSP_TOKEN", "test-token")
