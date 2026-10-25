"""Adapter for the pinned mizan-full-sft MiniMind RunPod worker contract.

MiniMind weights/tokenizer are unrelated to Ruh's root/pattern checkpoints.
No remote code, checkpoint, credentials, or training job is loaded here.
"""

from __future__ import annotations

import math
import os
from typing import cast

from providers import ContentBlock, LLMResponse
from providers_ruh_remote import RuhRemoteProvider

MODEL_ID = "Zubairshaikh/mizan-full-sft"
MODEL_REVISION = "2ecc917266a626db919fd6af154f9f0d3a286bcf"
CHECKPOINT_SHA256 = "4490faad19e43a3f6b8d78f665e62acddd9620e0b922ded0c1df75257be97814"


def configured() -> bool:
    return bool(os.getenv("MINIMIND_ENDPOINT_ID") and os.getenv("RUNPOD_API_KEY"))


class MiniMindRemoteProvider(RuhRemoteProvider):
    """Text-only queue worker, 2048 context and at most 256 generated tokens.

    The worker counts tokens with its training tokenizer and rejects overflow.
    We preserve messages rather than silently removing source text/history.
    """

    provider_name = "mizan-minimind"
    submission_path = "run"
    supports_tools = False
    context_window = 2048
    max_output_tokens = 256

    def _run_job(self, payload: dict) -> dict:
        # Get the job ID promptly, then poll; HTTP wait limits are not job limits.
        payload = {**payload, "policy": {"executionTimeout": 60000, "ttl": 120000}}
        return cast(dict, super()._run_job(payload))

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        if model not in ("", MODEL_ID, "mizan-minimind-full-sft"):
            raise ValueError("MiniMind endpoint serves only " + MODEL_ID)
        return super().create(model, max_tokens, system, messages, tools, temperature)

    def _build_input(self, max_tokens, system, messages, tools, temperature) -> dict:
        if tools:
            raise ValueError("This MiniMind checkpoint does not support tool calling")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        if temperature is not None and (not math.isfinite(temperature) or temperature < 0):
            raise ValueError("temperature must be finite and non-negative")
        chat = [{"role": "system", "content": system}] if system else []
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role not in {"system", "user", "assistant"}:
                raise ValueError("MiniMind supports only system/user/assistant text messages")
            if isinstance(content, list):
                if not all(isinstance(b, dict) and b.get("type") == "text" for b in content):
                    raise ValueError("MiniMind does not support image or tool-result blocks")
                content = "\n".join(b.get("text", "") for b in content)
            if not isinstance(content, str) or not content.strip():
                raise ValueError("MiniMind message content must be non-empty text")
            if role == "system" and chat:
                raise ValueError("System prompt must occur once at the beginning")
            chat.append({"role": role, "content": content})
        if not chat or chat[-1]["role"] != "user":
            raise ValueError("MiniMind generation requires a final user message")
        return {
            "messages": chat,
            "max_new_tokens": min(max_tokens, self.max_output_tokens),
            "do_sample": temperature is not None and temperature > 0,
            "temperature": temperature if temperature and temperature > 0 else 0.85,
        }

    def _parse_output(self, result: dict) -> LLMResponse:
        output = result["output"]
        text = output.get("response")
        if not isinstance(text, str):
            raise ValueError("MiniMind worker response must contain response text")
        identity = output.get("model")
        if not isinstance(identity, dict) or identity.get("checkpoint_sha256") != CHECKPOINT_SHA256:
            raise ValueError("MiniMind worker checkpoint does not match the configured release")
        finish = output.get("finish_reason")
        if finish not in {"eos", "length"}:
            raise ValueError("MiniMind worker returned an unknown finish reason")
        usage = output.get("usage", {})
        return LLMResponse(
            content=[ContentBlock(type="text", text=text)],
            stop_reason="end_turn" if finish == "eos" else "max_tokens",
            model=MODEL_ID,
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "checkpoint_sha256": CHECKPOINT_SHA256,
            },
        )
