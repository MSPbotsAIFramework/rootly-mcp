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
"""Auth, retries, JSON:API shaping and request shapes against a mocked Rootly API."""

import json

import httpx
import pytest

from rootly_mcp import api_client
from rootly_mcp.api_client import RootlyClient, RootlyCredentials, RootlyError
from rootly_mcp.server import _credentials_var, create_mcp_server

CREDS = RootlyCredentials(api_token="tok-1")
INC = "a1b2c3d4-0000-0000-0000-000000000001"
INCIDENT = {
    "data": {
        "id": INC,
        "type": "incidents",
        "attributes": {"title": "API down", "status": "started"},
        "relationships": {"severity": {"data": {"id": "sev-1", "type": "severities"}}, "groups": {"data": [{"id": "t1", "type": "groups"}]}},
    }
}


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

    def calls(self, path: str, method: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == f"/v1/{path}" and (method is None or r.method == method)]


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


# ---- transport -------------------------------------------------------------


async def test_bearer_and_json_api_headers():
    rec = Recorder()
    client = RootlyClient(CREDS, httpx.AsyncClient(transport=httpx.MockTransport(rec)))
    await client.request("POST", "alerts", body={"data": {"type": "alerts", "attributes": {"summary": "x"}}})
    request = rec.requests[0]
    assert str(request.url) == "https://api.rootly.com/v1/alerts"
    assert request.headers["Authorization"] == "Bearer tok-1"
    assert request.headers["Content-Type"] == "application/vnd.api+json"
    assert request.headers["Accept"] == "application/vnd.api+json"


async def test_json_api_errors_are_flattened(monkeypatch):
    error = {"errors": [{"title": "Invalid", "detail": "can't be blank", "source": {"pointer": "/data/attributes/title"}}]}
    rec = Recorder({"POST incidents": lambda r: httpx.Response(422, json=error)})
    result = await _call(monkeypatch, rec, "rootly_incidents_create", {"title": "x"})
    assert result["error"]["code"] == "invalid_argument"
    assert "title: can't be blank" in result["error"]["message"]


async def test_unauthorized(monkeypatch):
    rec = Recorder({"users/me": lambda r: httpx.Response(401, json={"errors": [{"title": "Unauthorized"}]})})
    result = await _call(monkeypatch, rec, "rootly_status", {})
    assert result["error"]["code"] == "unauthorized"


async def test_get_retries_but_writes_do_not():
    replies = iter([httpx.Response(502), httpx.Response(200, json={"data": []})])
    rec = Recorder({"GET incidents": lambda r: next(replies), "POST incidents": lambda r: httpx.Response(500)})
    client = RootlyClient(CREDS, httpx.AsyncClient(transport=httpx.MockTransport(rec)))
    assert await client.get("incidents") == {"data": []}
    with pytest.raises(RootlyError):
        await client.request("POST", "incidents", body={})
    assert len(rec.calls("incidents", "GET")) == 2 and len(rec.calls("incidents", "POST")) == 1


# ---- incidents -------------------------------------------------------------


async def test_incidents_list_filters_paging_and_flattening(monkeypatch):
    page = {
        "data": [INCIDENT["data"]],
        "meta": {"current_page": 2, "total_count": 60, "total_pages": 3},
        "links": {"next": "https://api.rootly.com/v1/incidents?page[number]=3"},
    }
    rec = Recorder({"incidents": page})
    result = await _call(monkeypatch, rec, "rootly_incidents_list", {"status": "started", "severity": "sev1", "limit": 25, "page": 2})
    params = rec.requests[0].url.params
    assert (params["filter[status]"], params["filter[severity]"], params["page[size]"], params["page[number]"], params["sort"]) == (
        "started", "sev1", "25", "2", "-created_at",
    )
    incident = result["incidents"][0]
    assert incident == {"id": INC, "type": "incidents", "title": "API down", "status": "started", "severity_id": "sev-1", "groups_ids": ["t1"]}
    assert result["has_more"] is True and result["total"] == 60


async def test_incident_create_maps_teams_to_group_ids(monkeypatch):
    rec = Recorder({"POST incidents": INCIDENT})
    await _call(monkeypatch, rec, "rootly_incidents_create", {"title": "API down", "severity_id": "sev-1", "team_ids": ["t1", "t2"]})
    assert body(rec.calls("incidents", "POST")[0]) == {
        "data": {"type": "incidents", "attributes": {"title": "API down", "severity_id": "sev-1", "group_ids": ["t1", "t2"]}}
    }


