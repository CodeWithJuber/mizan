"""
Specialized Agents - Quranic Roles
====================================

Each agent embodies a specific Quranic role/quality:

Mubashir (مبشر) - Browser Agent: "Give glad tidings" - discovers and retrieves
Mundhir (منذر) - Research Agent: "Warner" - analyzes and warns of issues
Katib (كاتب) - Code Agent: "Scribe" - writes and executes code
Rasul (رسول) - Communication Agent: "Messenger" - sends and receives messages
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
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
    """
    
    def __init__(self, **kwargs):
        super().__init__(role="mubashir", **kwargs)
        self._register_browser_tools()
    
    def _register_browser_tools(self):
        self.tools.update({
            "browse_url": self._tool_browse_url,
            "search_web": self._tool_search_web,
            "extract_content": self._tool_extract_content,
            "take_screenshot": self._tool_take_screenshot,
            "click_element": self._tool_click_element,
            "fill_form": self._tool_fill_form,
        })
    
    async def _tool_browse_url(self, url: str) -> Dict:
        """Browse a URL and return content"""
        try:
            import httpx
            from html.parser import HTMLParser
            
            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.skip_tags = {'script', 'style', 'noscript', 'head'}
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
            
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                }
                response = await client.get(url, headers=headers)
                
                extractor = TextExtractor()
                extractor.feed(response.text)
                text_content = " ".join(extractor.text[:200])
                
                return {
                    "url": url,
                    "status": response.status_code,
                    "title": self._extract_title(response.text),
                    "content": text_content[:3000],
                    "links": self._extract_links(response.text, url)[:20],
                }
        except Exception as e:
            return {"error": str(e), "url": url}
    
    def _extract_title(self, html: str) -> str:
        import re
        match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else "No title"
    
    def _extract_links(self, html: str, base_url: str) -> List[str]:
        import re
        links = re.findall(r'href=["\']([^"\']+)["\']', html)
        return [l for l in links if l.startswith('http')][:20]
    
    async def _tool_search_web(self, query: str) -> Dict:
        """Search the web using DuckDuckGo"""
        try:
            import httpx
            import urllib.parse
            
            encoded = urllib.parse.quote(query)
            url = f"https://duckduckgo.com/html/?q={encoded}"
            
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
                response = await client.get(url, headers=headers)
                
                import re
                results = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*class=["\']result__url["\']', response.text)
                titles = re.findall(r'<a[^>]+class=["\']result__a["\'][^>]*>(.*?)</a>', response.text)
                
                return {
                    "query": query,
                    "results": [{"url": r, "title": t} for r, t in zip(results[:10], titles[:10])],
                }
        except Exception as e:
            return {"error": str(e), "query": query}
    
    async def _tool_extract_content(self, url: str, selector: str = None) -> Dict:
        """Extract specific content from a URL"""
        result = await self._tool_browse_url(url)
        return result
    
    async def _tool_take_screenshot(self, url: str) -> Dict:
        """Take screenshot using headless browser"""
        try:
            result = await self._tool_bash(
                f"which chromium-browser || which google-chrome || which chromium || echo 'not_found'",
                timeout=5
            )
            browser = result.get("stdout", "").strip()
            if "not_found" in browser or not browser:
                return {"error": "No browser found for screenshots", "url": url}
            
            screenshot_path = f"/tmp/screenshot_{os.getpid()}.png"
            cmd = f"{browser.splitlines()[0]} --headless --screenshot={screenshot_path} --window-size=1280,720 {url}"
            await self._tool_bash(cmd, timeout=30)
            
            if os.path.exists(screenshot_path):
                return {"success": True, "path": screenshot_path, "url": url}
            return {"error": "Screenshot failed", "url": url}
        except Exception as e:
            return {"error": str(e)}
    
    async def _tool_click_element(self, url: str, selector: str) -> Dict:
        return {"info": "Playwright required for click automation", "url": url, "selector": selector}
    
    async def _tool_fill_form(self, url: str, fields: Dict) -> Dict:
        return {"info": "Playwright required for form automation", "url": url, "fields": list(fields.keys())}


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
        self.tools.update({
            "analyze_text": self._tool_analyze_text,
            "synthesize_sources": self._tool_synthesize_sources,
            "fact_check": self._tool_fact_check,
            "generate_report": self._tool_generate_report,
            "arxiv_search": self._tool_arxiv_search,
        })
    
    async def _tool_analyze_text(self, text: str, aspect: str = "general") -> Dict:
        """Analyze text for key insights"""
        words = text.split()
        sentences = text.split(".")
        
        return {
            "word_count": len(words),
            "sentence_count": len(sentences),
            "key_terms": list(set(w.lower() for w in words if len(w) > 6))[:20],
            "aspect": aspect,
        }
    
    async def _tool_synthesize_sources(self, sources: List[str]) -> Dict:
        """Synthesize multiple sources"""
        return {
            "source_count": len(sources),
            "synthesized": True,
            "summary": f"Synthesized {len(sources)} sources",
        }
    
    async def _tool_fact_check(self, claim: str) -> Dict:
        """Basic fact checking"""
        return {
            "claim": claim,
            "status": "requires_verification",
            "confidence": 0.5,
        }
    
    async def _tool_generate_report(self, topic: str, format: str = "markdown") -> Dict:
        """Generate structured report"""
        return {
            "topic": topic,
            "format": format,
            "template": f"# Research Report: {topic}\n\n## Summary\n\n## Findings\n\n## Conclusions\n",
        }
    
    async def _tool_arxiv_search(self, query: str, max_results: int = 5) -> Dict:
        """Search ArXiv for academic papers"""
        try:
            import httpx
            import urllib.parse
            
            encoded = urllib.parse.quote(query)
            url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&max_results={max_results}"
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                
                import re
                titles = re.findall(r'<title>(.*?)</title>', response.text)[1:]  # Skip feed title
                summaries = re.findall(r'<summary>(.*?)</summary>', response.text, re.DOTALL)
                
                results = []
                for title, summary in zip(titles[:max_results], summaries[:max_results]):
                    results.append({
                        "title": title.strip(),
                        "summary": summary.strip()[:200],
                    })
                
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
        self.tools.update({
            "generate_code": self._tool_generate_code,
            "run_tests": self._tool_run_tests,
            "lint_code": self._tool_lint_code,
            "git_operation": self._tool_git_operation,
            "install_package": self._tool_install_package,
        })
    
    async def _tool_generate_code(self, spec: str, language: str = "python") -> Dict:
        return {"spec": spec, "language": language, "template": f"# Generated {language} code\n# Spec: {spec}\n"}
    
    async def _tool_run_tests(self, path: str, framework: str = "pytest") -> Dict:
        result = await self._tool_bash(f"cd {path} && {framework} --tb=short 2>&1 | head -50", timeout=60)
        return {"framework": framework, "path": path, "output": result}
    
    async def _tool_lint_code(self, path: str) -> Dict:
        result = await self._tool_bash(f"pylint {path} 2>&1 | head -30 || flake8 {path} 2>&1 | head -30", timeout=30)
        return {"path": path, "output": result}
    
    async def _tool_git_operation(self, operation: str, repo_path: str = ".", args: str = "") -> Dict:
        safe_ops = ["status", "log", "diff", "branch", "add", "commit", "push", "pull", "clone"]
        op = operation.split()[0]
        if op not in safe_ops:
            return {"error": f"Operation '{op}' not allowed"}
        result = await self._tool_bash(f"cd {repo_path} && git {operation} {args} 2>&1", timeout=60)
        return result
    
    async def _tool_install_package(self, package: str, manager: str = "pip") -> Dict:
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
        self.tools.update({
            "send_webhook": self._tool_send_webhook,
            "check_email": self._tool_check_email,
            "send_notification": self._tool_send_notification,
        })
    
    async def _tool_send_webhook(self, url: str, payload: Dict) -> Dict:
        result = await self._tool_http_post(url, payload)
        return result
    
    async def _tool_check_email(self, host: str, user: str, password: str, 
                                 folder: str = "INBOX", limit: int = 10) -> Dict:
        try:
            import imaplib
            import email
            
            mail = imaplib.IMAP4_SSL(host)
            mail.login(user, password)
            mail.select(folder)
            
            _, data = mail.search(None, "ALL")
            ids = data[0].split()[-limit:]
            
            messages = []
            for msg_id in ids:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                messages.append({
                    "from": msg.get("From"),
                    "subject": msg.get("Subject"),
                    "date": msg.get("Date"),
                })
            
            mail.logout()
            return {"count": len(messages), "messages": messages}
        except Exception as e:
            return {"error": str(e)}
    
    async def _tool_send_notification(self, message: str, channel: str = "log") -> Dict:
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
