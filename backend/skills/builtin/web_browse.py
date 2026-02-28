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

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._tools = {
            "web_browse": self.browse,
            "web_search": self.search,
        }

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "browse")
        if action == "browse":
            return await self.browse(params.get("url", ""))
        elif action == "search":
            return await self.search(params.get("query", ""))
        return {"error": f"Unknown action: {action}"}

    async def browse(self, url: str | dict = "") -> dict:
        """Browse a URL and extract text content"""
        # Defensive: handle dict input from invoke system
        if isinstance(url, dict):
            url = url.get("url", "")
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 (MIZAN AGI Browser)"}
                )

                extractor = TextExtractor()
                extractor.feed(response.text)
                content = " ".join(extractor.text[:200])

                return {
                    "url": url,
                    "status": response.status_code,
                    "content": content[:5000],
                }
        except Exception as e:
            return {"error": str(e), "url": url}

    async def search(self, query: str | dict = "") -> dict:
        """Search the web using DuckDuckGo"""
        import urllib.parse

        # Defensive: handle dict input from invoke system
        if isinstance(query, dict):
            query = query.get("query", "")
        encoded = urllib.parse.quote(str(query))
        url = f"https://duckduckgo.com/html/?q={encoded}"

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 (MIZAN AGI Browser)"}
                )

                import re

                titles = re.findall(
                    r'<a[^>]+class=["\']result__a["\'][^>]*>(.*?)</a>',
                    response.text,
                )

                return {
                    "query": query,
                    "results": titles[:10],
                }
        except Exception as e:
            return {"error": str(e)}

    def get_tool_schemas(self) -> list:
        return [
            {
                "name": "web_browse",
                "description": "Browse a URL and extract text content",
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
                "description": "Search the web using DuckDuckGo",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                },
            },
        ]