async def test_incident_update_uses_put(monkeypatch):
    rec = Recorder({f"PUT incidents/{INC}": INCIDENT})
    await _call(monkeypatch, rec, "rootly_incidents_update", {"incident_id": INC, "status": "mitigated"})
    request = rec.calls(f"incidents/{INC}", "PUT")[0]
    assert body(request) == {"data": {"type": "incidents", "attributes": {"status": "mitigated"}, "id": INC}}
    empty = await _call(monkeypatch, Recorder(), "rootly_incidents_update", {"incident_id": INC})
    assert empty["error"]["code"] == "invalid_argument"


async def test_incident_resolve_endpoint(monkeypatch):
    rec = Recorder({f"PUT incidents/{INC}/resolve": INCIDENT})
    await _call(monkeypatch, rec, "rootly_incidents_resolve", {"incident_id": INC, "resolution_message": "Rolled back"})
    assert body(rec.calls(f"incidents/{INC}/resolve", "PUT")[0])["data"]["attributes"] == {"resolution_message": "Rolled back"}


async def test_ids_are_validated(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "rootly_incidents_get", {"incident_id": "../teams"})
    assert result["error"]["code"] == "invalid_argument"
    assert rec.requests == []


# ---- alerts ----------------------------------------------------------------


ALERT = {"data": {"id": "al-1", "type": "alerts", "attributes": {"summary": "CPU high", "status": "acknowledged"}}}


async def test_alert_acknowledge_and_resolve_use_action_endpoints(monkeypatch):
    rec = Recorder({"POST alerts/al-1/acknowledge": ALERT, "POST alerts/al-1/resolve": ALERT})
    await _call(monkeypatch, rec, "rootly_alerts_acknowledge", {"alert_id": "al-1"})
    await _call(monkeypatch, rec, "rootly_alerts_resolve", {"alert_id": "al-1", "resolution_message": "fixed"})
    assert body(rec.calls("alerts/al-1/acknowledge", "POST")[0]) == {"data": {"type": "alerts", "attributes": {}}}
    assert body(rec.calls("alerts/al-1/resolve", "POST")[0])["data"]["attributes"] == {"resolution_message": "fixed"}


async def test_alert_update_routes_status_and_summary(monkeypatch):
    rec = Recorder({"PATCH alerts/al-1": ALERT, "POST alerts/al-1/resolve": ALERT})
    result = await _call(monkeypatch, rec, "rootly_alerts_update", {"alert_id": "al-1", "status": "resolved", "summary": "CPU high on web-1"})
    assert body(rec.calls("alerts/al-1", "PATCH")[0])["data"]["attributes"] == {"summary": "CPU high on web-1"}
    assert len(rec.calls("alerts/al-1/resolve", "POST")) == 1
    assert result["alert"]["status"] == "acknowledged"
    nothing = await _call(monkeypatch, Recorder(), "rootly_alerts_update", {"alert_id": "al-1"})
    assert nothing["error"]["code"] == "invalid_argument"


async def test_alert_create_body(monkeypatch):
    rec = Recorder({"POST alerts": ALERT})
    await _call(monkeypatch, rec, "rootly_alerts_create", {"summary": "CPU high", "description": "web-1 at 98%"})
    assert body(rec.calls("alerts", "POST")[0]) == {"data": {"type": "alerts", "attributes": {"summary": "CPU high", "description": "web-1 at 98%"}}}


async def test_alerts_list_status_filter(monkeypatch):
    rec = Recorder()
    await _call(monkeypatch, rec, "rootly_alerts_list", {"status": "triggered"})
    assert rec.requests[0].url.params["filter[status]"] == "triggered"


# ---- schedules and org -----------------------------------------------------


async def test_schedules_use_schedules_endpoint(monkeypatch):
    rec = Recorder({"schedules/s1": {"data": {"id": "s1", "type": "schedules", "attributes": {"name": "Primary"}}}})
    await _call(monkeypatch, rec, "rootly_schedules_list", {})
    one = await _call(monkeypatch, rec, "rootly_schedules_get", {"schedule_id": "s1"})
    assert rec.requests[0].url.path == "/v1/schedules"
    assert one == {"id": "s1", "type": "schedules", "name": "Primary"}


async def test_team_create_uses_groups_type_and_user_ids_attribute(monkeypatch):
    rec = Recorder({"POST teams": {"data": {"id": "t9", "type": "groups", "attributes": {"name": "SRE"}}}})
    await _call(monkeypatch, rec, "rootly_org_teams_create", {"name": "SRE", "user_ids": ["u1"], "notify_emails": ["sre@example.com"]})
    assert body(rec.calls("teams", "POST")[0]) == {
        "data": {"type": "groups", "attributes": {"name": "SRE", "notify_emails": ["sre@example.com"], "user_ids": ["u1"]}}
    }


