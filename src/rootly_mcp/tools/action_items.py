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
"""Action items: follow-up tasks tracked on an incident, or org-wide. PRD-21240."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import RootlyClient
from ._common import (
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

ActionItemId = Annotated[str, Field(description="Rootly action item id.", min_length=1)]
IncidentId = Annotated[str, Field(description="Rootly incident id.")]
Priority = Literal["high", "medium", "low"]
ActionItemStatus = Literal["open", "in_progress", "cancelled", "done"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def rootly_action_items_list(
        incident_id: Annotated[str | None, Field(description="Limit to one incident's action items.")] = None,
        status: Annotated[str | None, Field(description="Status, e.g. open, in_progress, done, cancelled. Org-wide only: not supported together with incident_id.")] = None,
        priority: Annotated[str | None, Field(description="high, medium or low. Org-wide only: not supported together with incident_id.")] = None,
        kind: Annotated[str | None, Field(description="task or follow_up. Org-wide only: not supported together with incident_id.")] = None,
        limit: Limit = None,
        page: Page = None,
        offset: Offset = None,
    ) -> str:
        """List action items: one incident's (with incident_id) or org-wide (without it, with filters)."""

        async def action(client: RootlyClient) -> dict:
            iid = resource_id(incident_id, "incident_id") if incident_id else None
            if iid and (status or priority or kind):
                raise ValueError(
                    "incident_id does not support status/priority/kind filters on Rootly's incident-scoped "
                    "action items endpoint; call without incident_id for org-wide filtered search."
                )
            if iid:
                return await list_page(client, f"incidents/{iid}/action_items", "action_items", {}, limit, page, offset, by_offset=True)
            params = compact({"filter[status]": status, "filter[priority]": priority, "filter[kind]": kind})
            return await list_page(client, "action_items", "action_items", params, limit, page, offset, by_offset=True)

        return await run_tool("rootly_action_items_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_action_items_get(action_item_id: ActionItemId) -> str:
        """Get one action item by id."""

        async def action(client: RootlyClient) -> Any:
            return single(await client.get(f"action_items/{resource_id(action_item_id, 'action_item_id')}"))

        return await run_tool("rootly_action_items_get", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def rootly_action_items_create(
        incident_id: IncidentId,
        summary: Annotated[str, Field(description="Action item summary.", min_length=1)],
        description: Annotated[str | None, Field(description="Longer description.")] = None,
        priority: Annotated[Priority | str | None, Field(description="high, medium or low.")] = None,
        due_date: Annotated[str | None, Field(description="Due date (ISO 8601 date).")] = None,
        assigned_to_user_id: Annotated[str | None, Field(description="User id to assign (from rootly_org_current_user or incident responders).")] = None,
    ) -> str:
        """Create a follow-up action item under an incident. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            iid = resource_id(incident_id, "incident_id")
            if not summary.strip():
                raise ValueError("summary must not be blank.")
            attributes = compact(
                {
                    "summary": summary.strip(),
                    "description": description,
                    "priority": priority,
                    "due_date": due_date,
                    "assigned_to_user_id": assigned_to_user_id,
                }
            )
            return single(await client.request("POST", f"incidents/{iid}/action_items", body=body("incident_action_items", attributes)))

        return await run_tool("rootly_action_items_create", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_action_items_update(
        action_item_id: ActionItemId,
        status: Annotated[ActionItemStatus | str | None, Field(description="open, in_progress, done or cancelled.")] = None,
        priority: Annotated[Priority | str | None, Field(description="high, medium or low.")] = None,
        description: Annotated[str | None, Field(description="New description.")] = None,
        due_date: Annotated[str | None, Field(description="New due date (ISO 8601 date).")] = None,
        assigned_to_user_id: Annotated[str | None, Field(description="New assignee user id.")] = None,
    ) -> str:
        """Change an action item's status, priority, description, due date or assignee.

        Only when the user explicitly asks.
        """

        async def action(client: RootlyClient) -> Any:
            aid = resource_id(action_item_id, "action_item_id")
            attributes = compact(
                {
                    "status": status,
                    "priority": priority,
                    "description": description,
                    "due_date": due_date,
                    "assigned_to_user_id": assigned_to_user_id,
                }
            )
            if not attributes:
                raise ValueError("Nothing to update: pass at least one field to change.")
            return single(await client.request("PUT", f"action_items/{aid}", body=body("incident_action_items", attributes, aid)))

        return await run_tool("rootly_action_items_update", client_factory, action)
