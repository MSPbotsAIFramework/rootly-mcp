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
"""Discovery helpers kept for compatibility, plus the connection check.

Every tool is listed from the first tools/list, so rootly_navigate and
rootly_back only describe tools; they keep no state.
"""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._json import compact as to_json
from ..api_client import RootlyClient
from ._common import LOCAL, READ_ONLY, ClientFactory, run_tool, single

DOMAINS: dict[str, tuple[str, list[str]]] = {
    "incidents": (
        "Incidents: list, get, create, update, resolve.",
        ["rootly_incidents_list", "rootly_incidents_get", "rootly_incidents_create", "rootly_incidents_update", "rootly_incidents_resolve"],
    ),
    "alerts": (
        "Alerts: list, acknowledge, resolve, create, update.",
        ["rootly_alerts_list", "rootly_alerts_acknowledge", "rootly_alerts_resolve", "rootly_alerts_create", "rootly_alerts_update"],
    ),
    "schedules": ("On-call schedules: list, get.", ["rootly_schedules_list", "rootly_schedules_get"]),
    "org": (
        "Teams (list, get, create, update, patch, delete), severities and the current user.",
        [
            "rootly_org_teams_list",
            "rootly_org_teams_get",
            "rootly_org_teams_create",
            "rootly_org_teams_update",
            "rootly_org_teams_patch",
            "rootly_org_teams_delete",
            "rootly_org_severities_list",
            "rootly_org_current_user",
        ],
    ),
}


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=LOCAL)
    async def rootly_navigate(
        domain: Annotated[Literal["incidents", "alerts", "schedules", "org"], Field(description="Area to describe.")],
    ) -> str:
        """Describe the tools of one Rootly area. All tools are already callable; this changes nothing."""
        summary, tools = DOMAINS[domain]
        return to_json({"domain": domain, "summary": summary, "tools": tools})

    @mcp.tool(annotations=LOCAL)
    async def rootly_back() -> str:
        """List every Rootly area and its tools. All tools are already callable; this changes nothing."""
        return to_json({"domains": {name: {"summary": s, "tools": t} for name, (s, t) in DOMAINS.items()}})

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_status() -> str:
        """Check the Rootly connection: token accepted and the user it belongs to."""

        async def action(client: RootlyClient) -> dict:
            user = single(await client.get("users/me")) or {}
            return {
                "connected": True,
                "user": {k: user.get(k) for k in ("id", "name", "email", "full_name") if user.get(k) is not None}
                if isinstance(user, dict)
                else user,
                "domains": list(DOMAINS),
            }

        return await run_tool("rootly_status", client_factory, action)
