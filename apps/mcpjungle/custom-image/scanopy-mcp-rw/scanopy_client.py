#!/usr/bin/env python3
"""
Scanopy Client Library

REST client for Scanopy's API (https://scanopy.xrs444.net/api/v1/). Modeled directly on
netbox_client.py's NetBoxRestClient — same shape, adapted for real differences confirmed
live against the deployed instance:

  - Auth header is "Authorization: Bearer {token}" (a Scanopy User API Key), not NetBox's
    "Authorization: Token {token}".
  - Base path is "{url}/api/v1/{endpoint}", not NetBox's "{url}/api/{endpoint}".
  - Responses are wrapped: {"success": true, "data": [...]}. NetBox instead returns a bare
    list/dict with a "results" key for pagination. _unwrap() handles Scanopy's envelope.
  - IDs are UUID strings (e.g. "70680c92-9087-4427-a0b4-e1afd096891c"), not integers.

Only GET was verified live against the real deployment while building this (see
flux/apps/services/scanopy/ for the deployed instance). Whether create/update/delete/bulk
responses use the same {"success", "data"} envelope was NOT verified — _unwrap() is written
defensively (falls back to the raw parsed JSON if there's no "data" key) specifically because
of that gap. Whether Scanopy's API supports bulk operations at all (the /bulk/ suffix
convention below is copied from NetBox/DRF, not confirmed against Scanopy's own docs) is
also unverified — expect the bulk_* methods to need adjustment once actually exercised.
"""

from typing import Any, Dict, List, Optional, Union
import requests


class ScanopyRestClient:
    """
    Scanopy client implementation using the REST API.

    Example:
        client = ScanopyRestClient(url="https://scanopy.xrs444.net", token="scp_u_...")
        hosts = client.get("hosts", params={"limit": 10})
        host = client.get("hosts", id="70680c92-9087-4427-a0b4-e1afd096891c")
        new_tag = client.create("tags", {"name": "verified"})
    """

    def __init__(self, url: str, token: str, verify_ssl: bool = True):
        """
        Args:
            url: Base URL of the Scanopy instance (e.g. "https://scanopy.xrs444.net")
            token: Scanopy User API Key (Bearer token)
            verify_ssl: Whether to verify TLS certificates (Scanopy runs a real Let's
                Encrypt cert here, unlike some other self-hosted apps in this infra that
                need this set to False for self-signed certs — leave True)
        """
        self.base_url = url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self.token = token
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _build_url(self, endpoint: str, id: Optional[str] = None) -> str:
        """Build the full URL for an API request."""
        endpoint = endpoint.strip("/")
        if id is not None:
            return f"{self.api_url}/{endpoint}/{id}"
        return f"{self.api_url}/{endpoint}"

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        """
        Unwrap Scanopy's {"success": true, "data": ...} response envelope.
        Falls back to the raw parsed JSON if it doesn't look like that shape, since only
        GET responses were verified live to use this envelope — see module docstring.
        """
        if isinstance(payload, dict) and "data" in payload and "success" in payload:
            return payload["data"]
        return payload

    def get(
        self,
        endpoint: str,
        id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Retrieve one or more objects from Scanopy via the REST API."""
        url = self._build_url(endpoint, id)
        response = self.session.get(url, params=params, verify=self.verify_ssl)
        response.raise_for_status()
        return self._unwrap(response.json())

    def create(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new object in Scanopy via the REST API."""
        url = self._build_url(endpoint)
        response = self.session.post(url, json=data, verify=self.verify_ssl)
        response.raise_for_status()
        return self._unwrap(response.json())

    def update(self, endpoint: str, id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing object in Scanopy via the REST API (partial update)."""
        url = self._build_url(endpoint, id)
        response = self.session.patch(url, json=data, verify=self.verify_ssl)
        response.raise_for_status()
        return self._unwrap(response.json())

    def delete(self, endpoint: str, id: str) -> bool:
        """Delete an object from Scanopy via the REST API."""
        url = self._build_url(endpoint, id)
        response = self.session.delete(url, verify=self.verify_ssl)
        response.raise_for_status()
        return response.status_code in (200, 204)

    def bulk_create(self, endpoint: str, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create multiple objects in Scanopy via the REST API.
        UNVERIFIED: whether Scanopy's API actually supports a /bulk/ endpoint at all — this
        mirrors NetBox/DRF convention, not something confirmed against Scanopy's own docs.
        """
        url = f"{self._build_url(endpoint)}/bulk"
        response = self.session.post(url, json=data, verify=self.verify_ssl)
        response.raise_for_status()
        return self._unwrap(response.json())

    def bulk_update(self, endpoint: str, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Update multiple objects in Scanopy via the REST API. UNVERIFIED, see bulk_create."""
        url = f"{self._build_url(endpoint)}/bulk"
        response = self.session.patch(url, json=data, verify=self.verify_ssl)
        response.raise_for_status()
        return self._unwrap(response.json())

    def bulk_delete(self, endpoint: str, ids: List[str]) -> bool:
        """Delete multiple objects from Scanopy via the REST API. UNVERIFIED, see bulk_create."""
        url = f"{self._build_url(endpoint)}/bulk"
        data = [{"id": id} for id in ids]
        response = self.session.delete(url, json=data, verify=self.verify_ssl)
        response.raise_for_status()
        return response.status_code in (200, 204)
