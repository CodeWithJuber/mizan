"""The owned controller cannot call a hosted model, including on failure."""

import os
import pickle
import re
import threading
from collections.abc import Callable
from pathlib import Path

from mizan_owned.prompt import OwnedPromptOverflow, prepare_prompt
from mizan_owned.store import ReviewStore
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.auth import current_user_id

MODEL = "mizan-owned"
ABSTAIN = (
    "Mizan's own architecture cannot answer this request with the available reviewed "
    "memory or local reply checkpoint. More evidence or training is required. "
    "OpenRouter support must be requested separately."
)


class OwnedCheckpointUnavailable(ValueError):
    """A safe operator-facing reason; never includes checkpoint paths or contents."""

    MESSAGES = {
        "registry_no_active_checkpoint": "The local checkpoint registry has no active checkpoint.",
        "registry_invalid": "The local checkpoint registry could not be verified.",
        "registry_decoder_override": "A custom decoder cannot replace the configured registry.",
        "checkpoint_hash_mismatch": "The loaded checkpoint does not match the promoted hash.",
        "checkpoint_load_failed": "The selected local checkpoint could not be loaded safely.",
    }

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(self.MESSAGES[reason])


def owned_only() -> bool:
    return (
        os.getenv("MIZAN_OWNED_ONLY", "").lower() in {"1", "true", "yes"}
        or os.getenv("LLM_PROVIDER", "") == MODEL
    )


def store_from_env() -> ReviewStore:
    return ReviewStore(os.getenv("MIZAN_OWNED_DB", "data/mizan_owned.sqlite3"))


def health() -> dict:
    checkpoint = os.getenv("MIZAN_REPLY_CHECKPOINT", "")
    result = {
        "provider": MODEL,
        "status": "ok",
        "controller_healthy": True,
        "health_scope": "controller_not_general_model_readiness",
        "external_inference": False,
        "checkpoint_configured": bool(checkpoint),
        "checkpoint_exists": bool(checkpoint and Path(checkpoint).is_file()),
        # Legacy configuration has no promotion receipt to verify here.
        "checkpoint_ready": False,
        "checkpoint_source": "environment" if checkpoint else "none",
        "registry_configured": False,
        "ready_for_general_chat": False,
        "fallback": "abstain",
    }
    root = os.getenv("MIZAN_OWNED_LEARNING_DIR", "").strip()
    if not root:
        return result
    try:
        from mizan_owned.learning_cycle import registry_status

        registry = registry_status(root)
        if not isinstance(registry, dict):
            raise ValueError("Invalid registry health response")
    except Exception:
        # Registry faults are visible in health, never a reason to read legacy weights.
        registry = {"status": "invalid", "reason": "registry_invalid", "active": None}
    invalid = registry.get("status") == "invalid"
    active = registry.get("active") if not invalid else None
    result.update(
        {
            "status": "invalid" if invalid else "ok",
            "checkpoint_configured": bool(active),
            "checkpoint_exists": bool(active),
            "checkpoint_ready": bool(active),
            "checkpoint_source": "registry",
            "registry_configured": True,
            "registry_generation": registry.get("generation"),
            "registry": registry,
        }
    )
    return result


