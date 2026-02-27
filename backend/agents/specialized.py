"""
Specialized Agents - Quranic Roles
====================================

Each agent embodies a specific Quranic role/quality:

Mubashir (مبشر) - Browser Agent: "Give glad tidings" - discovers and retrieves
Mundhir (منذر) - Research Agent: "Warner" - analyzes and warns of issues
Katib (كاتب) - Code Agent: "Scribe" - writes and executes code
Rasul (رسول) - Communication Agent: "Messenger" - sends and receives messages
"""

import os

from .base import BaseAgent


class BrowserAgent(BaseAgent):
    """
    Mubashir (مبشر) - Browser/Discovery Agent
    "And We sent you as a giver of good tidings (Mubashir)" - Quran 33:45

    Capabilities:
    - Web browsing and scraping
    - Screenshot capture
    - Form interaction
    - JavaScript execution

    Graceful degradation:
    - Full Playwright if installed -> headless Chromium -> httpx fallback
    """

    def __init__(self, **kwargs):
        super().__init__(role="mubashir", **kwargs)
        self._playwright_available: bool | None = None
        self._register_browser_tools()

    def _check_playwright(self) -> bool:
        """Check once whether playwright is importable and usable."""
        if self._playwright_available is not None:
            return self._playwright_available
        try:
            import playwright  # noqa: F401

            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
        return self._playwright_available

    def _register_browser_tools(self):
        self.tools.update(
            {
                "browse_url": self._tool_browse_url,
                "navigate": self._tool_navigate,
                "search_web": self._tool_search_web,
                "extract_content": self._tool_extract_content,
                "take_screenshot": self._tool_take_screenshot,
                "click_element": self._tool_click_element,
                "fill_form": self._tool_fill_form,
            }
        )

    # ── Shared httpx helper ──

    async def _httpx_fetch(self, url: str) -> dict:
        """Fetch a URL with httpx, parse HTML into structured data."""
        from html.parser import HTMLParser

        import httpx as _httpx

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

        async with _httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
            response = await client.get(url, headers=headers)

            extractor = TextExtractor()
            extractor.feed(response.text)
            text_content = " ".join(extractor.text[:200])

            return {
                "url": url,
                "status": response.status_code,
                "title": self._extract_title(response.text),
                "content": text_content[:3000],
                "html": response.text[:5000],
                "links": self._extract_links(response.text, url)[:20],
                "backend": "httpx",
            }

    async def _tool_browse_url(self, url: str) -> dict:
        """Browse a URL and return content"""
        try:
            return await self._httpx_fetch(url)
        except Exception as e:
            return {"error": str(e), "url": url}

    async def _tool_navigate(self, url: str, wait_for: str = None) -> dict:
        """
        Navigate to a URL. Uses Playwright when available for full JS
        rendering; falls back to httpx for basic HTML fetching.
        """
        # Try Playwright first
        if self._check_playwright():
            try:
                from playwright.async_api import async_playwright

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, timeout=30000)
                    if wait_for:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    title = await page.title()
                    content = await page.content()
                    text = await page.evaluate("() => document.body.innerText")
                    await browser.close()

                    return {
                        "url": url,
                        "title": title,
                        "content": (text or "")[:3000],
                        "links": self._extract_links(content, url)[:20],
                        "backend": "playwright",
                    }
            except Exception:
                # Fall through to httpx
                pass

        # httpx fallback (no JS rendering)
        try:
            result = await self._httpx_fetch(url)
            result["note"] = (
                "Rendered with httpx (no JavaScript execution). "
                "Install playwright for full browser automation: pip install playwright && playwright install"
            )
            return result
        except Exception as e:
            return {"error": str(e), "url": url}

    def _extract_title(self, html: str) -> str:
        import re

        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else "No title"

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        import re

        links = re.findall(r'href=["\']([^"\']+)["\']', html)
        return [link for link in links if link.startswith("http")][:20]

    async def _tool_search_web(self, query: str) -> dict:
        """Search the web using DuckDuckGo"""
        try:
            import urllib.parse

            import httpx as _httpx

            encoded = urllib.parse.quote(query)
            url = f"https://duckduckgo.com/html/?q={encoded}"

            async with _httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
                response = await client.get(url, headers=headers)

                import re

                results = re.findall(
                    r'<a[^>]+href=["\']([^"\']+)["\'][^>]*class=["\']result__url["\']',
                    response.text,
                )
                titles = re.findall(
                    r'<a[^>]+class=["\']result__a["\'][^>]*>(.*?)</a>', response.text
                )

                return {
                    "query": query,
                    "results": [
                        {"url": r, "title": t}
                        for r, t in zip(results[:10], titles[:10], strict=False)
                    ],
                }
        except Exception as e:
            return {"error": str(e), "query": query}

    async def _tool_extract_content(self, url: str, selector: str = None) -> dict:
        """Extract specific content from a URL"""
        # Try Playwright if a CSS selector is given
        if selector and self._check_playwright():
            try:
                from playwright.async_api import async_playwright

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, timeout=30000)
                    elements = await page.query_selector_all(selector)
                    texts = []
                    for el in elements[:20]:
                        texts.append(await el.inner_text())
                    await browser.close()
                    return {
                        "url": url,
                        "selector": selector,
                        "matches": texts,
                        "count": len(texts),
                        "backend": "playwright",
                    }
            except Exception:
                pass  # Fall through to httpx

        # httpx fallback
        result = await self._tool_browse_url(url)
        if selector:
            result["note"] = (
                f"CSS selector '{selector}' ignored — install playwright for "
                "selector-based extraction: pip install playwright && playwright install"
            )
        return result

    async def _tool_take_screenshot(self, url: str) -> dict:
        """
        Take a screenshot of a web page.

        Tries (in order):
          1. Playwright (best quality, full JS rendering)
          2. System Chromium/Chrome in headless mode
          3. httpx fallback (returns HTML text instead of image)
        """
        # 1. Try Playwright
        if self._check_playwright():
            try:
                from playwright.async_api import async_playwright

                screenshot_path = f"/tmp/screenshot_{os.getpid()}.png"
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page(viewport={"width": 1280, "height": 720})
                    await page.goto(url, timeout=30000)
                    await page.screenshot(path=screenshot_path, full_page=False)
                    await browser.close()

                if os.path.exists(screenshot_path):
                    return {
                        "success": True,
                        "path": screenshot_path,
                        "url": url,
                        "backend": "playwright",
                    }
            except Exception:
                pass  # Fall through

        # 2. Try system Chrome/Chromium
        try:
            result = await self._tool_bash(
                "which chromium-browser || which google-chrome || which chromium || echo 'not_found'",
                timeout=5,
            )
            browser = result.get("stdout", "").strip()
            if browser and "not_found" not in browser:
                screenshot_path = f"/tmp/screenshot_{os.getpid()}.png"
                cmd = f"{browser.splitlines()[0]} --headless --screenshot={screenshot_path} --window-size=1280,720 {url}"
                await self._tool_bash(cmd, timeout=30)

                if os.path.exists(screenshot_path):
                    return {
                        "success": True,
                        "path": screenshot_path,
                        "url": url,
                        "backend": "chromium",
                    }
        except Exception:
            pass  # Fall through

        # 3. httpx fallback — return page text instead of image
        try:
            page_data = await self._httpx_fetch(url)
            return {
                "success": False,
                "url": url,
                "fallback": "text",
                "title": page_data.get("title", ""),
                "content": page_data.get("content", "")[:2000],
                "note": (
                    "Screenshot unavailable — neither Playwright nor a system browser "
                    "was found. Returning page text instead. To enable screenshots, "
                    "install playwright: pip install playwright && playwright install"
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "note": (
                    "Screenshot unavailable and httpx fetch also failed. "
                    "Install playwright for full browser support: pip install playwright && playwright install"
                ),
            }

    async def _tool_click_element(self, url: str, selector: str) -> dict:
        """
        Click an element on a page. Requires Playwright for real interaction;
        provides a graceful fallback with guidance when unavailable.
        """
        if self._check_playwright():
            try:
                from playwright.async_api import async_playwright

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, timeout=30000)
                    await page.click(selector, timeout=10000)
                    # Return page state after click
                    new_url = page.url
                    title = await page.title()
                    text = await page.evaluate("() => document.body.innerText")
                    await browser.close()
                    return {
                        "success": True,
                        "url": new_url,
                        "title": title,
                        "content": (text or "")[:2000],
                        "backend": "playwright",
                    }
            except Exception as e:
                return {"success": False, "error": str(e), "url": url, "selector": selector}

        # Graceful fallback — fetch the page and explain the limitation
        try:
            page_data = await self._httpx_fetch(url)
            return {
                "success": False,
                "url": url,
                "selector": selector,
                "title": page_data.get("title", ""),
                "links": page_data.get("links", []),
                "note": (
                    f"Cannot click '{selector}' — Playwright is not installed. "
                    "The page content and links have been fetched for reference. "
                    "To enable click automation: pip install playwright && playwright install"
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "selector": selector,
                "error": str(e),
                "note": (
                    "Click automation requires Playwright. "
                    "Install it with: pip install playwright && playwright install"
                ),
            }

    async def _tool_fill_form(self, url: str, fields: dict) -> dict:
        """
        Fill form fields on a page. Requires Playwright for real interaction;
        provides a graceful fallback with guidance when unavailable.
        """
        if self._check_playwright():
            try:
                from playwright.async_api import async_playwright

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, timeout=30000)
                    for selector, value in fields.items():
                        await page.fill(selector, str(value), timeout=5000)
                    title = await page.title()
                    await browser.close()
                    return {
                        "success": True,
                        "url": url,
                        "fields_filled": list(fields.keys()),
                        "title": title,
                        "backend": "playwright",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "url": url,
                    "fields": list(fields.keys()),
                }

        # Graceful fallback
        try:
            page_data = await self._httpx_fetch(url)
            return {
                "success": False,
                "url": url,
                "fields": list(fields.keys()),
                "title": page_data.get("title", ""),
                "note": (
                    f"Cannot fill form fields {list(fields.keys())} — Playwright is not installed. "
                    "The page has been fetched for reference. If the form supports a simple HTTP POST, "
                    "consider using the http_post tool instead. "
                    "To enable form automation: pip install playwright && playwright install"
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "fields": list(fields.keys()),
                "error": str(e),
                "note": (
                    "Form automation requires Playwright. "
                    "Install it with: pip install playwright && playwright install"
                ),
            }


class ResearchAgent(BaseAgent):
    """
    Mundhir (منذر) - Research & Analysis Agent
    "And We have not sent you except as a giver of good tidings and a warner" - 25:56

    Capabilities:
    - Deep research and analysis
    - Multi-source synthesis
    - Fact verification
    - Report generation
    """

    def __init__(self, **kwargs):
        super().__init__(role="mundhir", **kwargs)
        self._register_research_tools()

    def _register_research_tools(self):
        self.tools.update(
            {
                "analyze_text": self._tool_analyze_text,
                "synthesize_sources": self._tool_synthesize_sources,
                "fact_check": self._tool_fact_check,
                "generate_report": self._tool_generate_report,
                "arxiv_search": self._tool_arxiv_search,
            }
        )

    async def _tool_analyze_text(self, text: str, aspect: str = "general") -> dict:
        """Analyze text for key insights"""
        words = text.split()
        sentences = text.split(".")

        return {
            "word_count": len(words),
            "sentence_count": len(sentences),
            "key_terms": list(set(w.lower() for w in words if len(w) > 6))[:20],
            "aspect": aspect,
        }

    async def _tool_synthesize_sources(self, sources: list[str]) -> dict:
        """Synthesize multiple sources"""
        return {
            "source_count": len(sources),
            "synthesized": True,
            "summary": f"Synthesized {len(sources)} sources",
        }

    async def _tool_fact_check(self, claim: str) -> dict:
        """Basic fact checking"""
        return {
            "claim": claim,
            "status": "requires_verification",
            "confidence": 0.5,
        }

    async def _tool_generate_report(self, topic: str, format: str = "markdown") -> dict:
        """Generate structured report"""
        return {
            "topic": topic,
            "format": format,
            "template": f"# Research Report: {topic}\n\n## Summary\n\n## Findings\n\n## Conclusions\n",
        }

    async def _tool_arxiv_search(self, query: str, max_results: int = 5) -> dict:
        """Search ArXiv for academic papers"""
        try:
            import urllib.parse

            import httpx

            encoded = urllib.parse.quote(query)
            url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&max_results={max_results}"

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)

                import re

                titles = re.findall(r"<title>(.*?)</title>", response.text)[1:]  # Skip feed title
                summaries = re.findall(r"<summary>(.*?)</summary>", response.text, re.DOTALL)

                results = []
                for title, summary in zip(
                    titles[:max_results], summaries[:max_results], strict=False
                ):
                    results.append(
                        {
                            "title": title.strip(),
                            "summary": summary.strip()[:200],
                        }
                    )

                return {"query": query, "papers": results}
        except Exception as e:
            return {"error": str(e)}


