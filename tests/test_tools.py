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
"""tools/list snapshot and error-envelope mapping. No network access."""

import asyncio
import json

import pytest

from rootly_mcp.api_client import RootlyError
from rootly_mcp.server import INSTRUCTIONS, create_mcp_server

# Tool names are a public contract: existing agents and tenant connections
# depend on them. Changing this snapshot is a breaking change.
EXPECTED_TOOLS: dict[str, set[str]] = {
    "rootly_navigate": {"domain"},
    "rootly_back": set(),
    "rootly_status": set(),
    "rootly_incidents_list": set(),
    "rootly_incidents_get": {"incident_id"},
    "rootly_incidents_create": {"title"},
    "rootly_incidents_update": {"incident_id"},
    "rootly_incidents_resolve": {"incident_id"},
    "rootly_alerts_list": set(),
    "rootly_alerts_acknowledge": {"alert_id"},
    "rootly_alerts_resolve": {"alert_id"},
    "rootly_alerts_create": {"summary"},
    "rootly_alerts_update": {"alert_id"},
    "rootly_schedules_list": set(),
    "rootly_schedules_get": {"schedule_id"},
    "rootly_org_teams_list": set(),
    "rootly_org_teams_get": {"team_id"},
    "rootly_org_teams_create": {"name"},
    "rootly_org_teams_update": {"team_id"},
    "rootly_org_teams_patch": {"team_id"},
    "rootly_org_teams_delete": {"team_id"},
    "rootly_org_severities_list": set(),
    "rootly_org_current_user": set(),
}

WRITE_TOOLS = {
    "rootly_incidents_create",
    "rootly_incidents_update",
    "rootly_incidents_resolve",
    "rootly_alerts_acknowledge",
    "rootly_alerts_resolve",
    "rootly_alerts_create",
    "rootly_alerts_update",
    "rootly_org_teams_create",
    "rootly_org_teams_update",
    "rootly_org_teams_patch",
    "rootly_org_teams_delete",
}


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_all_tools_listed_without_navigation(tools):
    assert set(tools) == set(EXPECTED_TOOLS)


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_required_params(tools, name):
    assert set(tools[name].inputSchema.get("required", [])) == EXPECTED_TOOLS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_description_budget(tools, name):
    description = (tools[name].description or "").strip()
    assert description, f"{name} has no description"
    assert len(description) <= 500
    assert len(description.splitlines()[0]) <= 100


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_annotations_match_side_effects(tools, name):
    annotations = tools[name].annotations
    assert annotations is not None
    assert annotations.readOnlyHint is (name not in WRITE_TOOLS)
    assert bool(annotations.destructiveHint) is (name == "rootly_org_teams_delete")


@pytest.mark.parametrize("name", sorted(WRITE_TOOLS))
def test_write_tools_say_when_to_use_them(tools, name):
    assert "explicitly asks" in (tools[name].description or "")


def test_instructions_budget():
    assert len(INSTRUCTIONS) <= 1500


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (0, "upstream_error", True),
    ],
)
def test_error_envelope(status, code, retryable):
    envelope = json.loads(RootlyError(status, "boom").to_envelope())
    assert envelope == {"error": {"code": code, "message": "boom", "retryable": retryable}}


def test_tool_without_credentials_returns_not_configured():
    content, _ = asyncio.run(create_mcp_server().call_tool("rootly_status", {}))
    assert json.loads(content[0].text)["error"]["code"] == "not_configured"


def test_navigation_tools_need_no_credentials():
    content, _ = asyncio.run(create_mcp_server().call_tool("rootly_navigate", {"domain": "schedules"}))
    assert json.loads(content[0].text)["tools"] == ["rootly_schedules_list", "rootly_schedules_get"]
