# Connectors (MCP servers)

Every signed-in user can connect Model Context Protocol servers. A connected
server's tools become agent tools named `mcp__<server>__<tool>`. They pass the
same Fitrah, Izn approval and provenance checks as built-in tools. MIZAN uses
the official `mcp` Python SDK (2.x) and speaks the 2026-07-28 protocol, falling
back to the initialize handshake for older servers.

## Adding a server

Open **Settings → Connectors** (`/settings/connectors`). You can:

- **Pick a preset** (`GET /api/connectors/presets`): curated servers whose URL
  was checked against the vendor's own documentation (below).
- **Browse** the official MCP Registry (`registry.modelcontextprotocol.io`,
  API `v0.1` with `v0` as fallback, cached for 1 hour). Only entries the
  registry lists as `active` are shown (deprecated and deleted versions are left
  out). An entry is marked **official** when its verified namespace owns the
  host it reaches or its website (`com.notion/…` → `mcp.notion.com`): the
  publisher runs that service. A GitHub namespace (`io.github.<owner>/…`)
  proves only who published it, so it is never marked. Each package carries a ready `install`: the
  command, arguments and environment variables to add it as a local server
  (`npm` → `npx -y name@version …`, `pypi` → `uvx name==version …`, `oci` →
  `docker run -i --rm image:tag …`; other registries say `supported: false`).
- **Add remote** with an `https://` URL:
  - transport `http` (Streamable HTTP, the current one) or `sse` (the older
    HTTP+SSE transport some servers still offer);
  - an `Authorization` header for servers that take a token or API key;
  - no header for OAuth servers (see OAuth below).
- **Add local** with a command, arguments and environment (stdio). See *Local
  (stdio) servers* below.

Then press **Connect**. The tool list appears; each tool has a policy (below).

### Presets

Each URL was checked against the page in `docs_url` on 28 Nov 2026.

| Preset | Transport | URL or command | Sign-in |
|--------|-----------|----------------|---------|
| GitHub | http | `https://api.githubcopilot.com/mcp/` | personal access token (`Authorization: Bearer …`); GitHub's own sign-in needs an OAuth app registered for MIZAN |
| Notion | http | `https://mcp.notion.com/mcp` | OAuth |
| Linear | http | `https://mcp.linear.app/mcp` | OAuth |
| Atlassian (Jira, Confluence) | http | `https://mcp.atlassian.com/v2/mcp` | OAuth |
| Sentry | http | `https://mcp.sentry.dev/mcp` | OAuth |
| Stripe | http | `https://mcp.stripe.com` | OAuth (or an agent API key as a header) |
| Hugging Face | http | `https://huggingface.co/mcp` | access token (`Authorization: Bearer …`) |
| Cloudflare documentation | http | `https://docs.mcp.cloudflare.com/mcp` | none |
| Vercel | http | `https://mcp.vercel.com` | OAuth, with MIZAN's client metadata document (needs MIZAN on https) |
| Files (sandbox) | stdio | `npx -y @modelcontextprotocol/server-filesystem /workspace` | none |
| Fetch web pages | stdio | `uvx mcp-server-fetch` | none |

## OAuth

When a server needs OAuth, **Connect** returns `authorization_url` and the page
opens it in a new window. MIZAN uses PKCE and identifies itself in one of
three ways, in this order:

1. **A pre-registered client**: `oauth: {client_id, client_secret?, scopes?}` on
   create or `PATCH`. For servers without dynamic registration (Google, Slack,
   enterprise identity providers). The secret is sealed; the scopes are what
   the person is asked for.
2. **A client metadata document** (CIMD): when MIZAN runs on https, its client
   ID is the URL of `GET /api/connectors/oauth/client-metadata.json`, used by
   authorization servers that say they accept one (Vercel requires it).
3. **Dynamic client registration** (RFC 7591), as a public client. A
   registration made for another callback (`MIZAN_PUBLIC_URL` changed) is
   dropped and MIZAN registers again.