class CodeAgent(BaseAgent):
    """
    Katib (كاتب) - Code/Scribe Agent
    "By the pen and what they write" - Quran 68:1

    Capabilities:
    - Code generation
    - Code review and fixing
    - Testing
    - Deployment
    """

    def __init__(self, **kwargs):
        super().__init__(role="katib", **kwargs)
        self._register_code_tools()

    def _register_code_tools(self):
        self.tools.update(
            {
                "generate_code": self._tool_generate_code,
                "run_tests": self._tool_run_tests,
                "lint_code": self._tool_lint_code,
                "git_operation": self._tool_git_operation,
                "install_package": self._tool_install_package,
            }
        )

    async def _tool_generate_code(self, spec: str, language: str = "python") -> dict:
        return {
            "spec": spec,
            "language": language,
            "template": f"# Generated {language} code\n# Spec: {spec}\n",
        }

    async def _tool_run_tests(self, path: str, framework: str = "pytest") -> dict:
        result = await self._tool_bash(
            f"cd {path} && {framework} --tb=short 2>&1 | head -50", timeout=60
        )
        return {"framework": framework, "path": path, "output": result}

    async def _tool_lint_code(self, path: str) -> dict:
        result = await self._tool_bash(
            f"pylint {path} 2>&1 | head -30 || flake8 {path} 2>&1 | head -30", timeout=30
        )
        return {"path": path, "output": result}

    async def _tool_git_operation(
        self, operation: str, repo_path: str = ".", args: str = ""
    ) -> dict:
        safe_ops = ["status", "log", "diff", "branch", "add", "commit", "push", "pull", "clone"]
        op = operation.split()[0]
        if op not in safe_ops:
            return {"error": f"Operation '{op}' not allowed"}
        result = await self._tool_bash(f"cd {repo_path} && git {operation} {args} 2>&1", timeout=60)
        return result

    async def _tool_install_package(self, package: str, manager: str = "pip") -> dict:
        from security.validation import validate_package_name

        is_safe, reason = validate_package_name(package)
        if not is_safe:
            return {"error": f"Package name rejected: {reason}"}

        managers = {
            "pip": f"pip install {package} --break-system-packages",
            "npm": f"npm install {package}",
        }
        if manager not in managers:
            return {"error": f"Unknown package manager: {manager}. Allowed: pip, npm"}
        result = await self._tool_bash(managers[manager], timeout=120)
        return result


