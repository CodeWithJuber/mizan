"""Curated connectors, each checked against its vendor's own documentation.

Every remote URL below is the one the vendor documents (``docs_url``), checked on
28 Nov 2026. ``auth`` says how MIZAN signs in: ``oauth`` (MIZAN registers itself
and the person signs in in a browser window), ``headers`` (the person pastes a
token into ``header_name``) or ``none``. Local presets run as stdio servers, in
the person's sandbox unless an administrator may run them on the host.
"""

from __future__ import annotations

PRESETS: list[dict] = [
    {
        "id": "github",
        "name": "GitHub",
        "description": "Repositories, issues, pull requests and Actions. Uses a personal access "
        "token; GitHub's own sign-in needs an OAuth app registered for MIZAN (client ID).",
        "transport": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        "auth": "headers",
        "header_name": "Authorization",
        "header_hint": "Bearer <GitHub personal access token>",
        "docs_url": "https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/set-up-the-github-mcp-server",
        "official": True,
    },
    {
        "id": "notion",
        "name": "Notion",
        "description": "Search, read and edit pages and databases in your Notion workspace.",
        "transport": "http",
        "url": "https://mcp.notion.com/mcp",
        "auth": "oauth",
        "docs_url": "https://developers.notion.com/guides/mcp/get-started-with-mcp",
        "official": True,
    },
    {
        "id": "linear",
        "name": "Linear",
        "description": "Find, create and update Linear issues, projects and comments.",
        "transport": "http",
        "url": "https://mcp.linear.app/mcp",
        "auth": "oauth",
        "docs_url": "https://linear.app/docs/mcp",
        "official": True,
    },
    {
        "id": "atlassian",
        "name": "Atlassian (Jira, Confluence)",
        "description": "Jira issues and Confluence pages through Atlassian's Rovo MCP server.",
        "transport": "http",
        "url": "https://mcp.atlassian.com/v2/mcp",
        "auth": "oauth",
        "docs_url": "https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/",
        "official": True,
    },
    {
        "id": "sentry",
        "name": "Sentry",
        "description": "Errors, issues and releases from your Sentry organisation.",
        "transport": "http",
        "url": "https://mcp.sentry.dev/mcp",
        "auth": "oauth",
        "docs_url": "https://mcp.sentry.dev/",
        "official": True,
    },
    {
        "id": "stripe",
        "name": "Stripe",
        "description": "Customers, payments, invoices and the Stripe docs. Signs in with OAuth; "
        "an agent API key in the Authorization header also works.",
        "transport": "http",
        "url": "https://mcp.stripe.com",
        "auth": "oauth",
        "docs_url": "https://docs.stripe.com/mcp",
        "official": True,
    },
    {
        "id": "huggingface",
        "name": "Hugging Face",
        "description": "Search models, datasets, Spaces and papers on the Hugging Face Hub.",
        "transport": "http",
        "url": "https://huggingface.co/mcp",
        "auth": "headers",
        "header_name": "Authorization",
        "header_hint": "Bearer <Hugging Face access token>",
        "docs_url": "https://huggingface.co/docs/hub/hf-mcp-server",
        "official": True,
    },
    {
        "id": "cloudflare-docs",
        "name": "Cloudflare documentation",
        "description": "Search Cloudflare's developer documentation. No sign-in.",
        "transport": "http",
        "url": "https://docs.mcp.cloudflare.com/mcp",
        "auth": "none",
        "docs_url": "https://developers.cloudflare.com/agents/model-context-protocol/mcp-servers-for-cloudflare/",
        "official": True,
    },
    {
        "id": "vercel",
        "name": "Vercel",
        "description": "Projects, deployments, logs and the Vercel docs. Vercel accepts clients "
        "that publish a client metadata document, which needs MIZAN on an https address "
        "(MIZAN_PUBLIC_URL).",
        "transport": "http",
        "url": "https://mcp.vercel.com",
        "auth": "oauth",
        "docs_url": "https://vercel.com/docs/agent-resources/vercel-mcp",
        "official": True,
    },
    {
        "id": "filesystem",
        "name": "Files (sandbox)",
        "description": "Read and write files under /workspace in your own sandbox.",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
        "auth": "none",
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        "official": True,
    },
    {
        "id": "fetch",
        "name": "Fetch web pages",
        "description": "Fetch a web page and read it as Markdown (through the sandbox's network).",
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "auth": "none",
        "docs_url": "https://pypi.org/project/mcp-server-fetch/",
        "official": True,
    },
]


def presets() -> list[dict]:
    return [dict(preset) for preset in PRESETS]
