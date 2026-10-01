"""
Knowledge Ingestion (Ilm - عِلْم)
==================================

"Read in the name of your Lord who created" - Quran 96:1

Extracts knowledge from external sources (URLs, PDFs, YouTube)
and stores it in MIZAN's memory system.
"""

import asyncio
import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser

import httpx

logger = logging.getLogger("mizan.knowledge")


class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping scripts/styles."""

    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self._skip_tags = {"script", "style", "noscript", "head"}
        self._skipping = False
        self._title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skipping = True
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skipping = False
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self._title += data.strip()
        if not self._skipping:
            stripped = data.strip()
            if stripped:
                self.text.append(stripped)


MAX_FETCH_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5


async def _public_destination(url: str) -> tuple[httpx.URL, str, str]:
    parsed = httpx.URL(url)
    if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.userinfo:
        raise ValueError("Only public HTTP(S) URLs without credentials are allowed")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await asyncio.get_running_loop().getaddrinfo(
        parsed.host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
    )
    ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
    if not ips or any(
        not ip.is_global
        or ip.is_multicast
        or (
            isinstance(ip, ipaddress.IPv6Address)
            and ip.ipv4_mapped is not None
            and not ip.ipv4_mapped.is_global
        )
        for ip in ips
    ):
        raise ValueError("URL resolves to a non-public address")
    host_header = parsed.netloc.decode("ascii")
    # Connect to the validated literal, eliminating the second DNS lookup/rebinding gap.
    return parsed.copy_with(host=str(ips[0])), host_header, parsed.host


async def extract_url(url: str) -> dict:
    """Fetch a bounded public document, checking and pinning every redirect."""
    original = url
    async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
        for redirect in range(MAX_REDIRECTS + 1):
            destination, host_header, tls_hostname = await _public_destination(url)
            async with client.stream(
                "GET",
                destination,
                headers={
                    "User-Agent": "MIZAN/1.0",
                    "Host": host_header,
                    "Accept-Encoding": "identity",
                },
                extensions={"sni_hostname": tls_hostname},
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location or redirect == MAX_REDIRECTS:
                        raise ValueError("Invalid or excessive redirects")
                    url = str(httpx.URL(url).join(location))
                    continue
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError("Compressed documents are not accepted")
                if int(response.headers.get("content-length", "0")) > MAX_FETCH_BYTES:
                    raise ValueError("Document exceeds size limit")
                body = bytearray()
                async for chunk in response.aiter_raw(chunk_size=65536):
                    if len(body) + len(chunk) > MAX_FETCH_BYTES:
                        raise ValueError("Document exceeds size limit")
                    body.extend(chunk)
                text = body.decode(response.encoding or "utf-8", errors="replace")
                extractor = _TextExtractor()
                extractor.feed(text)
                content = " ".join(extractor.text)
                return {
                    "title": extractor._title or original,
                    "content": content[:50000],
                    "source": original,
                    "source_type": "url",
                    "char_count": len(content),
                }
    raise ValueError("Unable to fetch document")


def extract_pdf(file_bytes: bytes, filename: str = "upload.pdf") -> dict:
    """Extract text content from a PDF file."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return {
            "error": "pymupdf not installed. Run: pip install pymupdf",
            "source": filename,
            "source_type": "pdf",
        }

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text = []
    for page in doc:
        pages_text.append(page.get_text())
    doc.close()

    content = "\n\n".join(pages_text)
    title_match = re.search(r"^(.{5,100})", content.strip())
    title = title_match.group(1) if title_match else filename

    return {
        "title": title,
        "content": content[:50000],
        "source": filename,
        "source_type": "pdf",
        "page_count": len(pages_text),
        "char_count": len(content),
    }


def _extract_youtube_id(url: str) -> str | None:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def extract_youtube(url: str) -> dict:
    """Extract transcript from a YouTube video."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {
            "error": "youtube-transcript-api not installed. Run: pip install youtube-transcript-api",
            "source": url,
            "source_type": "youtube",
        }

    video_id = _extract_youtube_id(url)
    if not video_id:
        return {
            "error": f"Could not extract video ID from URL: {url}",
            "source": url,
            "source_type": "youtube",
        }

    try:
        # The 1.x SDK returns typed transcript snippets and performs blocking HTTP.
        transcript = await asyncio.to_thread(YouTubeTranscriptApi().fetch, video_id)
        content = " ".join(snippet.text for snippet in transcript)

        return {
            "title": f"YouTube: {video_id}",
            "content": content[:50000],
            "source": url,
            "source_type": "youtube",
            "video_id": video_id,
            "segment_count": len(transcript),
            "char_count": len(content),
        }
    except Exception as exc:
        return {
            "error": f"Failed to get transcript: {exc}",
            "source": url,
            "source_type": "youtube",
            "video_id": video_id,
        }


def detect_source_type(source: str) -> str:
    """Auto-detect source type from URL/string."""
    lower = source.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.startswith("http://") or lower.startswith("https://"):
        return "url"
    return "unknown"


def chunk_content(content: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
    """Split content into overlapping chunks for memory storage."""
    if len(content) <= chunk_size:
        return [content]

    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]
        # Try to break at sentence boundary
        if end < len(content):
            last_period = chunk.rfind(". ")
            if last_period > chunk_size // 2:
                chunk = chunk[: last_period + 1]
                end = start + last_period + 1
        chunks.append(chunk.strip())
        start = end - overlap

    return chunks
