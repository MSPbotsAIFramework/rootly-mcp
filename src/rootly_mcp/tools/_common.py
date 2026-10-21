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
"""Shared argument types, JSON:API helpers and the error-handling wrapper."""

import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, get_args

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import RootlyClient, RootlyError

logger = logging.getLogger("rootly_mcp.tools")

ClientFactory = Callable[[], RootlyClient | None]

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
LOCAL = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITES_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)

NOT_CONFIGURED = error_envelope("not_configured", "The Rootly API token is missing for this request (X-Rootly-Api-Token).", False)

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

Limit = Annotated[int | None, Field(description="Results per page (1-100, default 25).", ge=1, le=100)]
Page = Annotated[int | None, Field(description="Page number, from 1.", ge=1)]


def compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def resource_id(value: str, what: str) -> str:
    """Ids go into URL paths; Rootly ids are UUIDs or slugs."""
    text = (value or "").strip()
    if not _ID.match(text):
        raise ValueError(f"{what} must be a Rootly id (got {value!r}).")
    return text


def flatten(resource: Any) -> Any:
    """JSON:API {id, type, attributes, relationships} -> one flat dict."""
    if not isinstance(resource, dict) or "attributes" not in resource:
        return resource
    flat: dict[str, Any] = {"id": resource.get("id"), "type": resource.get("type")}
    flat.update(resource.get("attributes") or {})
    for name, rel in (resource.get("relationships") or {}).items():
        data = rel.get("data") if isinstance(rel, dict) else None
        if isinstance(data, list) and data:
            flat[f"{name}_ids"] = [d.get("id") for d in data if isinstance(d, dict)]
        elif isinstance(data, dict):
            flat[f"{name}_id"] = data.get("id")
    return flat


def single(payload: Any) -> Any:
    return flatten(payload.get("data")) if isinstance(payload, dict) and "data" in payload else payload


async def list_page(client: RootlyClient, path: str, key: str, params: dict[str, Any], limit: int | None, page: int | None) -> dict:
    size, number = limit or 25, page or 1
    payload = await client.get(path, compact({**params, "page[size]": size, "page[number]": number})) or {}
    items = [flatten(r) for r in payload.get("data") or []] if isinstance(payload, dict) else []
    meta = payload.get("meta") if isinstance(payload, dict) and isinstance(payload.get("meta"), dict) else {}
    links = payload.get("links") if isinstance(payload, dict) and isinstance(payload.get("links"), dict) else {}
    total_pages = meta.get("total_pages")
    more = bool(links.get("next")) if links else (isinstance(total_pages, int) and number < total_pages)
    return compact(
        {
            key: items,
            "count": len(items),
            "total": meta.get("total_count"),
            "page": number,
            "total_pages": total_pages,
            "has_more": more,
        }
    )


def body(resource_type: str, attributes: dict[str, Any], resource_id_: str | None = None) -> dict:
    data: dict[str, Any] = {"type": resource_type, "attributes": attributes}
    if resource_id_:
        data["id"] = resource_id_
    return {"data": data}


def enum_value(value: Any, choices: Any) -> Any:
    """Canonical spelling of a case-insensitive match in ``choices`` (a Literal type).

    Any other value passes through unchanged, so the API decides (older callers sent free text).
    """
    if not isinstance(value, str):
        return value
    wanted = value.strip().lower()
    return next((c for c in get_args(choices) if isinstance(c, str) and c.lower() == wanted), value)


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[RootlyClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    started = time.monotonic()
    try:
        result = await action(client)
    except RootlyError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    if result is None:
        result = {"result": None, "note": "Rootly returned an empty response."}
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
