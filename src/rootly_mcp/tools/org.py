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
"""Organisation: teams (Rootly "groups"), severities and the current user."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import RootlyClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    WRITES_IDEMPOTENT,
    ClientFactory,
    Limit,
    Offset,
    Page,
    body,
    compact,
    list_page,
    resource_id,
    run_tool,
    single,
)

TeamId = Annotated[str, Field(description="Team id from rootly_org_teams_list.", min_length=1)]
Name = Annotated[str | None, Field(description="Team name.")]
Description = Annotated[str | None, Field(description="Team description.")]
Color = Annotated[str | None, Field(description="Hex colour, e.g. #3366FF.")]
NotifyEmails = Annotated[list[str] | None, Field(description="Email addresses notified for the team (replaces the list).")]
UserIds = Annotated[list[str] | None, Field(description="Member user ids (replaces the member list).")]

# Teams are "groups" in the Rootly API.
_TYPE = "groups"
_EDITABLE = ("name", "description", "color", "notify_emails", "user_ids")


def _team_attributes(name: str | None, description: str | None, color: str | None, notify_emails: list[str] | None, user_ids: list[str] | None) -> dict:
    return compact({"name": name, "description": description, "color": color, "notify_emails": notify_emails, "user_ids": user_ids})


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def rootly_org_teams_list(limit: Limit = None, page: Page = None, offset: Offset = None) -> str:
        """List teams with name, slug, description and colour."""

        async def action(client: RootlyClient) -> dict:
            return await list_page(client, "teams", "teams", {"sort": "name"}, limit, page, offset, by_offset=True)

        return await run_tool("rootly_org_teams_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_org_teams_get(team_id: TeamId) -> str:
        """Get one team by id, including notification emails and member ids."""

        async def action(client: RootlyClient) -> Any:
            return single(await client.get(f"teams/{resource_id(team_id, 'team_id')}"))

        return await run_tool("rootly_org_teams_get", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def rootly_org_teams_create(
        name: Annotated[str, Field(description="Team name.", min_length=1)],
        description: Description = None,
        color: Color = None,
        notify_emails: NotifyEmails = None,
        user_ids: UserIds = None,
    ) -> str:
        """Create a team. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            if not name.strip():
                raise ValueError("name must not be blank.")
            attributes = _team_attributes(name.strip(), description, color, notify_emails, user_ids)
            return single(await client.request("POST", "teams", body=body(_TYPE, attributes)))

        return await run_tool("rootly_org_teams_create", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_org_teams_update(
        team_id: TeamId,
        name: Name = None,
        description: Description = None,
        color: Color = None,
        notify_emails: NotifyEmails = None,
        user_ids: UserIds = None,
    ) -> str:
        """Update a team with the fields given (lists are replaced). Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            tid = resource_id(team_id, "team_id")
            attributes = _team_attributes(name, description, color, notify_emails, user_ids)
            if not attributes:
                raise ValueError("Nothing to update: pass at least one field to change.")
            return single(await client.request("PUT", f"teams/{tid}", body=body(_TYPE, attributes, tid)))

        return await run_tool("rootly_org_teams_update", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_org_teams_patch(
        team_id: TeamId,
        name: Name = None,
        description: Description = None,
        color: Color = None,
        notify_emails: NotifyEmails = None,
        user_ids: UserIds = None,
    ) -> str:
        """Change a few team fields, keeping the rest as they are now. Only when the user explicitly asks.

        Reads the team first and sends its current values with your changes.
        """

        async def action(client: RootlyClient) -> dict:
            tid = resource_id(team_id, "team_id")
            changes = _team_attributes(name, description, color, notify_emails, user_ids)
            if not changes:
                raise ValueError("Nothing to update: pass at least one field to change.")
            current = single(await client.get(f"teams/{tid}")) or {}
            merged = {k: current.get(k) for k in _EDITABLE if isinstance(current, dict) and current.get(k) is not None} | changes
            updated = single(await client.request("PUT", f"teams/{tid}", body=body(_TYPE, merged, tid)))
            return {"team": updated, "changed": sorted(changes)}

        return await run_tool("rootly_org_teams_patch", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def rootly_org_teams_delete(
        team_id: TeamId,
        confirm: Annotated[bool | None, Field(description="Must be true; the deletion cannot be undone.")] = None,
    ) -> str:
        """Permanently delete a team and its memberships. Irreversible: only when the user explicitly asks.

        Needs confirm=true.
        """

        async def action(client: RootlyClient) -> dict:
            tid = resource_id(team_id, "team_id")
            if confirm is not True:
                raise ValueError("Deleting a team cannot be undone; call again with confirm=true once the user has approved it.")
            await client.request("DELETE", f"teams/{tid}")
            return {"team_id": tid, "deleted": True}

        return await run_tool("rootly_org_teams_delete", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_org_severities_list() -> str:
        """List incident severities (id, name, slug, description) used for severity_id and severity filters."""

        async def action(client: RootlyClient) -> dict:
            return await list_page(client, "severities", "severities", {}, 100, 1)

        return await run_tool("rootly_org_severities_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_org_current_user() -> str:
        """Get the user the API token belongs to."""

        async def action(client: RootlyClient) -> Any:
            return single(await client.get("users/me"))

        return await run_tool("rootly_org_current_user", client_factory, action)