async def test_team_patch_keeps_current_values(monkeypatch):
    current = {"data": {"id": "t1", "type": "groups", "attributes": {"name": "SRE", "description": "On-call", "color": "#336699", "notify_emails": ["a@example.com"]}}}
    rec = Recorder({"GET teams/t1": current, "PUT teams/t1": current})
    result = await _call(monkeypatch, rec, "rootly_org_teams_patch", {"team_id": "t1", "color": "#000000"})
    sent = body(rec.calls("teams/t1", "PUT")[0])["data"]["attributes"]
    assert sent == {"name": "SRE", "description": "On-call", "color": "#000000", "notify_emails": ["a@example.com"]}
    assert result["changed"] == ["color"]


async def test_team_delete_needs_confirm(monkeypatch):
    rec = Recorder()
    refused = await _call(monkeypatch, rec, "rootly_org_teams_delete", {"team_id": "t1"})
    assert refused["error"]["code"] == "invalid_argument"
    assert rec.requests == []
    rec = Recorder({"DELETE teams/t1": lambda r: httpx.Response(204)})
    result = await _call(monkeypatch, rec, "rootly_org_teams_delete", {"team_id": "t1", "confirm": True})
    assert result == {"team_id": "t1", "deleted": True}


async def test_severities_and_current_user(monkeypatch):
    rec = Recorder(
        {
            "severities": {"data": [{"id": "sev-1", "type": "severities", "attributes": {"name": "SEV1", "slug": "sev1"}}], "meta": {"total_count": 1, "total_pages": 1}},
            "users/me": {"data": {"id": "u1", "type": "users", "attributes": {"name": "Jane", "email": "jane@example.com"}}},
        }
    )
    severities = await _call(monkeypatch, rec, "rootly_org_severities_list", {})
    assert severities["severities"][0]["slug"] == "sev1"
    assert rec.calls("severities")[0].url.params["page[size]"] == "100"
    user = await _call(monkeypatch, rec, "rootly_org_current_user", {})
    assert user["email"] == "jane@example.com"
    status = await _call(monkeypatch, rec, "rootly_status", {})
    assert status["connected"] is True and status["user"]["name"] == "Jane"


# ---- compatibility: enum params accept any casing (normalized) and unknown values (passed through)


async def test_alert_update_status_any_case_uses_action_endpoint(monkeypatch):
    rec = Recorder({"POST alerts/al-1/acknowledge": ALERT})
    await _call(monkeypatch, rec, "rootly_alerts_update", {"alert_id": "al-1", "status": "Acknowledged"})
    assert len(rec.calls("alerts/al-1/acknowledge", "POST")) == 1
    assert not rec.calls("alerts/al-1", "PATCH")


async def test_alert_update_unknown_status_passed_through(monkeypatch):
    rec = Recorder({"PATCH alerts/al-1": ALERT})
    await _call(monkeypatch, rec, "rootly_alerts_update", {"alert_id": "al-1", "status": "snoozed"})
    assert body(rec.calls("alerts/al-1", "PATCH")[0])["data"]["attributes"] == {"status": "snoozed"}
    assert not rec.calls("alerts/al-1/acknowledge", "POST") and not rec.calls("alerts/al-1/resolve", "POST")


@pytest.mark.parametrize("given,sent", [("MITIGATED", "mitigated"), ("In_Triage", "in_triage"), ("paused", "paused")])
async def test_incident_update_status_normalized_or_passed_through(monkeypatch, given, sent):
    rec = Recorder({f"PUT incidents/{INC}": INCIDENT})
    await _call(monkeypatch, rec, "rootly_incidents_update", {"incident_id": INC, "status": given})
    assert body(rec.calls(f"incidents/{INC}", "PUT")[0])["data"]["attributes"] == {"status": sent}


# ---- Page-number paging that survives truncation ----------------------------
# Rootly pages by page[number] + page[size] only. offset reads the page that holds a record
# position and next_offset continues right after the last record returned, also when a page is
# cut to fit the response size limit (the rest of a cut page is on no other page).

TOTAL = 130
# Many short fields: shortening long values cannot make 25 such records fit 20,000 characters.
BIG = {f"field{k}": "z" * 60 for k in range(30)}

PAGED_TOOLS = [
    ("rootly_incidents_list", "incidents", "incidents"),
    ("rootly_alerts_list", "alerts", "alerts"),
    ("rootly_schedules_list", "schedules", "schedules"),
    ("rootly_org_teams_list", "teams", "teams"),
]


