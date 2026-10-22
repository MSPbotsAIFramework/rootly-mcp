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
"""Alerts."""

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
    enum_value,
    list_page,
    resource_id,
    run_tool,
    single,
)

AlertId = Annotated[str, Field(description="Rootly alert id.", min_length=1)]
AlertStatus = Literal["acknowledged", "resolved"]


async def acknowledge(client: RootlyClient, aid: str) -> Any:
    return single(await client.request("POST", f"alerts/{aid}/acknowledge", body=body("alerts", {})))


async def resolve(client: RootlyClient, aid: str, message: str | None = None) -> Any:
    attributes = compact({"resolution_message": (message or "").strip() or None})
    return single(await client.request("POST", f"alerts/{aid}/resolve", body=body("alerts", attributes)))


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def rootly_alerts_list(
        status: Annotated[str | None, Field(description="Status, e.g. triggered, acknowledged, resolved.")] = None,
        limit: Limit = None,
        page: Page = None,
        offset: Offset = None,
    ) -> str:
        """List alerts with summary, status, source, services and timestamps, optionally by status."""

        async def action(client: RootlyClient) -> dict:
            params = compact({"filter[status]": (status or "").strip() or None})
            return await list_page(client, "alerts", "alerts", params, limit, page, offset, by_offset=True)

        return await run_tool("rootly_alerts_list", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_alerts_acknowledge(alert_id: AlertId) -> str:
        """Acknowledge an alert so escalation stops. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            return await acknowledge(client, resource_id(alert_id, "alert_id"))

        return await run_tool("rootly_alerts_acknowledge", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_alerts_resolve(
        alert_id: AlertId,
        resolution_message: Annotated[str | None, Field(description="How the alert was resolved.")] = None,
    ) -> str:
        """Resolve an alert, optionally with a resolution message. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            return await resolve(client, resource_id(alert_id, "alert_id"), resolution_message)

        return await run_tool("rootly_alerts_resolve", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def rootly_alerts_create(
        summary: Annotated[str, Field(description="Alert summary.", min_length=1)],
        source: Annotated[str | None, Field(description="Alert source label (deprecated by Rootly; optional).")] = None,
        description: Annotated[str | None, Field(description="Longer description.")] = None,
    ) -> str:
        """Create an alert; with On-Call enabled it may page responders. Only when the user explicitly asks."""

        async def action(client: RootlyClient) -> Any:
            if not summary.strip():
                raise ValueError("summary must not be blank.")
            attributes = compact({"summary": summary.strip(), "source": source, "description": description})
            return single(await client.request("POST", "alerts", body=body("alerts", attributes)))

        return await run_tool("rootly_alerts_create", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def rootly_alerts_update(
        alert_id: AlertId,
        status: Annotated[AlertStatus | str | None, Field(description="acknowledged or resolved.")] = None,
        summary: Annotated[str | None, Field(description="New summary.")] = None,
    ) -> str:
        """Change an alert's summary, or move it to acknowledged / resolved.

        Only when the user explicitly asks.
        """

        async def action(client: RootlyClient) -> dict:
            aid = resource_id(alert_id, "alert_id")
            new_status = enum_value(status, AlertStatus)
            if new_status is None and not (summary and summary.strip()):
                raise ValueError("Nothing to update: pass status and / or summary.")
            result: dict[str, Any] = {"alert_id": aid}
            # acknowledged / resolved have their own endpoints; any other status goes to the API as given.
            attributes = compact({"summary": (summary or "").strip() or None})
            if new_status is not None and new_status not in ("acknowledged", "resolved"):
                attributes["status"] = new_status
            if attributes:
                result["alert"] = single(await client.request("PATCH", f"alerts/{aid}", body=body("alerts", attributes, aid)))
            if new_status == "acknowledged":
                result["alert"] = await acknowledge(client, aid)
            elif new_status == "resolved":
                result["alert"] = await resolve(client, aid)
            return result

        return await run_tool("rootly_alerts_update", client_factory, action)
