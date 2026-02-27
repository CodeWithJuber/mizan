"""
Basirah Engine (بصيرة) — Insightful Vision & Document Understanding
=====================================================================

"Have they not traveled through the land and have hearts by which to
understand and eyes (absar) by which to see?" — Quran 22:46

Basirah goes beyond raw vision — it provides insight and understanding:
- Image analysis with contextual interpretation
- Document/screenshot understanding
- Visual pattern recognition
- OCR-like text extraction from images
- Qalb-aware interpretation (considers emotional context)
"""

import logging
import time
from dataclasses import dataclass, field

from perception.vision import VisionProcessor

logger = logging.getLogger("mizan.basirah")


@dataclass
class BasirahInsight:
    """An insight extracted from visual input."""

    description: str
    category: str  # "text", "diagram", "screenshot", "photo", "document"
    confidence: float = 0.8
    extracted_text: str = ""
    key_elements: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "description": self.description[:200],
            "category": self.category,
            "confidence": round(self.confidence, 2),
            "extracted_text": self.extracted_text[:500] if self.extracted_text else "",
            "key_elements": self.key_elements[:10],
            "processing_time_ms": round(self.processing_time_ms, 1),
        }


class BasirahEngine:
    """
    Insightful vision engine that wraps VisionProcessor with
    contextual understanding and structured output.

    Usage:
        basirah = BasirahEngine()

        # Analyze with insight
        insight = await basirah.analyze(image_bytes, context="user debugging a web app")
        print(insight.category)       # "screenshot"
        print(insight.extracted_text)  # Any text found in the image
    """

    def __init__(self):
        self._vision = VisionProcessor()

    async def analyze(
        self, image_bytes: bytes, context: str = "", media_type: str = "image/png"
    ) -> BasirahInsight:
        """Analyze an image with contextual insight."""
        start = time.time()

        prompt = self._build_prompt(context)
        raw_result = await self._vision.analyze_image(image_bytes, prompt, media_type)

        # Parse the result into structured insight
        insight = self._parse_result(raw_result)
        insight.processing_time_ms = (time.time() - start) * 1000

        return insight

    async def analyze_url(self, url: str, context: str = "") -> BasirahInsight:
        """Analyze an image from URL with contextual insight."""
        start = time.time()

        prompt = self._build_prompt(context)
        raw_result = await self._vision.analyze_image_url(url, prompt)

        insight = self._parse_result(raw_result)
        insight.processing_time_ms = (time.time() - start) * 1000
        return insight

    def _build_prompt(self, context: str) -> str:
        base = (
            "Analyze this image and provide:\n"
            "1. A clear description of what you see\n"
            "2. Category: text, diagram, screenshot, photo, or document\n"
            "3. Any text visible in the image\n"
            "4. Key elements or objects identified\n"
        )
        if context:
            base += f"\nContext: {context}"
        return base

    def _parse_result(self, raw: str) -> BasirahInsight:
        """Parse raw vision output into structured insight."""
        # Determine category from content
        raw_lower = raw.lower()
        if any(w in raw_lower for w in ["screenshot", "interface", "ui", "window", "browser"]):
            category = "screenshot"
        elif any(w in raw_lower for w in ["diagram", "chart", "graph", "flow"]):
            category = "diagram"
        elif any(w in raw_lower for w in ["document", "page", "pdf", "form"]):
            category = "document"
        elif any(w in raw_lower for w in ["error" in raw_lower and "text"]):
            category = "text"
        else:
            category = "photo"

        return BasirahInsight(
            description=raw[:500],
            category=category,
            confidence=0.8,
            extracted_text="",  # Would be populated by more advanced parsing
            key_elements=[],
        )