def _paged_api(big=True):
    """Fake JSON:API list paging TOTAL records by page[number] (from 1) and page[size] like Rootly."""
    records = [{"id": str(n), "type": "things", "attributes": {"n": n, **(BIG if big else {})}} for n in range(TOTAL)]

    def reply(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params.get("page[number]", 1))
        size = int(request.url.params.get("page[size]", 20))
        pages = max((TOTAL + size - 1) // size, 1)
        links = {"next": f"https://api.rootly.com/v1/x?page[number]={number + 1}"} if number < pages else {"next": None}
        return httpx.Response(
            200,
            json={
                "data": records[(number - 1) * size : number * size],
                "meta": {"current_page": number, "total_count": TOTAL, "total_pages": pages},
                "links": links,
            },
        )

    return reply


async def _walk(monkeypatch, tool, path, key, args):
    rec = Recorder({path: _paged_api()})
    seen, calls = [], 0
    result = await _call(monkeypatch, rec, tool, args)
    while True:
        calls += 1
        assert calls < 100
        seen += [r["n"] for r in result[key]]
        if "next_offset" in result:
            assert "retry_page_size" not in result
        else:
            assert result["has_more"] is False
            return seen, calls
        rest = {k: v for k, v in args.items() if k != "page"}
        result = await _call(monkeypatch, rec, tool, {**rest, "offset": result["next_offset"]})


@pytest.mark.parametrize("tool,path,key", PAGED_TOOLS)
async def test_cut_pages_walked_by_next_offset_return_every_record_once(monkeypatch, tool, path, key):
    seen, calls = await _walk(monkeypatch, tool, path, key, {"limit": 25})
    assert seen == list(range(TOTAL))
    assert calls > TOTAL // 25 + 1  # pages really were cut


@pytest.mark.parametrize("tool,path,key", PAGED_TOOLS)
async def test_cut_pages_walked_from_a_later_page(monkeypatch, tool, path, key):
    seen, _ = await _walk(monkeypatch, tool, path, key, {"page": 3, "limit": 25})
    assert seen == list(range(50, TOTAL))


@pytest.mark.parametrize("tool,path,key", PAGED_TOOLS)
@pytest.mark.parametrize("offset,page,ids", [(30, 2, range(30, 50)), (25, 2, range(25, 50)), (0, 1, range(25))])
async def test_offset_reads_the_page_that_holds_it(monkeypatch, tool, path, key, offset, page, ids):
    rec = Recorder({path: _paged_api(big=False)})
    result = await _call(monkeypatch, rec, tool, {"limit": 25, "offset": offset})
    params = rec.requests[0].url.params
    assert (params["page[number]"], params["page[size]"]) == (str(page), "25")
    assert [r["n"] for r in result[key]] == list(ids)
    assert result["offset"] == offset and result["next_offset"] == page * 25 and result["page"] == page


@pytest.mark.parametrize("tool,path,key", PAGED_TOOLS)
async def test_offset_past_the_end(monkeypatch, tool, path, key):
    rec = Recorder({path: _paged_api(big=False)})
    result = await _call(monkeypatch, rec, tool, {"limit": 25, "offset": 1000})
    assert result[key] == [] and result["has_more"] is False and "next_offset" not in result


@pytest.mark.parametrize("tool,path,key", PAGED_TOOLS)
async def test_offset_wins_over_page(monkeypatch, tool, path, key):
    rec = Recorder({path: _paged_api(big=False)})
    result = await _call(monkeypatch, rec, tool, {"page": 1, "limit": 25, "offset": 60})
    assert rec.requests[0].url.params["page[number]"] == "3"
    assert [r["n"] for r in result[key]] == list(range(60, 75))


@pytest.mark.parametrize(
    "tool,path,key,extra",
    [
        ("rootly_incidents_list", "incidents", "incidents", {"sort": "-created_at"}),
        ("rootly_alerts_list", "alerts", "alerts", {}),
        ("rootly_schedules_list", "schedules", "schedules", {}),
        ("rootly_org_teams_list", "teams", "teams", {"sort": "name"}),
    ],
)
@pytest.mark.parametrize(
    "paging,sent",
    [({"page": 2, "limit": 25}, {"page[number]": "2", "page[size]": "25"}), ({}, {"page[number]": "1", "page[size]": "25"})],
)
async def test_page_only_call_sends_the_same_request(monkeypatch, tool, path, key, extra, paging, sent):
    rec = Recorder({path: _paged_api(big=False)})
    result = await _call(monkeypatch, rec, tool, paging)
    assert dict(rec.requests[0].url.params) == {**extra, **sent}
    first = (paging.get("page", 1) - 1) * 25
    assert [r["n"] for r in result[key]] == list(range(first, first + 25))
    assert result["page"] == paging.get("page", 1) and result["has_more"] is True


async def test_severities_list_has_no_offset_fields(monkeypatch):
    rec = Recorder({"severities": _paged_api(big=False)})
    result = await _call(monkeypatch, rec, "rootly_org_severities_list", {})
    assert "offset" not in result and "next_offset" not in result
