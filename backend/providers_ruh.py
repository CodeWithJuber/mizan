"""Ruh Model LLM Provider for MIZAN."""

import logging
from typing import Any, Literal

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
            self._tokenizer = self._model.tokenizer or BayanTokenizer.from_pretrained(
                self.model_path
            )
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

        from ruh_model.tokenizer.conversation import serialize_messages

        prompt = serialize_messages(messages, system=system)
        tokens = self._tokenizer.encode(prompt, add_eos=False)
        context_limit = getattr(getattr(self._model, "config", None), "max_seq_len", 2048)
        if isinstance(context_limit, int):
            tokens = tokens[-context_limit:]
        root_ids, pattern_ids = self._tokens_to_tensors(tokens)

        import torch

        with torch.no_grad():
            generated = self._model.generate(
                root_ids,
                pattern_ids,
                max_new_tokens=min(max_tokens or 256, 1024),
                temperature=1.0 if temperature is None else temperature,
                valid_n_roots=self._tokenizer._vocab.n_roots,
            )

        generated_root_ids = generated[0].tolist() if generated.ndim == 2 else generated.tolist()
        generated_root_ids = generated_root_ids[len(tokens) :]
        generated_tokens = [(int(root_id), 1) for root_id in generated_root_ids]
        output_text = self._tokenizer.decode(generated_tokens)

        return LLMResponse(
            content=[ContentBlock(type="text", text=output_text)],
            stop_reason="end_turn",
            model="ruh-local",
            usage={"input_tokens": len(tokens), "output_tokens": len(generated_root_ids)},
        )

    def stream(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ):
        """Stream an assistant turn.

        The Ruh model generates whole responses at once (no token-by-token
        streaming), so this wraps :meth:`create` and yields the complete text
        as a single chunk, matching the :class:`BaseLLMProvider` stream
        protocol used by the chat loop.
        """
        return _RuhStreamWrapper(
            self,
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            temperature=temperature,
        )

    def _extract_prompt(self, messages: list[dict]) -> str:
        """Get the text from the last user message."""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                texts = [block.get("text", "") for block in content if block.get("type") == "text"]
                return " ".join(texts)
            return str(content)
        return ""

    def _tokens_to_tensors(self, tokens: list) -> tuple:
        """Convert token pairs to root_id and pattern_id tensors."""
        import torch

        root_ids = torch.tensor(
            [[token[0] for token in tokens]], dtype=torch.long, device=self.device
        )
        pattern_ids = torch.tensor(
            [[token[1] for token in tokens]], dtype=torch.long, device=self.device
        )
        return root_ids, pattern_ids


class _RuhStreamWrapper:
    """Adapt :meth:`RuhModelProvider.create` to the provider stream protocol.

    The chat loop (``base.py`` / ``khalifah.py``) calls ``provider.stream(...)``
    as a context manager and reads ``text_stream`` for deltas, then
    ``get_final_response()`` for the complete response. Ruh has no native
    token streaming, so the full response is generated on ``__enter__`` and
    yielded as one chunk.
    """

    def __init__(
        self,
        provider: RuhModelProvider,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        temperature: float | None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._system = system
        self._messages = messages
        self._temperature = temperature
        self._response: LLMResponse | None = None

    def __enter__(self) -> "_RuhStreamWrapper":
        self._response = self._provider.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system,
            messages=self._messages,
            temperature=self._temperature,
        )
        return self

    def __exit__(self, *exc_info: object) -> Literal[False]:
        return False

    @property
    def text_stream(self):
        """Yield the response text as a single chunk."""
        if self._response is None:
            return
        for block in self._response.content:
            if block.type == "text" and block.text:
                yield block.text

    def get_final_response(self) -> LLMResponse:
        if self._response is None:
            raise RuntimeError("stream was not entered")
        return self._response
