# Connectors (MCP servers)

Every signed-in user can connect Model Context Protocol servers. A connected
server's tools become agent tools named `mcp__<server>__<tool>`. They pass the
same Fitrah, Izn approval and provenance checks as built-in tools. MIZAN uses
the official `mcp` Python SDK (2.x).

## Adding a server

Open **Connectors** in the sidebar. You can:

- **Browse** the official MCP Registry (`registry.modelcontextprotocol.io`,
  cached for 1 hour) and add a listed remote server in one click.
- **Add remote** with an `https://` URL, using the Streamable HTTP transport.
  - Give it an `Authorization` header if the server uses API keys.
  - Leave the header out for OAuth servers.
- **Add local** with a command, arguments and environment (stdio transport).
  See *Local (stdio) servers* below.

Then press **Connect**. The tool list appears, and each tool can be switched off.

## OAuth

When a server needs OAuth, Connect returns an authorization URL and the UI
opens it in a new window. MIZAN registers itself dynamically as a public
client, uses PKCE, and waits for the browser to return to
`/api/connectors/oauth/callback`. That route is public: the single-use OAuth
`state` is the key. Tokens are stored encrypted and refreshed by the SDK.

The callback URL comes from the request, which works behind the bundled nginx
because it forwards `Host` and `X-Forwarded-Proto`. Set `MIZAN_PUBLIC_URL`
(e.g. `https://mizan.example.com`) when another proxy rewrites them.

During a chat, a server that needs authorization fails fast with a message to
reconnect. The agent never waits on a browser window.

## Security

- **Encryption.** Headers, environment values and OAuth tokens are encrypted
  with Fernet. The key is `$MIZAN_DATA_DIR/connectors.key` (mode 0600), created
  on first use. Back it up with the data volume: without it, saved secrets
  cannot be read.
- **Addresses.** Every request a connector makes must resolve to public
  addresses. This includes OAuth metadata discovery and redirects. Private,
  loopback, link-local and metadata addresses are refused, so a server URL
  cannot reach MIZAN's own network. An administrator can allow specific hosts
  with `MIZAN_MCP_ALLOW_PRIVATE_HOSTS=host1,host2`.
- **Approvals.**
  - Tools marked `readOnlyHint` run without approval prompts and stay available
    in plan mode.
  - Other tools follow the chat's permission mode (see `agentic-coding.md`).
- **Ownership.** Servers are per user (`$MIZAN_DATA_DIR/connectors/<user>.json`).
  One user's servers and tools are never visible to another.

## Local (stdio) servers

A stdio server is a process. `MIZAN_MCP_HOST_STDIO` decides who may start one
on the backend host:

| Value | Who |
|-------|-----|
| `admin` (default) | administrators |
| `all` | every user. Only for single-user installs: it lets users run commands on the host. |
| `off` | nobody |

Everyone else's stdio servers run inside their own sandbox session on the
workspace runner, not on the host.

- Each server gets its own hardened container: unprivileged, with limits, and
  network only through the egress allowlist, so `npx` and `pip` installs work.
- The runner relays stdin and stdout over a WebSocket, one JSON-RPC message per
  frame.
- Removing the connector stops its container.

Without a configured runner, Connect explains that the sandbox is not
available.

## Connection lifetime

Each (user, server) pair has one owner task that holds the SDK session. It
closes after 10 idle minutes and reconnects on the next tool call. Changing
headers, environment or the enabled switch reconnects it.

## API

All routes are under `/api/connectors`. Writes need the editor role.

| Route | Purpose |
|-------|---------|
| `GET /` | your servers (secrets masked) |
| `GET /registry?search=&cursor=` | browse the MCP Registry |
| `POST /` | add `{name, transport, url, headers}` or `{name, transport: "stdio", command, args, env}` |
| `GET` / `PATCH` / `DELETE /{id}` | read, update (name, enabled, headers, env, `disabled_tools`), remove |
| `POST /{id}/connect` | connect; may return `authorization_required` with `authorization_url` |
| `POST /{id}/disconnect` | disconnect |
| `GET /oauth/callback` | browser return from the authorization server |
