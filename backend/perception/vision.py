"""
Vision Processing (Basar - بَصَر)
====================================

"He is the Hearing, the Seeing (Basar)" — Quran 42:11

Image understanding via Claude's multimodal API.
"""

import os
import base64
import logging
from typing import Optional

import anthropic

logger = logging.getLogger("mizan.vision")


class VisionProcessor:
    """
    Vision processing using Claude's multimodal capabilities.
    Analyzes images, screenshots, and documents.
    """

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self._model = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")

    async def analyze_image(self, image_bytes: bytes, prompt: str = "Describe this image",
                             media_type: str = "image/png") -> str:
        """Analyze an image using Claude Vision"""
        if not self._client:
            return "Vision processing unavailable: no API key configured"

        try:
            image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

            response = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }],
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"[VISION] Analysis failed: {e}")
            return f"Vision analysis error: {str(e)}"

    async def analyze_image_url(self, url: str, prompt: str = "Describe this image") -> str:
        """Analyze an image from a URL"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "image/png")
                    return await self.analyze_image(response.content, prompt, content_type)
                return f"Failed to fetch image: HTTP {response.status_code}"
        except Exception as e:
            return f"Failed to fetch image: {str(e)}"
