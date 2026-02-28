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

import json as _json
import logging
import re
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
        self,
        image_bytes: bytes,
        context: str = "",
        media_type: str = "image/png",
        qalb_state: str = "",
    ) -> BasirahInsight:
        """Analyze an image with contextual insight, modulated by emotional state."""
        start = time.time()

        prompt = self._build_prompt(context, qalb_state)
        raw_result = await self._vision.analyze_image(image_bytes, prompt, media_type)

        insight = self._parse_result(raw_result)
        insight.processing_time_ms = (time.time() - start) * 1000

        return insight

    async def analyze_url(
        self, url: str, context: str = "", qalb_state: str = ""
    ) -> BasirahInsight:
        """Analyze an image from URL with contextual insight."""
        start = time.time()

        prompt = self._build_prompt(context, qalb_state)
        raw_result = await self._vision.analyze_image_url(url, prompt)

        insight = self._parse_result(raw_result)
        insight.processing_time_ms = (time.time() - start) * 1000
        return insight

    def _build_prompt(self, context: str, qalb_state: str = "") -> str:
        base = (
            "Analyze this image and respond in the following JSON format:\n"
            '{"description": "what you see in the image", '
            '"category": "text|diagram|screenshot|photo|document", '
            '"extracted_text": "any text visible in the image", '
            '"key_elements": ["element1", "element2"], '
            '"confidence": 0.0}\n'
            "Set confidence between 0.0 and 1.0 based on your certainty.\n"
        )
        if context:
            base += f"\nContext: {context}"

        # Qalb-aware perception: adjust focus based on emotional context
        if qalb_state and qalb_state != "neutral":
            focus_map = {
                "frustrated": "Pay special attention to error messages, warnings, or problematic elements.",
                "confused": "Focus on clarity — highlight text, labels, and structural elements.",
                "anxious": "Note any reassuring or concerning elements. Be thorough but gentle.",
                "determined": "Focus on actionable information and key data points.",
                "positive": "Highlight achievements, successes, and positive indicators.",
            }
            focus = focus_map.get(qalb_state, "")
            if focus:
                base += f"\n{focus}"

        return base

    def _parse_result(self, raw: str) -> BasirahInsight:
        """Parse raw vision output into structured insight."""
        if not raw:
            return BasirahInsight(
                description="No result from vision analysis",
                category="photo",
                confidence=0.0,
            )

        # Try to extract JSON from LLM response
        try:
            json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
            if json_match:
                parsed = _json.loads(json_match.group())
                return BasirahInsight(
                    description=str(parsed.get("description", raw[:500]))[:500],
                    category=self._validate_category(parsed.get("category", "")),
                    confidence=min(1.0, max(0.0, float(parsed.get("confidence", 0.7)))),
                    extracted_text=str(parsed.get("extracted_text", ""))[:2000],
                    key_elements=[str(e) for e in parsed.get("key_elements", [])][:20],
                )
        except (ValueError, KeyError, TypeError):
            pass

        # Fallback: heuristic parsing
        return BasirahInsight(
            description=raw[:500],
            category=self._guess_category(raw),
            confidence=0.6,  # Lower confidence for unparsed results
            extracted_text="",
            key_elements=[],
        )

    @staticmethod
    def _validate_category(category: str) -> str:
        """Validate and normalize the category string."""
        valid = {"text", "diagram", "screenshot", "photo", "document"}
        cat = category.lower().strip()
        return cat if cat in valid else "photo"

    @staticmethod
    def _guess_category(raw: str) -> str:
        """Heuristic category detection from raw text."""
        raw_lower = raw.lower()
        if any(w in raw_lower for w in ["screenshot", "interface", "ui", "window", "browser"]):
            return "screenshot"
        if any(w in raw_lower for w in ["diagram", "chart", "graph", "flow"]):
            return "diagram"
        if any(w in raw_lower for w in ["document", "page", "pdf", "form"]):
            return "document"
        if "error" in raw_lower and "text" in raw_lower:
            return "text"
        return "photo"
