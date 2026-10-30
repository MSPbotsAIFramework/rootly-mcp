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
"""Current on-call (no meta/links, unlike every other list) and override idempotency. PRD-21240."""

import json

import httpx
import pytest

from rootly_mcp import api_client
from rootly_mcp.server import _credentials_var, create_mcp_server

CREDS = api_client.RootlyCredentials(api_token="tok-1")
SCHED = "a1b2c3d4-0000-0000-0000-000000000005"
USER = "a1b2c3d4-0000-0000-0000-000000000006"


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
        self.default = default if default is not None else {"data": []}

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


ONCALL = {
    "data": [
        {
            "id": "oc-1",
            "type": "on_call_resources",
            "attributes": {
                "schedule_id": SCHED,
                "schedule_name": "Primary",
                "user_id": USER,
                "escalation_policy_id": "ep-1",
                "escalation_policy_name": "Default",
                "escalation_level": 1,
            },
        }
    ]
}


async def test_oncalls_list_flattens_without_pagination_fields(monkeypatch):
    rec = Recorder({"GET oncalls": ONCALL})
    result = await _call(monkeypatch, rec, "rootly_oncalls_list", {})
    assert result == {"oncalls": [{"id": "oc-1", "type": "on_call_resources", **ONCALL["data"][0]["attributes"]}]}
    assert "count" not in result and "has_more" not in result


async def test_oncalls_list_filters_by_schedule_and_user(monkeypatch):
    rec = Recorder({"GET oncalls": ONCALL})
    await _call(monkeypatch, rec, "rootly_oncalls_list", {"schedule_id": SCHED, "user_id": USER, "since": "2026-11-01T00:00:00Z"})
    params = rec.requests[0].url.params
    assert params["filter[schedule_ids]"] == SCHED
    assert params["filter[user_ids]"] == USER
    assert params["since"] == "2026-11-01T00:00:00Z"
    assert "until" not in params


async def test_override_create_missing_required_field_raises_invalid_argument(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "rootly_schedules_override_create", {"schedule_id": SCHED, "user_id": "", "starts_at": "x", "ends_at": "y"})
    assert result["error"]["code"] == "invalid_argument"
    assert not rec.requests


async def test_override_create_posts_to_override_shifts(monkeypatch):
    rec = Recorder(
        {
            f"POST schedules/{SCHED}/override_shifts": {
                "data": {"id": "ov-1", "type": "shifts", "attributes": {"user_id": USER, "starts_at": "2026-11-01T00:00:00Z", "ends_at": "2026-11-02T00:00:00Z"}}
            }
        }
    )
    result = await _call(
        monkeypatch,
        rec,
        "rootly_schedules_override_create",
        {"schedule_id": SCHED, "user_id": USER, "starts_at": "2026-11-01T00:00:00Z", "ends_at": "2026-11-02T00:00:00Z"},
    )
    assert rec.requests[0].url.path == f"/v1/schedules/{SCHED}/override_shifts"
    assert body(rec.requests[0])["data"] == {
        "type": "shifts",
        "attributes": {"user_id": USER, "starts_at": "2026-11-01T00:00:00Z", "ends_at": "2026-11-02T00:00:00Z"},
    }
    assert result["id"] == "ov-1"


async def test_override_create_repeated_call_returns_the_same_override_not_an_error(monkeypatch):
    """Rootly itself de-duplicates identical overrides server-side (200, not 201); no client-side key needed."""
    rec = Recorder({f"POST schedules/{SCHED}/override_shifts": lambda r: httpx.Response(200, json={"data": {"id": "ov-1", "type": "shifts", "attributes": {}}})})
    result = await _call(
        monkeypatch,
        rec,
        "rootly_schedules_override_create",
        {"schedule_id": SCHED, "user_id": USER, "starts_at": "2026-11-01T00:00:00Z", "ends_at": "2026-11-02T00:00:00Z"},
    )
    assert "error" not in result and result["id"] == "ov-1"
