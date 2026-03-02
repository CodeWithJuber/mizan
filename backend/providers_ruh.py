"""Ruh Model LLM Provider for MIZAN."""

import logging
from typing import Any

from providers import BaseLLMProvider, ContentBlock, LLMResponse

logger = logging.getLogger("mizan.providers.ruh")


class RuhModelProvider(BaseLLMProvider):
    """Local Ruh Model provider implementing the MIZAN LLM interface."""

    provider_name = "ruh"

    def __init__(self, model_path: str, device: str = "cpu") -> None:
        self.model_path = model_path
        self.device = device
        self._model: Any = None
        self._tokenizer: Any = None
        self._loaded: bool = False

    def _ensure_loaded(self) -> None:
        """Lazy-load model on first use."""
        if self._loaded:
            return
        try:
            from ruh_model.model import RuhModel
            from ruh_model.tokenizer.bayan import BayanTokenizer

            self._model = RuhModel.from_pretrained(self.model_path)
            self._model.to(self.device)
            # Set model to inference mode
            self._model.train(False)
            self._tokenizer = BayanTokenizer()
            self._loaded = True
            logger.info("Ruh Model loaded from %s on %s", self.model_path, self.device)
        except Exception as exc:
            logger.error("Failed to load Ruh Model: %s", exc)
            raise

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Generate a response using the local Ruh Model."""
        self._ensure_loaded()

        prompt = self._extract_prompt(messages)
        tokens = self._tokenizer.encode(prompt)
        root_ids, pattern_ids = self._tokens_to_tensors(tokens)

        import torch

        with torch.no_grad():
            generated = self._model.generate(
                root_ids,
                pattern_ids,
                max_new_tokens=min(max_tokens or 256, 1024),
                temperature=temperature or 1.0,
            )

        generated_root_ids = generated[0].tolist() if generated.ndim == 2 else generated.tolist()
        generated_tokens = [(int(root_id), 0) for root_id in generated_root_ids]
        output_text = self._tokenizer.decode(generated_tokens)

        return LLMResponse(
            content=[ContentBlock(type="text", text=output_text)],
            stop_reason="end_turn",
            model="ruh-local",
            usage={"input_tokens": len(tokens), "output_tokens": len(generated_root_ids)},
        )

    def _extract_prompt(self, messages: list[dict]) -> str:
        """Get the text from the last user message."""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                texts = [
                    block.get("text", "")
                    for block in content
                    if block.get("type") == "text"
                ]
                return " ".join(texts)
            return str(content)
        return ""

    def _tokens_to_tensors(self, tokens: list) -> tuple:
        """Convert token pairs to root_id and pattern_id tensors."""
        import torch

        root_ids = torch.tensor(
            [[token[0] for token in tokens]], dtype=torch.long
        )
        pattern_ids = torch.tensor(
            [[token[1] for token in tokens]], dtype=torch.long
        )
        return root_ids, pattern_ids
