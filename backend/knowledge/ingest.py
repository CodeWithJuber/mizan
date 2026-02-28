"""
Knowledge Ingestion (Ilm - عِلْم)
==================================

"Read in the name of your Lord who created" - Quran 96:1

Extracts knowledge from external sources (URLs, PDFs, YouTube)
and stores it in MIZAN's memory system.
"""

import logging
import re
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


async def extract_url(url: str) -> dict:
    """Extract text content from a web URL."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MIZAN/1.0)"}
        response = await client.get(url, headers=headers)
        response.raise_for_status()

        extractor = _TextExtractor()
        extractor.feed(response.text)
        content = " ".join(extractor.text)

        return {
            "title": extractor._title or url,
            "content": content[:50000],
            "source": url,
            "source_type": "url",
            "char_count": len(content),
        }


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
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        content = " ".join(entry["text"] for entry in transcript_list)

        return {
            "title": f"YouTube: {video_id}",
            "content": content[:50000],
            "source": url,
            "source_type": "youtube",
            "video_id": video_id,
            "segment_count": len(transcript_list),
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
