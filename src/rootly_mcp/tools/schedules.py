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
"""On-call schedules."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import RootlyClient
from ._common import READ_ONLY, ClientFactory, Limit, Offset, Page, list_page, resource_id, run_tool, single


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def rootly_schedules_list(limit: Limit = None, page: Page = None, offset: Offset = None) -> str:
        """List on-call schedules with name, description, owning team and time zone."""

        async def action(client: RootlyClient) -> dict:
            return await list_page(client, "schedules", "schedules", {}, limit, page, offset, by_offset=True)

        return await run_tool("rootly_schedules_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_schedules_get(
        schedule_id: Annotated[str, Field(description="Schedule id from rootly_schedules_list.", min_length=1)],
    ) -> str:
        """Get one on-call schedule by id."""

        async def action(client: RootlyClient) -> Any:
            return single(await client.get(f"schedules/{resource_id(schedule_id, 'schedule_id')}"))

        return await run_tool("rootly_schedules_get", client_factory, action)
