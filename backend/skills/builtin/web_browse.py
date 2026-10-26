"""
Web Browse Skill
=================

Enhanced web browsing with content extraction.
"""

from html.parser import HTMLParser

import httpx

from ..base import SkillBase, SkillManifest


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {"script", "style", "noscript", "head"}
        self.current_skip = False

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.current_skip = True

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.current_skip = False

    def handle_data(self, data):
        if not self.current_skip:
            stripped = data.strip()
            if stripped:
                self.text.append(stripped)


class WebBrowseSkill(SkillBase):
    """Enhanced web browsing skill"""

    manifest = SkillManifest(
        name="web_browse",
        version="1.0.0",
        description="Browse web pages and extract content",
        permissions=["network:https://*", "network:http://*"],
        tags=["web", "browse", "scrape"],
    )

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._tools = {
            "web_browse": self.browse,
            "web_search": self.search,
        }

    async def execute(self, params: dict, context: dict | None = None) -> dict:
        action = params.get("action", "browse")
        if action == "browse":
            return await self.browse(params.get("url", ""))
        elif action == "search":
            return await self.search(params.get("query", ""))
        return {"error": f"Unknown action: {action}"}

    async def browse(self, url: str | dict = "") -> dict:
        """Fetch a public page as readable text.

        Every hop (including redirects) must resolve to a public address and
        the connection is pinned to the checked IP, so a URL can never reach
        the backend's own network (other containers, metadata services).
        """
        from knowledge.ingest import extract_url

        if isinstance(url, dict):
            url = url.get("url", "")
        if not isinstance(url, str) or not url.strip():
            return {"error": "URL must be text"}
        try:
            document = await extract_url(url.strip())
        except Exception as e:  # noqa: BLE001 - a fetch failure is a tool receipt
            return {"error": str(e)[:300], "url": url}
        return {
            "url": url,
            "title": document.get("title", ""),
            "content": str(document.get("content", ""))[:20000],
            "characters": document.get("char_count", 0),
        }

    async def search(self, query: str | dict = "") -> dict:
        """Search the web (DuckDuckGo HTML results: title, URL, snippet)."""
        import html
        import re
        import urllib.parse

        if isinstance(query, dict):
            query = query.get("query", "")
        query = str(query).strip()[:400]
        if not query:
            return {"error": "A search query is required"}
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 (MIZAN AGI Browser)"}
                )
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:300], "query": query}
        page = response.text
        links = re.findall(
            r'<a[^>]+class=["\']result__a["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            page,
            re.S,
        )
        snippets = re.findall(r'<a[^>]+class=["\']result__snippet["\'][^>]*>(.*?)</a>', page, re.S)

        def clean(fragment: str) -> str:
            return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()

        def target(href: str) -> str:
            href = html.unescape(href)
            if "uddg=" in href:
                parsed = urllib.parse.urlparse(href)
                return urllib.parse.parse_qs(parsed.query).get("uddg", [href])[0]
            return href

        results = [
            {
                "title": clean(title),
                "url": target(href),
                "snippet": clean(snippets[index]) if index < len(snippets) else "",
            }
            for index, (href, title) in enumerate(links[:10])
        ]
        return {"query": query, "results": results, "status": response.status_code}

    def get_tool_schemas(self) -> list:
        return [
            {
                "name": "web_browse",
                "description": "Fetch a public web page and return its readable text (public addresses only)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to browse"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "web_search",
                "description": "Search the web; returns titles, URLs and snippets to open with web_browse",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                },
            },
        ]
