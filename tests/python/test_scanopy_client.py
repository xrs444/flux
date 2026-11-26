"""ScanopyRestClient: envelope unwrapping, verbs, and the removed bulk-write surface."""
from unittest.mock import MagicMock

import pytest
import requests

from scanopy_client import ScanopyRestClient


def _client():
    c = ScanopyRestClient("https://scanopy.example.com/", "scp_u_tok")
    c.session = MagicMock()
    return c


def _resp(json_data=None, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return r


def test_init_uses_bearer_and_api_v1_base():
    c = ScanopyRestClient("https://scanopy.example.com/", "tok")
    assert c.api_url == "https://scanopy.example.com/api/v1"
    assert c.session.headers["Authorization"] == "Bearer tok"


def test_build_url_has_no_trailing_slash():
    c = _client()
    assert c._build_url("hosts") == "https://scanopy.example.com/api/v1/hosts"
    assert c._build_url("/hosts/", "abc") == "https://scanopy.example.com/api/v1/hosts/abc"


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"success": True, "data": [1, 2]}, [1, 2]),
        ({"success": True, "data": {"id": "x"}}, {"id": "x"}),
        ({"id": "x"}, {"id": "x"}),  # not an envelope -> returned as-is
        ({"data": [1]}, {"data": [1]}),  # "data" without "success" is not an envelope
        ([1, 2], [1, 2]),
    ],
)
def test_unwrap(payload, expected):
    assert ScanopyRestClient._unwrap(payload) == expected


def test_get_unwraps_envelope():
    c = _client()
    c.session.get.return_value = _resp({"success": True, "data": [{"id": "h1"}]})
    assert c.get("hosts", params={"limit": 1}) == [{"id": "h1"}]


def test_update_uses_patch():
    c = _client()
    c.session.patch.return_value = _resp({"success": True, "data": {"id": "h1"}})
    assert c.update("hosts", "h1", {"name": "n"}) == {"id": "h1"}
    c.session.patch.assert_called_once()


@pytest.mark.parametrize("status,expected", [(200, True), (204, True), (202, False)])
def test_delete_status_mapping(status, expected):
    c = _client()
    c.session.delete.return_value = _resp(None, status)
    assert c.delete("hosts", "h1") is expected


def test_http_error_propagates():
    c = _client()
    c.session.get.return_value = _resp(None, 403)
    with pytest.raises(requests.HTTPError):
        c.get("hosts")


def test_bulk_writes_stay_removed():
    """Guard: bulk_* were removed because the /bulk/ API shape was never verified
    (2026-11-07 security review). Re-adding them must be a deliberate change."""
    for name in ("bulk_create", "bulk_update", "bulk_delete"):
        assert not hasattr(ScanopyRestClient, name)
