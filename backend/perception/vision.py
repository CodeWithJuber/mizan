"""
Vision Processing (Basar - بَصَر)
====================================

"He is the Hearing, the Seeing (Basar)" — Quran 42:11

Image understanding via multimodal LLM APIs.
Supports Anthropic Claude Vision, OpenAI GPT-4o Vision, and OpenRouter.
"""

import os
import base64
import logging
from typing import Optional

from providers import create_provider, get_default_model

logger = logging.getLogger("mizan.vision")


class VisionProcessor:
    """
    Vision processing using multimodal LLM capabilities.
    Analyzes images, screenshots, and documents.
    Works with any provider that supports vision (Anthropic, OpenAI, OpenRouter).
    """

    def __init__(self):
        provider_name = os.getenv("LLM_PROVIDER", "") or None
        model = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
        self._provider = create_provider(provider=provider_name, model=model)
        self._model = model if model else (
            get_default_model(self._provider.provider_name) if self._provider else "claude-opus-4-6"
        )

    async def analyze_image(self, image_bytes: bytes, prompt: str = "Describe this image",
                             media_type: str = "image/png") -> str:
        """Analyze an image using the configured LLM provider's vision capabilities."""
        if not self._provider:
            return "Vision processing unavailable: no API key configured"

        try:
            image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

            # Use the unified provider interface
            response = self._provider.create(
                model=self._model,
                max_tokens=2048,
                system="You are a vision analysis assistant. Describe what you see accurately.",
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

            # Extract text from normalized response
            for block in response.content:
                if block.type == "text":
                    return block.text

            return "No text response from vision analysis"

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
