"""NetBoxRestClient: URL building, response unwrapping, and error propagation."""
from unittest.mock import MagicMock

import pytest
import requests

from netbox_client import NetBoxRestClient


def _client():
    c = NetBoxRestClient("https://netbox.example.com/", "tok")
    c.session = MagicMock()
    return c


def _resp(json_data=None, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return r


def test_init_strips_trailing_slash_and_sets_token_header():
    c = NetBoxRestClient("https://netbox.example.com/", "abc")
    assert c.api_url == "https://netbox.example.com/api"
    assert c.session.headers["Authorization"] == "Token abc"


@pytest.mark.parametrize(
    "endpoint,id_,expected",
    [
        ("dcim/sites", None, "https://netbox.example.com/api/dcim/sites/"),
        ("/dcim/sites/", None, "https://netbox.example.com/api/dcim/sites/"),
        ("dcim/sites", 7, "https://netbox.example.com/api/dcim/sites/7/"),
    ],
)
def test_build_url(endpoint, id_, expected):
    assert _client()._build_url(endpoint, id_) == expected


def test_get_list_unwraps_paginated_results():
    c = _client()
    c.session.get.return_value = _resp({"count": 2, "results": [{"id": 1}, {"id": 2}]})
    assert c.get("dcim/sites") == [{"id": 1}, {"id": 2}]


def test_get_by_id_returns_object_not_unwrapped():
    c = _client()
    c.session.get.return_value = _resp({"id": 5, "results": "not-a-list-wrapper"})
    assert c.get("dcim/sites", id=5)["id"] == 5


def test_get_passes_params_and_verify():
    c = NetBoxRestClient("https://n", "t", verify_ssl=False)
    c.session = MagicMock()
    c.session.get.return_value = _resp({"results": []})
    c.get("dcim/sites", params={"name": "home"})
    _, kwargs = c.session.get.call_args
    assert kwargs["params"] == {"name": "home"}
    assert kwargs["verify"] is False


def test_create_posts_json_and_returns_body():
    c = _client()
    c.session.post.return_value = _resp({"id": 9}, 201)
    assert c.create("dcim/sites", {"name": "x"}) == {"id": 9}
    c.session.post.assert_called_once()
    assert c.session.post.call_args.kwargs["json"] == {"name": "x"}


def test_delete_true_only_on_204():
    c = _client()
    c.session.delete.return_value = _resp(None, 204)
    assert c.delete("dcim/sites", 1) is True
    c.session.delete.return_value = _resp(None, 200)
    assert c.delete("dcim/sites", 1) is False


@pytest.mark.parametrize("method,args", [
    ("get", ("dcim/sites",)),
    ("create", ("dcim/sites", {})),
    ("update", ("dcim/sites", 1, {})),
    ("delete", ("dcim/sites", 1)),
])
def test_http_errors_propagate(method, args):
    c = _client()
    for verb in ("get", "post", "patch", "put", "delete"):
        getattr(c.session, verb).return_value = _resp(None, 500)
    with pytest.raises(requests.HTTPError):
        getattr(c, method)(*args)
