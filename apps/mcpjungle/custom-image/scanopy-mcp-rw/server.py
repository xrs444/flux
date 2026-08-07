from mcp.server.fastmcp import FastMCP
from scanopy_client import ScanopyRestClient
import os

# Mapping of simple object names to Scanopy API endpoints. Unlike NetBox (grouped under
# dcim/ipam/etc. app prefixes), Scanopy's API is flat under /api/v1/ — the endpoint is just
# the resource name itself. Confirmed against Scanopy's own source tree
# (backend/src/server/) and published API docs (scanopy.net/docs/api/).
SCANOPY_OBJECT_TYPES = {
    "credentials": "credentials",
    "daemons": "daemons",
    "dependencies": "dependencies",
    "hosts": "hosts",
    "interfaces": "interfaces",
    "invites": "invites",
    "ip-addresses": "ip-addresses",
    "networks": "networks",
    "organizations": "organizations",
    "ports": "ports",
    "services": "services",
    "shares": "shares",
    "snapshots": "snapshots",
    "subnets": "subnets",
    "tags": "tags",
    "topologies": "topologies",
    "users": "users",
    "vlans": "vlans",
}

# Writable subset — deliberately excludes "credentials" (SNMP community strings / SSH keys
# used for authenticated scans). Readable via scanopy_get_objects/get_object_by_id, but
# never created/updated/deleted/bulk-modified through this MCP: an LLM shouldn't be minting
# or rotating scan secrets. Every create/update/delete/bulk_* tool below validates against
# this map, not the full SCANOPY_OBJECT_TYPES map.
SCANOPY_WRITABLE_TYPES = {
    k: v for k, v in SCANOPY_OBJECT_TYPES.items() if k != "credentials"
}

mcp = FastMCP("Scanopy", log_level="DEBUG")
scanopy = None


def _valid_types_message(types: dict) -> str:
    valid = "\n".join(f"- {t}" for t in sorted(types.keys()))
    return f"Invalid object_type. Must be one of:\n{valid}"


@mcp.tool()
def scanopy_get_objects(object_type: str, filters: dict):
    """
    Get objects from Scanopy based on their type and filters.

    Args:
        object_type: String representing the Scanopy object type (e.g. "hosts", "vlans")
        filters: dict of filters/query params to apply (e.g. {"limit": 50, "offset": 0}).
            Scanopy paginates with limit (default 50, max 1000, 0 = no limit) and offset
            (default 0).

    Valid object_type values:
    - credentials  (SNMP/SSH credentials used for authenticated scans — read-only here)
    - daemons      (scanning daemon status, e.g. the xfw daemon)
    - dependencies (service/host dependency edges)
    - hosts        (discovered hosts — name, MACs, IPs, tags)
    - interfaces
    - invites
    - ip-addresses
    - networks
    - organizations
    - ports
    - services     (discovered services per host)
    - shares
    - snapshots    (point-in-time topology data)
    - subnets
    - tags
    - topologies   (link/dependency graph data)
    - users
    - vlans        (auto-detected from observed 802.1Q tags)

    See https://scanopy.net/docs/api/ for filtering options per object type.
    """
    if object_type not in SCANOPY_OBJECT_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_OBJECT_TYPES))

    endpoint = SCANOPY_OBJECT_TYPES[object_type]
    return scanopy.get(endpoint, params=filters)


@mcp.tool()
def scanopy_get_object_by_id(object_type: str, object_id: str):
    """
    Get detailed information about a specific Scanopy object by its ID.

    Args:
        object_type: String representing the Scanopy object type (e.g. "hosts", "vlans")
        object_id: The object's UUID string (Scanopy IDs are UUIDs, not integers — e.g.
            "70680c92-9087-4427-a0b4-e1afd096891c")

    Returns:
        Complete object details
    """
    if object_type not in SCANOPY_OBJECT_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_OBJECT_TYPES))

    endpoint = SCANOPY_OBJECT_TYPES[object_type]
    return scanopy.get(endpoint, id=object_id)


@mcp.tool()
def scanopy_create_object(object_type: str, data: dict):
    """
    Create a new object in Scanopy.

    Args:
        object_type: String representing the Scanopy object type. Does NOT include
            "credentials" — that resource is read-only through this MCP (see
            scanopy_get_objects for the full readable list; this tool's valid types are a
            subset of it).
        data: Dict containing the object data to create

    Returns:
        The created object as a dict

    Example:
    To tag a host as verified:
    scanopy_create_object("tags", {"name": "verified"})
    """
    if object_type not in SCANOPY_WRITABLE_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_WRITABLE_TYPES))

    endpoint = SCANOPY_WRITABLE_TYPES[object_type]
    return scanopy.create(endpoint, data)


