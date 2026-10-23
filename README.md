# Rootly MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Rootly](https://rootly.com) REST API
(v1), the incident management and on-call platform. It lets an AI agent read incidents,
alerts, on-call schedules, teams, severities and the API user and, on explicit request,
declare, update and resolve incidents, acknowledge, resolve, create and update alerts, and
manage teams.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: the API token arrives on every request as an HTTP header and is
  never stored; every tool is listed from the first `tools/list`
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Rootly-Api-Token` | Yes | string | none | - | Rootly API key (a leading `Bearer ` is accepted and ignored) | `rootly_xxxxxxxxxxxxxxxx` |

Where to get it: an admin creates an API key in Rootly's organization settings (API keys).
A global key works across the organization; a team or personal key is limited to what that
team or user can see and change. Use a key whose permissions cover incidents, alerts,
schedules and teams.

How the token is sent to Rootly: as `Authorization: Bearer <token>` to
`https://api.rootly.com/v1/...`, with the JSON:API media type. Values that look like
unresolved templates (`${...}`) are treated as missing.

A request to `/mcp` without the header gets HTTP 401 naming it.

## Tools

All tools return a JSON string. JSON:API resources are flattened to `{id, type, ...attributes}`
with related ids as `<relationship>_id` / `<relationship>_ids`. List tools take `limit`
(default 25, at most 100) and `page` and return `{items, count, total, page, total_pages,
has_more}` under the resource name. The incidents, alerts, schedules and teams lists also take
`offset` (record position, overriding `page`) and return `offset` / `next_offset`: when a page is
too large for the response size limit and is cut, `next_offset` continues right after the last
record returned, which `page` cannot (the rest of a cut page is on no other page).

| Tool | Purpose | Parameters (required in **bold**) |
|---|---|---|
| `rootly_navigate` | Describe the tools of one area (changes nothing) | **domain** (`incidents`, `alerts`, `schedules`, `org`) |
| `rootly_back` | List every area and its tools (changes nothing) | - |
| `rootly_status` | Check the connection: token accepted, owning user | - |
| `rootly_incidents_list` | List incidents, newest first | status, severity, limit, page |
| `rootly_incidents_get` | One incident with timeline, severity, teams and services | **incident_id** |
| `rootly_incidents_create` | Declare an incident (**write**) | **title**, summary, severity_id, team_ids |
| `rootly_incidents_update` | Change title, summary, status or severity (**write**) | **incident_id**, title, summary, status, severity_id |
| `rootly_incidents_resolve` | Resolve an incident (**write**) | **incident_id**, resolution_message |
| `rootly_alerts_list` | List alerts | status, limit, page |
| `rootly_alerts_acknowledge` | Acknowledge an alert (**write**) | **alert_id** |
| `rootly_alerts_resolve` | Resolve an alert (**write**) | **alert_id**, resolution_message |
| `rootly_alerts_create` | Create an alert (**write**) | **summary**, source, description |
| `rootly_alerts_update` | Change the summary, or acknowledge / resolve (**write**) | **alert_id**, status (`acknowledged`, `resolved`), summary |
| `rootly_schedules_list` | List on-call schedules | limit, page |
| `rootly_schedules_get` | One on-call schedule | **schedule_id** |
| `rootly_org_teams_list` | List teams | limit, page |
| `rootly_org_teams_get` | One team | **team_id** |
| `rootly_org_teams_create` | Create a team (**write**) | **name**, description, color, notify_emails, user_ids |
| `rootly_org_teams_update` | Update a team with the fields given (**write**) | **team_id**, name, description, color, notify_emails, user_ids |
| `rootly_org_teams_patch` | Change some fields, keeping current values for the rest (**write**) | **team_id**, name, description, color, notify_emails, user_ids |
| `rootly_org_teams_delete` | Permanently delete a team (**write**, needs `confirm: true`) | **team_id**, confirm |
| `rootly_org_severities_list` | Incident severities (id, slug) | - |
| `rootly_org_current_user` | The user the token belongs to | - |

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "invalid_argument", "message": "Rootly returned HTTP 422 for incidents: title: can't be blank", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`. Reads are retried with backoff on 429, 5xx and network
errors; writes only on 429.

## Run locally

```bash
uv sync
uv run python -m rootly_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t rootly-mcp:dev .
docker run --rm -p 8080:8080 rootly-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). The token is never read from
the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Rootly-Api-Token: rootly_xxxxxxxxxxxxxxxx" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# open incidents
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Rootly-Api-Token: rootly_xxxxxxxxxxxxxxxx" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"rootly_incidents_list","arguments":{"status":"started"}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Delivery notes

- **All tools always listed.** Older versions only listed the navigation tools until one was
  called. Behind a stateless gateway that hid every other tool, so this version lists all 23
  tools up front. `rootly_navigate` and `rootly_back` remain for compatibility and only
  describe the tools.
- **Built on the published API reference.** Every call follows Rootly's OpenAPI document.
  Corrections compared with the older version: on-call schedules come from `/schedules`;
  incidents are updated with `PUT` and resolved through `PUT /incidents/{id}/resolve`; alerts
  are acknowledged / resolved through `POST /alerts/{id}/acknowledge|resolve`; incident teams
  are sent as `group_ids`; teams use the API's `groups` resource type with `user_ids` as an
  attribute.
- **Parameters.** `rootly_alerts_create` no longer takes `severity` (the API has no such alert
  field) and gained `description`; the resolve tools gained an optional `resolution_message`;
  `rootly_alerts_update` status is limited to the transitions the API supports.
- **Deletes.** `rootly_org_teams_delete` needs `confirm: true`.
- **Gateway registration.** Rootly is not in the gateway registry yet; register it with the
  single credential field `X-Rootly-Api-Token`.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
