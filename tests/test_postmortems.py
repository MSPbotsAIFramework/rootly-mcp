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
"""Post-mortems: not_found / conflict mappings and the "nothing to update" guard. PRD-21240."""

import json

import httpx
import pytest

from rootly_mcp import api_client
from rootly_mcp.server import _credentials_var, create_mcp_server

CREDS = api_client.RootlyCredentials(api_token="tok-1")
PID = "a1b2c3d4-0000-0000-0000-000000000099"


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


def _not_found(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404, json={"errors": [{"title": "Not Found", "detail": "Couldn't find PostMortem"}]})


def _conflict(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        409,
        json={"errors": [{"title": "Conflict", "detail": "This retrospective is currently being edited in the collaborative editor"}]},
    )


async def test_get_nonexistent_returns_not_found(monkeypatch):
    rec = Recorder({f"GET post_mortems/{PID}": _not_found})
    result = await _call(monkeypatch, rec, "rootly_postmortems_get", {"postmortem_id": PID})
    assert result["error"]["code"] == "not_found"


async def test_update_nonexistent_returns_not_found(monkeypatch):
    rec = Recorder({f"PUT post_mortems/{PID}": _not_found})
    result = await _call(monkeypatch, rec, "rootly_postmortems_update", {"postmortem_id": PID, "title": "New title"})
    assert result["error"]["code"] == "not_found"


async def test_update_with_nothing_to_update_raises_invalid_argument(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "rootly_postmortems_update", {"postmortem_id": PID})
    assert result["error"]["code"] == "invalid_argument"
    assert "Nothing to update" in result["error"]["message"]
    assert not rec.requests  # no HTTP call made: the guard runs before any request


async def test_update_conflict_returns_structured_error_not_a_crash(monkeypatch):
    rec = Recorder({f"PUT post_mortems/{PID}": _conflict})
    result = await _call(monkeypatch, rec, "rootly_postmortems_update", {"postmortem_id": PID, "content": "<p>new</p>"})
    assert result["error"]["code"] == "invalid_argument"
    assert "collaborative editor" in result["error"]["message"]
    assert result["error"]["retryable"] is False


async def test_update_sends_only_the_fields_given(monkeypatch):
    rec = Recorder({f"PUT post_mortems/{PID}": {"data": {"id": PID, "type": "incident_post_mortems", "attributes": {"status": "published"}}}})
    await _call(monkeypatch, rec, "rootly_postmortems_update", {"postmortem_id": PID, "status": "Published"})
    assert body(rec.requests[0])["data"] == {"id": PID, "type": "incident_post_mortems", "attributes": {"status": "published"}}
