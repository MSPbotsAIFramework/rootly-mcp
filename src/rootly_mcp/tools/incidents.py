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
"""Incidents."""

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
    Page,
    body,
    compact,
    enum_value,
    list_page,
    resource_id,
    run_tool,
    single,
)

IncidentId = Annotated[str, Field(description="Rootly incident id.", min_length=1)]
Status = Literal["in_triage", "started", "detected", "acknowledged", "mitigated", "resolved", "closed", "cancelled"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def rootly_incidents_list(
        status: Annotated[str | None, Field(description="Status, e.g. started, mitigated, resolved (comma-separate several).")] = None,
        severity: Annotated[str | None, Field(description="Severity slug, e.g. sev1 (see rootly_org_severities_list).")] = None,
        limit: Limit = None,
        page: Page = None,
    ) -> str:
        """List incidents, newest first, optionally by status or severity."""

        async def action(client: RootlyClient) -> dict:
            params = compact({"filter[status]": (status or "").strip() or None, "filter[severity]": (severity or "").strip() or None, "sort": "-created_at"})
            return await list_page(client, "incidents", "incidents", params, limit, page)

        return await run_tool("rootly_incidents_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_incidents_get(incident_id: IncidentId) -> str:
        """Get one incident: title, status, severity, timeline timestamps, teams, services and links."""

        async def action(client: RootlyClient) -> Any:
            return single(await client.get(f"incidents/{resource_id(incident_id, 'incident_id')}"))

        return await run_tool("rootly_incidents_get", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def rootly_incidents_create(
        title: Annotated[str, Field(description="Incident title.", min_length=1)],
        summary: Annotated[str | None, Field(description="Short summary.")] = None,
        severity_id: Annotated[str | None, Field(description="Severity id from rootly_org_severities_list.")] = None,
        team_ids: Annotated[list[str] | None, Field(description="Team ids from rootly_org_teams_list.")] = None,
    ) -> str:
        """Declare a new incident; responders may be paged. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            if not title.strip():
                raise ValueError("title must not be blank.")
            attributes = compact(
                {
                    "title": title.strip(),
                    "summary": summary,
                    "severity_id": severity_id,
                    "group_ids": [resource_id(t, "team_ids") for t in team_ids] if team_ids else None,
                }
            )
            return single(await client.request("POST", "incidents", body=body("incidents", attributes)))

        return await run_tool("rootly_incidents_create", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_incidents_update(
        incident_id: IncidentId,
        title: Annotated[str | None, Field(description="New title.")] = None,
        summary: Annotated[str | None, Field(description="New summary.")] = None,
        status: Annotated[Status | str | None, Field(description="New status.")] = None,
        severity_id: Annotated[str | None, Field(description="New severity id.")] = None,
    ) -> str:
        """Change an incident's title, summary, status or severity. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            iid = resource_id(incident_id, "incident_id")
            attributes = compact({"title": title, "summary": summary, "status": enum_value(status, Status), "severity_id": severity_id})
            if not attributes:
                raise ValueError("Nothing to update: pass at least one field to change.")
            return single(await client.request("PUT", f"incidents/{iid}", body=body("incidents", attributes, iid)))

        return await run_tool("rootly_incidents_update", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_incidents_resolve(
        incident_id: IncidentId,
        resolution_message: Annotated[str | None, Field(description="How the incident was resolved.")] = None,
    ) -> str:
        """Mark an incident resolved, optionally with a resolution message. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            iid = resource_id(incident_id, "incident_id")
            attributes = compact({"resolution_message": (resolution_message or "").strip() or None})
            return single(await client.request("PUT", f"incidents/{iid}/resolve", body=body("incidents", attributes, iid)))

        return await run_tool("rootly_incidents_resolve", client_factory, action)
