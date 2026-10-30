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
"""Post-mortems (Rootly API resource: post_mortems, UI name: retrospectives).

There is no create tool: Rootly creates a post-mortem automatically when an
incident starts. PRD-21240.
"""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import RootlyClient
from ._common import (
    READ_ONLY,
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

PostmortemId = Annotated[str, Field(description="Rootly post-mortem id.", min_length=1)]
Status = Literal["draft", "published"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def rootly_postmortems_list(
        status: Annotated[str | None, Field(description="Status, e.g. draft, published.")] = None,
        search: Annotated[str | None, Field(description="Free-text search over title/content.")] = None,
        limit: Limit = None,
        page: Page = None,
        offset: Offset = None,
    ) -> str:
        """List post-mortems (retrospectives), optionally by status or a text search."""

        async def action(client: RootlyClient) -> dict:
            params = compact({"filter[status]": (status or "").strip() or None, "filter[search]": (search or "").strip() or None})
            return await list_page(client, "post_mortems", "post_mortems", params, limit, page, offset, by_offset=True)

        return await run_tool("rootly_postmortems_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def rootly_postmortems_get(postmortem_id: PostmortemId) -> str:
        """Get one post-mortem: title, status, content and incident timeline timestamps."""

        async def action(client: RootlyClient) -> Any:
            return single(await client.get(f"post_mortems/{resource_id(postmortem_id, 'postmortem_id')}"))

        return await run_tool("rootly_postmortems_get", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def rootly_postmortems_update(
        postmortem_id: PostmortemId,
        title: Annotated[str | None, Field(description="New title.")] = None,
        content: Annotated[str | None, Field(description="New content (HTML).")] = None,
        status: Annotated[Status | str | None, Field(description="draft or published.")] = None,
    ) -> str:
        """Change a post-mortem's title, content or status. Only when the user explicitly asks.

        Fails with a structured, non-crashing error if the retrospective is already open in
        Rootly's collaborative editor (Rootly owns the body in that case).
        """

        async def action(client: RootlyClient) -> Any:
            pid = resource_id(postmortem_id, "postmortem_id")
            attributes = compact({"title": title, "content": content, "status": enum_value(status, Status)})
            if not attributes:
                raise ValueError("Nothing to update: pass at least one field to change.")
            return single(await client.request("PUT", f"post_mortems/{pid}", body=body("incident_post_mortems", attributes, pid)))

        return await run_tool("rootly_postmortems_update", client_factory, action)
