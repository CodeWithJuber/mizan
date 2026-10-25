"""The owned controller cannot call a hosted model, including on failure."""

import os
import threading
from collections.abc import Callable
from pathlib import Path

from mizan_owned.store import ReviewStore
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.auth import current_user_id

MODEL = "mizan-owned"
ABSTAIN = (
    "Mizan's own architecture cannot answer this request with the available reviewed "
    "memory or local reply checkpoint. More evidence or training is required. "
    "OpenRouter support must be requested separately."
)


def owned_only() -> bool:
    return (
        os.getenv("MIZAN_OWNED_ONLY", "").lower() in {"1", "true", "yes"}
        or os.getenv("LLM_PROVIDER", "") == MODEL
    )


def store_from_env() -> ReviewStore:
    return ReviewStore(os.getenv("MIZAN_OWNED_DB", "data/mizan_owned.sqlite3"))


def health() -> dict:
    checkpoint = os.getenv("MIZAN_REPLY_CHECKPOINT", "")
    return {
        "provider": MODEL,
        "status": "ok",
        "external_inference": False,
        "checkpoint_configured": bool(checkpoint),
        "checkpoint_exists": bool(checkpoint and Path(checkpoint).is_file()),
        "ready_for_general_chat": False,
        "fallback": "abstain",
    }


class OwnedProvider(BaseLLMProvider):
    provider_name = MODEL

    def __init__(
        self,
        store: ReviewStore | None = None,
        decoder: Callable[[dict, int], tuple[str, bool]] | None = None,
    ):
        self.store = store or store_from_env()
        self.decoder = decoder
        self._checkpoint = os.getenv("MIZAN_REPLY_CHECKPOINT", "")
        self._lock = threading.Lock()

    def _decode(self, request: dict, max_tokens: int) -> tuple[str, bool]:
        if self.decoder is not None:
            return self.decoder(request, max_tokens)
        if not self._checkpoint:
            return "", False
        from mizan_reply.data import encode_prompt
        from mizan_reply.evaluate import inference_device, load_inference_model
        from mizan_reply.generation import generate

        # Local research weights only; no downloads and no hosted fallback.
        with self._lock:
            if not hasattr(self, "_model"):
                self._device = inference_device("cpu")
                self._model, _, self._sha = load_inference_model(
                    self._checkpoint, self._device, include_sha256=True
                )
            messages = request["messages"]
            if request["system"]:
                messages = [{"role": "system", "content": request["system"]}, *messages]
            prompt = encode_prompt(messages, [], None, self._model.config.max_seq_len)
            result = generate(
                self._model,
                prompt["input_ids"].to(self._device),
                roots=prompt["roots"].to(self._device),
                max_new_tokens=min(max_tokens, 1024),
            )
            return result.text, result.eos

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        request = {"system": system, "messages": messages}
        owner = current_user_id()
        # Scope never comes from model text or caller-supplied JSON.
        recalled = self.store.recall(owner, request) if owner else None
        if recalled:
            return LLMResponse(
                [ContentBlock(type="text", text=recalled["answer"])],
                model=MODEL,
                usage={"owned_status": "reviewed_memory", "proposal_id": recalled["id"]},
            )
        try:
            text, complete = self._decode(request, max_tokens)
            if not text.strip() or not complete or "\ufffd" in text or len(text) > 100_000:
                text, status = ABSTAIN, "abstained"
            else:
                status = "own_model_unverified"
        except (ValueError, RuntimeError, OSError, ImportError, KeyError, TypeError):
            text, status = ABSTAIN, "abstained"
        usage = {"owned_status": status}
        if owner and status == "own_model_unverified":
            row = self.store.save(owner, request, text, "mizan-reply", True)
            usage["proposal_id"] = row["id"]
        # Model text is never parsed into tool calls. Existing Izn tools remain host-controlled.
        return LLMResponse([ContentBlock(type="text", text=text)], model=MODEL, usage=usage)