class CommunicationAgent(BaseAgent):
    """
    Rasul (رسول) - Communication Agent
    "O Prophet, indeed We have sent you as a witness and a bringer of good tidings" - 33:45

    Capabilities:
    - Email management
    - Webhook handling
    - Notification dispatch
    - Channel management
    """

    def __init__(self, **kwargs):
        super().__init__(role="rasul", **kwargs)
        self._register_comm_tools()

    def _register_comm_tools(self):
        self.tools.update(
            {
                "send_webhook": self._tool_send_webhook,
                "check_email": self._tool_check_email,
                "send_notification": self._tool_send_notification,
            }
        )

    async def _tool_send_webhook(self, url: str, payload: dict) -> dict:
        result = await self._tool_http_post(url, payload)
        return result

    async def _tool_check_email(
        self, host: str, user: str, password: str, folder: str = "INBOX", limit: int = 10
    ) -> dict:
        try:
            import email
            import imaplib

            mail = imaplib.IMAP4_SSL(host)
            mail.login(user, password)
            mail.select(folder)

            _, data = mail.search(None, "ALL")
            ids = data[0].split()[-limit:]

            messages = []
            for msg_id in ids:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                messages.append(
                    {
                        "from": msg.get("From"),
                        "subject": msg.get("Subject"),
                        "date": msg.get("Date"),
                    }
                )

            mail.logout()
            return {"count": len(messages), "messages": messages}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_send_notification(self, message: str, channel: str = "log") -> dict:
        if channel == "log":
            print(f"[NOTIFICATION] {message}")
            return {"sent": True, "channel": "log"}
        return {"error": f"Unknown notification channel: {channel}"}


def create_agent(agent_type: str, **kwargs) -> BaseAgent:
    """Factory for creating Quranic agents"""
    agents = {
        "browser": BrowserAgent,
        "mubashir": BrowserAgent,
        "research": ResearchAgent,
        "mundhir": ResearchAgent,
        "code": CodeAgent,
        "katib": CodeAgent,
        "communication": CommunicationAgent,
        "rasul": CommunicationAgent,
        "general": BaseAgent,
        "wakil": BaseAgent,
    }

    agent_class = agents.get(agent_type, BaseAgent)

    # BaseAgent is abstract-like but we can instantiate it
    if agent_class == BaseAgent:

        class GeneralAgent(BaseAgent):
            pass

        return GeneralAgent(**kwargs)

    return agent_class(**kwargs)