class OwnedProvider(BaseLLMProvider):
    provider_name = MODEL
    supports_tools = False

    def __init__(
        self,
        store: ReviewStore | None = None,
        decoder: Callable[[dict, int], tuple[str, bool]] | None = None,
    ):
        self.store = store or store_from_env()
        self.decoder = decoder
        self._checkpoint = os.getenv("MIZAN_REPLY_CHECKPOINT", "")
        self._lock = threading.RLock()
        self._loaded_checkpoint: tuple[str, str, str | None] | None = None

    def _select_checkpoint(self, root: str) -> dict | None:
        if not root:
            return {"source": "environment", "path": self._checkpoint} if self._checkpoint else None
        try:
            from mizan_owned.learning_cycle import resolve_active

            selected = resolve_active(root)
            if selected is None:
                raise OwnedCheckpointUnavailable("registry_no_active_checkpoint")
            if (
                not isinstance(selected, dict)
                or not isinstance(selected.get("path"), str)
                or not Path(selected["path"]).is_absolute()
                or not isinstance(selected.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", selected["sha256"]) is None
                or type(selected.get("generation")) is not int
                or selected["generation"] < 0
            ):
                raise ValueError("Invalid checkpoint selection")
            return {**selected, "source": "registry"}
        except OwnedCheckpointUnavailable:
            raise
        except Exception as exc:
            # This is the registry boundary: malformed state or an implementation
            # fault must abstain rather than bypass its active-selection policy.
            raise OwnedCheckpointUnavailable("registry_invalid") from exc

    def _decode(self, request: dict, max_tokens: int) -> tuple[str, bool]:
        text, complete, _ = self._decode_with_receipt(request, max_tokens)
        return text, complete

    def _decode_with_receipt(
        self, request: dict, max_tokens: int, *, checkpoint_receipt: dict | None = None
    ) -> tuple[str, bool, dict]:
        # Resolve once per request, then pin this model until generation finishes.
        # Promotion/rollback during generation takes effect on the next request.
        with self._lock:
            root = os.getenv("MIZAN_OWNED_LEARNING_DIR", "").strip()
            if self.decoder is not None:
                if root:
                    raise OwnedCheckpointUnavailable("registry_decoder_override")
                text, complete = self.decoder(request, max_tokens)
                return text, complete, {}
            selected = self._select_checkpoint(root)
            if selected is None:
                return "", False, {}
            try:
                from mizan_reply.data import encode_prompt
                from mizan_reply.evaluate import inference_device, load_inference_model
                from mizan_reply.generation import generate
            except ImportError as exc:
                raise OwnedCheckpointUnavailable("checkpoint_load_failed") from exc

            identity = (selected["source"], selected["path"], selected.get("sha256"))
            if self._loaded_checkpoint != identity:
                try:
                    device = inference_device("cpu")
                    loaded, _, digest = load_inference_model(
                        selected["path"], device, include_sha256=True
                    )
                except (
                    ValueError,
                    RuntimeError,
                    OSError,
                    KeyError,
                    TypeError,
                    EOFError,
                    pickle.UnpicklingError,
                ) as exc:
                    raise OwnedCheckpointUnavailable("checkpoint_load_failed") from exc
                if selected["source"] == "registry" and digest != selected["sha256"]:
                    raise OwnedCheckpointUnavailable("checkpoint_hash_mismatch")
                # Install only the verified snapshot; a failed switch cannot poison
                # the last verified model or cause it to answer for the new selection.
                self._model, self._device, self._sha = loaded, device, digest
                self._loaded_checkpoint = identity
            if checkpoint_receipt is not None:
                checkpoint_receipt.update({"source": selected["source"], "sha256": self._sha})
                if selected["source"] == "registry":
                    checkpoint_receipt["generation"] = selected["generation"]
            messages, receipt = prepare_prompt(request, self._model.config.max_seq_len, max_tokens)
            prompt = encode_prompt(messages, [], None, self._model.config.max_seq_len)
            result = generate(
                self._model,
                prompt["input_ids"].to(self._device),
                roots=prompt["roots"].to(self._device),
                max_new_tokens=receipt["output_tokens"],
            )
            return result.text, result.eos, receipt

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        with self._lock:
            return self._create_locked(max_tokens, system, messages)

    def _create_locked(self, max_tokens: int, system: str, messages: list[dict]) -> LLMResponse:
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
        receipt: dict = {}
        checkpoint_receipt: dict = {}
        reason = ""
        try:
            text, complete, receipt = self._decode_with_receipt(
                request, max_tokens, checkpoint_receipt=checkpoint_receipt
            )
            if not text.strip() or not complete or "\ufffd" in text or len(text) > 100_000:
                text, status = ABSTAIN, "abstained"
            else:
                status = "own_model_unverified"
        except OwnedCheckpointUnavailable as exc:
            reason = exc.reason
            text = f"{exc} {ABSTAIN}"
            status = "abstained"
        except OwnedPromptOverflow as exc:
            receipt = exc.receipt
            reason = "context_budget_exceeded"
            text = (
                "Mizan's local reply checkpoint cannot fit the preserved instructions and "
                f"conversation ({receipt['prompt_tokens']} byte/framing tokens) while reserving "
                f"{receipt['minimum_output_tokens']} output tokens within its "
                f"{receipt['context_limit']}-token limit. No instructions, preferences, history "
                "or current input were removed. Use a larger-context local checkpoint or start "
                "a shorter conversation. OpenRouter support must be requested separately."
            )
            status = "abstained"
        except (ValueError, RuntimeError, OSError, ImportError, KeyError, TypeError):
            text, status = ABSTAIN, "abstained"
        usage: dict = {"owned_status": status}
        if receipt:
            usage["owned_prompt"] = receipt
        if checkpoint_receipt:
            usage["owned_checkpoint"] = checkpoint_receipt
        if reason:
            usage["owned_reason"] = reason
        if owner and status == "own_model_unverified":
            row = self.store.save(owner, request, text, "mizan-reply", True)
            usage["proposal_id"] = row["id"]
        # Model text is never parsed into tool calls. Existing Izn tools remain host-controlled.
        return LLMResponse([ContentBlock(type="text", text=text)], model=MODEL, usage=usage)