The authorization server sends the browser back to
`/api/connectors/oauth/callback`. That route is public, but it does not finish
the sign-in by itself: its page sends the code to `POST
/api/connectors/oauth/complete` with the person's own MIZAN credential, and
only the user who started the sign-in can complete it (the `state` names the
user and the connector, and tokens are stored only on that connector). The
page shows **Connected** only after MIZAN has exchanged the code for tokens;
otherwise it shows why. `GET /api/connectors/{id}/oauth/status` answers
`pending`, `connected` or `error` for the sign-in window. When the page cannot
read the person's credential (another browser, a different origin in
development), it says to open the link in the browser where they are signed in:
the app opens the window with no opener, so the code is never handed on.

Tokens are sealed with their absolute expiry (`auth.expires_at` in the API),
and with the authorization server's metadata. A connection opened after the
access token expired refreshes it before its first request; a token the
server rejects (401) is refreshed before a new authorization is asked. Only
when the refresh fails does the person need to connect again.

**Sign out** (`POST /{id}/signout`) revokes the refresh and access tokens at
the authorization server when it publishes a revocation endpoint (RFC 7009),
and forgets them. A pre-registered client's configuration stays.

The callback URL comes from the request, which works behind the bundled nginx
because it forwards `Host` and `X-Forwarded-Proto`. Set `MIZAN_PUBLIC_URL`
(e.g. `https://mizan.example.com`) when another proxy rewrites them.

During a chat, a server that needs authorization fails fast with a message to
reconnect, and its tools are no longer offered to the model until the person
signs in. The agent never waits on a browser window.

## Tools: trust, new tools and policies

- **Pinning (Amanah).** Each tool is pinned to the description, input schema
  and behaviour hints (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
  `openWorldHint`) first accepted. A tool whose description, schema or hints
  later change (a read-only tool that stops saying so), or whose first
  description carries instructions aimed at the AI, is **held**: hidden from the
  model until you trust it (`POST /{id}/tools/trust {tool}`). A changed tool
  shows what was accepted before (`previous`), so the change can be read.
  Pins made before hints counted are accepted once and moved to the new
  fingerprint, so an upgrade does not hold every tool.
- **New tools.** A tool that appears after the first listing is offered at once
  (the owner chose autonomy) and marked `new` until you have seen it
  (`POST /{id}/tools/ack {tools}`).
- **Policy per tool** (`POST /{id}/tools/policy {tool, policy}`):
  - `allow` (default): the chat's permission mode decides, as for built-in
    tools (see `agentic-coding.md`); tools marked `readOnlyHint` run without
    prompts and stay available in plan mode;
  - `ask`: a person approves every call, even in `auto` mode; with no one to
    ask (an unattended run) the call is held for its owner or refused;
  - `never`: the tool is not offered (the same as switching it off).
- **Server instructions.** What a server says about itself when it connects is
  shown to the model on that server's tool descriptions (300 characters), only
  when those tools are offered, and never when Amanah reads instructions aimed
  at the AI in it.
