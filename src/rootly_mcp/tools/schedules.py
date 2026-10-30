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
"""On-call schedules, current on-call and overrides. PRD-21240 added the on-call tools."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import RootlyClient
from ._common import READ_ONLY, WRITES_IDEMPOTENT, ClientFactory, Limit, Offset, Page, body, compact, flatten, list_page, resource_id, run_tool, single

ScheduleId = Annotated[str, Field(description="Schedule id from rootly_schedules_list.", min_length=1)]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def rootly_schedules_list(limit: Limit = None, page: Page = None, offset: Offset = None) -> str:
        """List on-call schedules with name, description, owning team and time zone."""

        async def action(client: RootlyClient) -> dict:
            return await list_page(client, "schedules", "schedules", {}, limit, page, offset, by_offset=True)

        return await run_tool("rootly_schedules_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_schedules_get(schedule_id: ScheduleId) -> str:
        """Get one on-call schedule by id."""

        async def action(client: RootlyClient) -> Any:
            return single(await client.get(f"schedules/{resource_id(schedule_id, 'schedule_id')}"))

        return await run_tool("rootly_schedules_get", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_oncalls_list(
        schedule_id: Annotated[str | None, Field(description="Limit to one schedule.")] = None,
        user_id: Annotated[str | None, Field(description="Limit to one user.")] = None,
        since: Annotated[str | None, Field(description="Start of the time window (ISO 8601).")] = None,
        until: Annotated[str | None, Field(description="End of the time window (ISO 8601).")] = None,
    ) -> str:
        """List who is on call right now (or in a given window), grouped by escalation policy."""

        async def action(client: RootlyClient) -> dict:
            params = compact(
                {
                    "filter[schedule_ids]": resource_id(schedule_id, "schedule_id") if schedule_id else None,
                    "filter[user_ids]": resource_id(user_id, "user_id") if user_id else None,
                    "since": since,
                    "until": until,
                }
            )
            # No meta/links on this response (unlike every other list in this server), so
            # list_page's paging machinery does not fit; flatten the raw data instead.
            payload = await client.get("oncalls", params) or {}
            return {"oncalls": [flatten(r) for r in payload.get("data") or []] if isinstance(payload, dict) else []}

        return await run_tool("rootly_oncalls_list", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_schedules_override_create(
        schedule_id: ScheduleId,
        user_id: Annotated[str, Field(description="User id to cover this window.", min_length=1)],
        starts_at: Annotated[str, Field(description="Override start (ISO 8601).", min_length=1)],
        ends_at: Annotated[str, Field(description="Override end (ISO 8601).", min_length=1)],
    ) -> str:
        """Hand off on-call coverage for a time window. Only when the user explicitly asks.

        Calling it again with the same user and times returns the existing override instead of
        creating a duplicate (Rootly de-duplicates identical overrides server-side).
        """

        async def action(client: RootlyClient) -> Any:
            sid = resource_id(schedule_id, "schedule_id")
            if not user_id.strip() or not starts_at.strip() or not ends_at.strip():
                raise ValueError("user_id, starts_at and ends_at are all required.")
            attributes = {"user_id": user_id.strip(), "starts_at": starts_at.strip(), "ends_at": ends_at.strip()}
            return single(await client.request("POST", f"schedules/{sid}/override_shifts", body=body("shifts", attributes)))

        return await run_tool("rootly_schedules_override_create", client_factory, action)