@mcp.tool()
def scanopy_update_object(object_type: str, object_id: str, data: dict):
    """
    Update an existing object in Scanopy (partial update — only changed fields needed).

    Args:
        object_type: String representing the Scanopy object type (excludes "credentials",
            see scanopy_create_object)
        object_id: The UUID string of the object to update
        data: Dict containing the fields to update

    Returns:
        The updated object as a dict

    Example:
    To rename a host:
    scanopy_update_object("hosts", "70680c92-9087-4427-a0b4-e1afd096891c", {"name": "xfw-daemon"})
    """
    if object_type not in SCANOPY_WRITABLE_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_WRITABLE_TYPES))

    endpoint = SCANOPY_WRITABLE_TYPES[object_type]
    return scanopy.update(endpoint, object_id, data)


@mcp.tool()
def scanopy_delete_object(object_type: str, object_id: str):
    """
    Delete an object from Scanopy.

    Args:
        object_type: String representing the Scanopy object type (excludes "credentials",
            see scanopy_create_object)
        object_id: The UUID string of the object to delete

    Returns:
        Success status

    WARNING: This permanently deletes the object and cannot be undone!
    """
    if object_type not in SCANOPY_WRITABLE_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_WRITABLE_TYPES))

    endpoint = SCANOPY_WRITABLE_TYPES[object_type]
    success = scanopy.delete(endpoint, object_id)

    if success:
        return {"success": True, "message": f"Successfully deleted {object_type} with ID {object_id}"}
    else:
        return {"success": False, "message": f"Failed to delete {object_type} with ID {object_id}"}


@mcp.tool()
def scanopy_bulk_create_objects(object_type: str, data: list):
    """
    Create multiple objects in Scanopy in a single request.
    UNVERIFIED: whether Scanopy's API actually supports bulk endpoints — see
    scanopy_client.py's module docstring. Try scanopy_create_object in a loop if this fails.

    Args:
        object_type: String representing the Scanopy object type (excludes "credentials")
        data: List of dicts containing the object data to create
    """
    if object_type not in SCANOPY_WRITABLE_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_WRITABLE_TYPES))

    endpoint = SCANOPY_WRITABLE_TYPES[object_type]
    return scanopy.bulk_create(endpoint, data)


@mcp.tool()
def scanopy_bulk_update_objects(object_type: str, data: list):
    """
    Update multiple objects in Scanopy in a single request. UNVERIFIED, see
    scanopy_bulk_create_objects.

    Args:
        object_type: String representing the Scanopy object type (excludes "credentials")
        data: List of dicts containing the object data to update (must include "id")
    """
    if object_type not in SCANOPY_WRITABLE_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_WRITABLE_TYPES))

    endpoint = SCANOPY_WRITABLE_TYPES[object_type]
    return scanopy.bulk_update(endpoint, data)


@mcp.tool()
def scanopy_bulk_delete_objects(object_type: str, object_ids: list):
    """
    Delete multiple objects from Scanopy in a single request. UNVERIFIED, see
    scanopy_bulk_create_objects.

    Args:
        object_type: String representing the Scanopy object type (excludes "credentials")
        object_ids: List of UUID strings to delete

    WARNING: This permanently deletes the objects and cannot be undone!
    """
    if object_type not in SCANOPY_WRITABLE_TYPES:
        raise ValueError(_valid_types_message(SCANOPY_WRITABLE_TYPES))

    endpoint = SCANOPY_WRITABLE_TYPES[object_type]
    success = scanopy.bulk_delete(endpoint, object_ids)

    if success:
        return {"success": True, "message": f"Successfully deleted {len(object_ids)} {object_type} objects"}
    else:
        return {"success": False, "message": f"Failed to delete {object_type} objects"}


if __name__ == "__main__":
    scanopy_url = os.getenv("SCANOPY_URL")
    scanopy_token = os.getenv("SCANOPY_TOKEN")

    if not scanopy_url or not scanopy_token:
        raise ValueError("SCANOPY_URL and SCANOPY_TOKEN environment variables must be set")

    scanopy = ScanopyRestClient(url=scanopy_url, token=scanopy_token)

    mcp.run(transport="stdio")
