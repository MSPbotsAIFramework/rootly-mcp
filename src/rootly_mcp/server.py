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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import re
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ._arguments import EnvelopeFastMCP
from .api_client import RootlyClient, RootlyCredentials
from .config import Settings

HEADER_API_TOKEN = "X-Rootly-Api-Token"

_PLACEHOLDER = re.compile(r"^\$\{.*\}$")
_BEARER = re.compile(r"^bearer(\s+|$)", re.IGNORECASE)

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[RootlyCredentials | None] = contextvars.ContextVar(
    "rootly_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("rootly_request_id", default="-")

INSTRUCTIONS = (
    "Rootly is an incident management and on-call platform. This server "
    "works with one Rootly organisation: incidents, alerts, on-call "
    "schedules, teams, severities and the API user.\n"
    "Usage:\n"
    "- Every tool is listed up front; rootly_navigate / rootly_back only "
    "describe them.\n"
    "- Look up ids first: rootly_org_severities_list for severity_id, "
    "rootly_org_teams_list for team ids, rootly_schedules_list for schedules.\n"
    "- Incidents: rootly_incidents_list(status, severity slug) -> "
    "rootly_incidents_get; rootly_incidents_resolve closes one with an "
    "optional resolution message.\n"
    "- Alerts: rootly_alerts_list(status) -> acknowledge / resolve.\n"
    "- Lists page with limit + page and report has_more.\n"
    "Creating, updating, resolving or acknowledging incidents and alerts "
    "notifies responders, and team changes affect paging: call those tools "
    "only when the user explicitly asks. rootly_org_teams_delete is "
    "irreversible and needs confirm=true."
)


def get_client_from_context() -> RootlyClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return RootlyClient(credentials)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or _PLACEHOLDER.match(text):
        return None
    return text


class GatewayCredentialsMiddleware:
    """Reads X-Rootly-Api-Token on /mcp requests into the request context; 401 without it."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        token = _clean(request.headers.get(HEADER_API_TOKEN))
        if token:
            token = _clean(_BEARER.sub("", token))
        if not token:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": f"Send the Rootly API token in the {HEADER_API_TOKEN} header",
                    "required_headers": [HEADER_API_TOKEN],
                },
                status_code=401,
            )(scope, receive, send)
            return

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(RootlyCredentials(api_token=token))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = EnvelopeFastMCP(
        name="rootly-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], RootlyClient | None] = get_client_from_context

    from .tools import alerts, incidents, navigation, org, schedules

    for module in (navigation, incidents, alerts, schedules, org):
        module.register(mcp, client_factory)

    return mcp
