# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Action items: incident-scoped vs. org-wide listing, and the invalid_argument guards. PRD-21240."""

import json

import httpx
import pytest

from rootly_mcp import api_client
from rootly_mcp.server import _credentials_var, create_mcp_server

CREDS = api_client.RootlyCredentials(api_token="tok-1")
INC = "a1b2c3d4-0000-0000-0000-000000000001"
AID = "a1b2c3d4-0000-0000-0000-000000000077"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


class Recorder:
    """Mock transport: replies by "METHOD path" or path below /v1/."""

    def __init__(self, routes=None, default=None):
        self.requests: list[httpx.Request] = []
        self.routes = routes or {}
        self.default = default if default is not None else {"data": [], "meta": {"total_count": 0, "total_pages": 1}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v1/")
        reply = self.routes.get(f"{request.method} {path}", self.routes.get(path, self.default))
        if callable(reply):
            return reply(request)
        return httpx.Response(200, json=reply)


def body(request: httpx.Request):
    return json.loads(request.content) if request.content else None


async def _call(monkeypatch, recorder: Recorder, tool: str, args: dict):
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    ctx = _credentials_var.set(CREDS)
    try:
        content, _ = await create_mcp_server().call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


async def test_incident_scoped_list_rejects_unsupported_filters(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "rootly_action_items_list", {"incident_id": INC, "status": "open"})
    assert result["error"]["code"] == "invalid_argument"
    assert "incident_id" in result["error"]["message"]
    assert not rec.requests  # the guard runs before any request


async def test_incident_scoped_list_uses_the_nested_endpoint(monkeypatch):
    rec = Recorder({f"GET incidents/{INC}/action_items": {"data": [], "meta": {}, "links": {}}})
    await _call(monkeypatch, rec, "rootly_action_items_list", {"incident_id": INC})
    assert rec.requests[0].url.path == f"/v1/incidents/{INC}/action_items"


async def test_org_wide_list_sends_the_given_filters(monkeypatch):
    rec = Recorder({"GET action_items": {"data": [], "meta": {"total_count": 0, "total_pages": 1}}})
    await _call(monkeypatch, rec, "rootly_action_items_list", {"status": "open", "priority": "high", "kind": "task"})
    params = rec.requests[0].url.params
    assert (params["filter[status]"], params["filter[priority]"], params["filter[kind]"]) == ("open", "high", "task")


async def test_create_without_summary_raises_invalid_argument(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "rootly_action_items_create", {"incident_id": INC, "summary": "   "})
    assert result["error"]["code"] == "invalid_argument"
    assert not rec.requests


async def test_create_posts_to_the_incident_scoped_endpoint(monkeypatch):
    rec = Recorder(
        {f"POST incidents/{INC}/action_items": {"data": {"id": AID, "type": "incident_action_items", "attributes": {"summary": "Add alert", "status": "open"}}}}
    )
    result = await _call(monkeypatch, rec, "rootly_action_items_create", {"incident_id": INC, "summary": "Add alert"})
    assert rec.requests[0].url.path == f"/v1/incidents/{INC}/action_items"
    assert body(rec.requests[0])["data"]["type"] == "incident_action_items"
    assert result["id"] == AID and result["status"] == "open"


async def test_update_with_nothing_to_update_raises_invalid_argument(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "rootly_action_items_update", {"action_item_id": AID})
    assert result["error"]["code"] == "invalid_argument"
    assert "Nothing to update" in result["error"]["message"]
    assert not rec.requests


async def test_update_marks_done(monkeypatch):
    rec = Recorder({f"PUT action_items/{AID}": {"data": {"id": AID, "type": "incident_action_items", "attributes": {"status": "done"}}}})
    result = await _call(monkeypatch, rec, "rootly_action_items_update", {"action_item_id": AID, "status": "done"})
    assert body(rec.requests[0])["data"]["attributes"] == {"status": "done"}
    assert result["status"] == "done"


async def test_get_nonexistent_returns_not_found(monkeypatch):
    rec = Recorder({f"GET action_items/{AID}": lambda r: httpx.Response(404, json={"errors": [{"title": "Not Found"}]})})
    result = await _call(monkeypatch, rec, "rootly_action_items_get", {"action_item_id": AID})
    assert result["error"]["code"] == "not_found"