- **Resources.** A server that offers resources gets two read-only tools,
  `mcp__<server>__resources_list` and `mcp__<server>__resources_read {uri}` (a
  tool of the server's own with the same name wins). A `resource_link` in a
  tool result names the tool that reads it. `GET /{id}/resources` lists them
  on the Connectors page.
- **Prompts.** `GET /{id}/prompts` lists a server's prompts and `POST
  /{id}/prompts/get {name, arguments}` fills one in. They are for the person,
  not agent tools.
- **Questions from the server (elicitation).** A server may ask the person
  something during a tool call. In an interactive chat it arrives as the live
  event `elicitation` (`{id, server, message, schema}`, or `url` for a page to
  open); the person answers with `POST /api/chat/elicitations/{id}`
  `{action: "accept" | "decline" | "cancel", content?}` within 5 minutes. An
  accepted answer must fit the server's schema. With no one watching (an
  unattended run, the API), MIZAN declines.
- **Progress.** Progress a server reports during a call reaches the chat as the
  live event `tool_progress` (`{tool, server, progress, total, message}`).
- **Tool list changes.** When a server says its tools changed
  (`notifications/tools/list_changed`), MIZAN lists them again and re-pins.

## Connection lifetime and health

Each (user, server) pair has one owner task that holds the SDK session.

- It closes after 10 idle minutes and reconnects on the next tool call.
- An idle open connection is pinged every two minutes; one that does not answer
  is closed, so the next call starts a fresh session.
- A call that fails because the session ended (the server restarted and no
  longer knows the session, the local process exited, the stream closed) makes
  MIZAN reconnect. The call is sent again once when it cannot have run: the
  server refused the session, or the tool is read-only or idempotent. Otherwise
  the agent is told it may or may not have run (`code: connector_disconnected`).
- Changing the URL, transport, headers, environment, command, OAuth client,
  limits or the enabled switch reconnects it. Disabling or removing a sandboxed
  local server stops its container.
- A connector that just failed to connect is not offered to the model for 5
  minutes (a later call tries again); one whose secrets cannot be decrypted or
  whose host process is no longer allowed is not offered until it is fixed.

**Status** in `GET /api/connectors` is live: `connected`, `connecting`,
`disconnected`, `error`, `auth_required` or `disabled`, with `last_error`.

**Test** (`POST /{id}/test`) opens a fresh connection (unless calls are running
on the current one), lists the tools and pings: `{ok, latency_ms, tools,
error?}`. **Logs** (`GET /{id}/logs`) are the last 200 lines: connections and
errors, the server's own log messages, and what a host process wrote to stderr.
Every line is redacted first (`manager.redact`): the connector's own sealed header and
env values, and anything shaped like a credential (`Authorization:`, `Bearer …`,
`token=`, `api_key=`, `secret=`, `password=`, known token formats, random-looking
tokens: Satr's patterns, [satr.md](satr.md)), read `[redacted]`. A connector tool's
result is covered the same way before the model sees it.

## Limits and errors

| Limit | Value |
|-------|-------|
| Servers per user | 20 |
| Open connections per user | 10 (the least recently used idle one closes; busy ones are kept) |
| Tools per server | 300 |
| Connect timeout | `timeouts.connect_s`: 30 s, 90 s for `npx`/`uvx`/`bunx` servers (they may download first) |
| Call timeout | `timeouts.call_s`: 120 s |
| Result | 20,000 characters of text, and of structured content (longer structured content comes as `structured_preview` with `structured_truncated`) |

A failed call is a receipt, never an exception: `{error, code, connector}` with
`code` one of `connector_timeout`, `auth_required`, `connector_disconnected`,
`connector_not_allowed`, `secrets_unreadable`, `tool_error`, `unknown_tool`.

## Security

- **Encryption.** Headers, environment values, OAuth tokens and a
  pre-registered client's secret are encrypted with Fernet (as are the other
  secrets MIZAN keeps: runtime settings, Sakk keys, the Web Push key).
  - The key is `$MIZAN_DATA_DIR/connectors.key` (mode 0600), created on first
    use. Back it up with the data volume: without it, saved secrets cannot be
    read.
  - `MIZAN_CONNECTORS_KEY` (comma-separated Fernet keys) replaces it: the first
    key seals, every key opens (`MultiFernet`). To rotate, put the new key first
    and keep the old one after it. The key file, when it exists, still opens
    what it sealed; delete it to retire that key.
  - A value no key opens is logged as an error and the connector shows
    `status: error` with "Saved secrets cannot be decrypted"; it is never
    treated as having no secret.
- **Addresses.** Every request a connector makes must resolve to public
  addresses: the MCP endpoint, OAuth metadata, registration, token and
  revocation requests, and every redirect. Connections go only to the address
  that was just checked (a pinned transport), so DNS rebinding cannot reach
  MIZAN's own network. An administrator can allow specific hosts with
  `MIZAN_MCP_ALLOW_PRIVATE_HOSTS=host1,host2` (such a host may serve its MCP
  endpoint over http).
- **OAuth endpoints** on another host than the MCP server must use https;
  http on the loopback address is accepted only with `MIZAN_DEV=1`
  (development and tests).
- **Tool results** are outside text: Amanah checks them like a web page.
- **Ownership.** Servers are per user
  (`$MIZAN_DATA_DIR/connectors/<SHA-256 of the user id>.json`). One user's
  servers, tools, logs and sign-ins are never visible to another.

## Local (stdio) servers

A stdio server is a process. `MIZAN_MCP_HOST_STDIO` decides who may start one
on the backend host:

| Value | Who |
|-------|-----|
| `admin` (default) | administrators |
| `all` | every user. Only for single-user installs: it lets users run commands on the host. |
| `off` | nobody |

The policy and the owner's role are checked at every launch, not only when the
server was added: an administrator who turns host processes off, or an owner
who is no longer an administrator, stops the next launch. A host process gets
a minimal environment (`PATH`, `LANG`, the SDK's defaults such as `USER`, and
`HOME` set to its own directory under
`$MIZAN_DATA_DIR/connectors/home/<owner>/<server id>`, also its working
directory) plus the connector's own environment; the backend's environment,
API keys included, is not inherited. Its stderr goes to the connector's log,
not the backend's.

Everyone else's stdio servers run inside their own sandbox session on the
workspace runner, not on the host.

- Each server gets its own hardened container: unprivileged, with limits, and
  network only through the egress allowlist, so `npx` and `pip` installs work.
- The runner relays stdin and stdout over a WebSocket, one JSON-RPC message per
  frame.
- Disabling or removing the connector stops its container.

Without a configured runner (and without host access), adding a local server is
refused with an explanation. `capabilities` in `GET /api/connectors` says what
is possible: `host_stdio`, `sandbox_stdio` (a runner is configured) and
`runner_available` (it answers now).

## API

All routes are under `/api/connectors` and act on the caller's own connectors.
Writes need the user role.

| Route | Purpose |
|-------|---------|
| `GET /` | your servers (secrets masked, live status) and `capabilities` |
| `GET /presets` | curated servers |
| `GET /registry?search=&cursor=` | browse the MCP Registry |
| `POST /` | add `{name, transport: "http" \| "sse", url, headers?, oauth?, timeouts?}` or `{name, transport: "stdio", command, args, env, timeouts?}` |
| `GET` / `PATCH` / `DELETE /{id}` | read; update (`name`, `url`, `transport`, `command`, `args`, `enabled`, `headers` and `env` merged per key with `null` removing one, `oauth` (`null` removes the client), `timeouts`, `disabled_tools`); remove. OAuth tokens are kept unless the URL or the OAuth client changes |
| `POST /{id}/connect` | connect; may return `authorization_required` with `authorization_url` |
| `GET /{id}/oauth/status` | `pending` · `connected` · `error` for the sign-in window |
| `POST /{id}/signout` | revoke and forget the OAuth tokens |
| `POST /{id}/test` | `{ok, latency_ms, tools, error?}` |
| `GET /{id}/logs` | `{lines}` |
| `GET /{id}/resources` | `{resources: [{uri, name, description, mime_type}]}` |
| `GET /{id}/prompts` | `{prompts: [{name, description, arguments}]}` |
| `POST /{id}/prompts/get` | one prompt filled in |
| `POST /{id}/tools/trust` | `{tool}`: accept a held tool as it is now (also `POST /{id}/tools/{tool}/trust`) |
| `POST /{id}/tools/policy` | `{tool, policy: "allow" \| "ask" \| "never"}` |
| `POST /{id}/tools/ack` | `{tools}`: clear the `new` mark |
| `POST /{id}/disconnect` | disconnect |
| `GET /oauth/callback` | browser return from the authorization server (public) |
| `POST /oauth/complete` | finish a sign-in this user started |
| `GET /oauth/client-metadata.json` | MIZAN's OAuth client metadata document (public) |

Also `POST /api/chat/elicitations/{id}` answers a server's question in a live
chat.
