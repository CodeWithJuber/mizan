"""
LLM Provider Abstraction (Ruh al-Ilm - روح العلم)
=====================================================

"Say: The Spirit (Ruh) is from the command of my Lord" — Quran 17:85

Unified interface for multiple LLM providers:
- Anthropic (Claude) — native tool_use API
- OpenRouter — 300+ models via OpenAI-compatible API
- OpenAI — GPT-4o, o1, etc.
- Ollama — local/self-hosted models

All providers return normalized response objects so the agentic loop
works identically regardless of the backend.
"""

import json
import logging
import math
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv

# Load .env so os.getenv() picks up API keys
load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger("mizan.providers")


def _answer_reasoning_options(provider_name: str, model: str, max_tokens: int) -> dict:
    """Reserve output space only for models with verified budget support.

    OpenRouter's Nemotron 3.5 Super VL listing documents default-on reasoning
    and a reasoning token budget. Reasoning shares the output limit; excluding
    it from the response would not save tokens. Do not guess support from a
    model-name prefix or send OpenRouter extensions to other API providers.
    Sources checked 2026-10-26:
    https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
    https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free
    """
    if provider_name != "openrouter" or model not in {
        "nvidia/nemotron-3.5-super-vl",
        "nvidia/nemotron-3.5-super-vl:free",
    }:
        return {}
    # A small explicit output limit should still leave room for an answer.
    reasoning = (
        {"max_tokens": min(1024, max_tokens // 4)} if max_tokens >= 2048 else {"enabled": False}
    )
    return {"extra_body": {"reasoning": reasoning}}


_OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5", "gpt-6")


# OpenRouter catalog facts (id → free/tools/context), refreshed with the limits.
_OPENROUTER_CATALOG: dict[str, dict[str, Any]] = {}


def openrouter_fallback_models(model: str, needs_tools: bool) -> list[str]:
    """Models OpenRouter tries, in order, when the primary model errors.

    The gateway handles the failover inside the same request, so MIZAN never
    re-sends anything. ``MIZAN_OPENROUTER_FALLBACKS`` is ``auto`` (default),
    ``none`` or a comma-separated list. ``auto`` only adds free models for a
    free primary, so a failover never changes what a request costs; models
    from the same vendor and with the largest context are preferred.
    """
    setting = os.getenv("MIZAN_OPENROUTER_FALLBACKS", "auto").strip()
    if not model or setting.lower() in {"none", "off", "false", "0"}:
        return []
    if setting.lower() not in {"", "auto"}:
        chosen = [item.strip() for item in setting.split(",")]
        return [item for item in dict.fromkeys(chosen) if item and item != model][:3]
    if not model.endswith(":free"):
        return []
    vendor = model.split("/", 1)[0]
    candidates = [
        (entry_id, info)
        for entry_id, info in _OPENROUTER_CATALOG.items()
        if entry_id != model and info.get("free") and (info.get("tools") or not needs_tools)
    ]
    candidates.sort(
        key=lambda item: (
            item[0].split("/", 1)[0] != vendor,
            -int(item[1].get("context") or 0),
            item[0],
        )
    )
    return [entry_id for entry_id, _ in candidates[:2]]


def _adapt_openai_request(provider_name: str, kwargs: dict) -> dict:
    """Provider-specific request fields for the OpenAI-compatible protocol.

    OpenRouter gets its native model fallbacks. OpenAI's own API takes
    ``max_completion_tokens`` and reasoning-class models accept only the
    default temperature. OpenRouter and Ollama keep ``max_tokens``.
    """
    if provider_name == "openrouter":
        fallbacks = openrouter_fallback_models(
            str(kwargs.get("model", "")), bool(kwargs.get("tools"))
        )
        if fallbacks:
            extra = dict(kwargs.get("extra_body") or {})
            extra["models"] = [kwargs["model"], *fallbacks]
            kwargs["extra_body"] = extra
        return kwargs
    if provider_name != "openai":
        return kwargs
    if "max_tokens" in kwargs:
        kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
    if str(kwargs.get("model", "")).startswith(_OPENAI_REASONING_PREFIXES):
        kwargs.pop("temperature", None)
    return kwargs


def _reasoning_usage(usage: dict, reasoning_observed: bool = False) -> dict:
    """Keep reported counters, never convert private reasoning into answer text."""
    raw = usage.get("raw", usage)
    details = raw.get("completion_tokens_details") if isinstance(raw, dict) else None
    count = details.get("reasoning_tokens") if isinstance(details, dict) else None
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        usage["reasoning_tokens"] = count
        total = usage.get("output")
        if isinstance(total, int) and not isinstance(total, bool) and total >= count:
            usage["visible_output_tokens"] = total - count
        reasoning_observed = reasoning_observed or count > 0
    if reasoning_observed:
        usage["reasoning_observed"] = True
    return usage


def _has_reasoning(message) -> bool:
    return any(
        bool(getattr(message, key, None))
        for key in ("reasoning", "reasoning_content", "reasoning_details")
    )


def _sdk_request_options(timeout_type) -> dict[str, Any]:
    """Bound SDK I/O waits and retries; a healthy stream can run longer.

    Retries stay disabled: socket failures do not prove a generation POST was
    rejected before execution. Agent recovery must not replay it either.
    """
    try:
        seconds = float(os.getenv("MIZAN_LLM_TIMEOUT_SECONDS", "60"))
        if not math.isfinite(seconds):
            raise ValueError("non-finite timeout")
    except ValueError:
        logger.warning("Invalid MIZAN_LLM_TIMEOUT_SECONDS; using 60 seconds")
        seconds = 60.0
    seconds = max(1.0, min(seconds, 180.0))
    return {
        "timeout": timeout_type(seconds, connect=min(5.0, seconds)),
        # A timed-out generation POST may already be accepted/billed. Retrying
        # inside an SDK is no safer than replaying it at the agent layer.
        "max_retries": 0,
    }


# ───── Normalized Response Types ─────


@dataclass
class ContentBlock:
    """A single block in an LLM response (text or tool_use)."""

    type: str  # "text" or "tool_use"
    text: str = ""
    id: str = ""  # tool_use block id
    name: str = ""  # tool name
    input: dict = field(default_factory=dict)  # tool input params


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: list[ContentBlock]
    stop_reason: str = "end_turn"  # "end_turn" or "tool_use"
    model: str = ""
    usage: dict = field(default_factory=dict)
    # Provider-native assistant content to send back unchanged on the next
    # call of the same run (Anthropic thinking/compaction/fallback blocks).
    raw_content: list[dict] | None = None


class IncompleteToolCall(ValueError):
    """A completed provider turn whose tool call was cut off by the output limit.

    ``partial`` holds the turn's visible text only; the cut-off call never runs.
    """

    def __init__(self, partial: "LLMResponse | None" = None):
        self.partial = partial or LLMResponse(content=[], stop_reason="max_tokens")
        super().__init__("Provider returned an incomplete tool call")


class ProviderRefusal(RuntimeError):
    """The provider declined the request (Anthropic ``stop_reason: refusal``)."""

    def __init__(self, category: str | None = None):
        self.category = category
        super().__init__(f"The model declined this request ({category or 'unspecified'})")


def content_block_to_dict(block: Any) -> dict:
    """Serialise a normalized or SDK content block for a provider request."""
    if isinstance(block, dict):
        return block
    if isinstance(block, ContentBlock):
        if block.type == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
        return {"type": "text", "text": block.text}
    to_dict = getattr(block, "to_dict", None)
    if callable(to_dict):
        return cast(dict, to_dict())
    return {"type": "text", "text": str(getattr(block, "text", block))}


def assistant_turn_content(response: "LLMResponse") -> list[dict]:
    """Content to append for an assistant turn, preserving provider-native blocks."""
    if response.raw_content:
        return list(response.raw_content)
    return [content_block_to_dict(block) for block in response.content]


# ───── Provider Interface ─────


class BaseLLMProvider:
    """Base class for all LLM providers."""

    provider_name: str = "base"

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    def stream(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ):
        """Return a context manager with text_stream and get_final_response."""
        return _BufferedStreamWrapper(self, model, max_tokens, system, messages, tools, temperature)


# ───── Anthropic Provider ─────
#
# Requests follow API version 2026-10-21 (anthropic SDK 2.x): no sampling
# parameters, adaptive thinking left on by default, effort via output_config.
# Assistant turns are replayed with their thinking blocks unchanged, which the
# preserved-thinking check requires inside one tool loop.

_CLAUDE_MODEL = re.compile(
    r"^(?:anthropic/)?claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:-(\d+))?"
)
_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_COMPACTION_BETA = "compact-2026-01-12"
# Server-side ``fallbacks: "default"`` is documented for these models.
_DEFAULT_FALLBACK_MODELS = {
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
}


def claude_version(model: str) -> tuple[str, float] | None:
    """Return (family, version) for a Claude model ID, ignoring date suffixes."""
    match = _CLAUDE_MODEL.match(model or "")
    if not match:
        return None
    family, major, minor = match.groups()
    # A dated snapshot ID (claude-sonnet-4-20250514) carries a date, not a minor.
    minor_value = int(minor) if minor and len(minor) <= 2 else 0
    return family, int(major) + minor_value / 10


def anthropic_effort(model: str) -> str | None:
    """Configured effort for models that accept ``output_config.effort``."""
    version = claude_version(model)
    if version is None:
        return None
    family, number = version
    supported = (
        family in {"fable", "mythos"}
        or (family == "opus" and number >= 4.5)
        or (family == "sonnet" and number >= 4.6)
        or (family == "haiku" and number >= 5)
    )
    if not supported:
        return None
    level = os.getenv("MIZAN_CHAT_EFFORT", "high").strip().lower()
    if level not in _EFFORT_LEVELS:
        level = "high"
    # xhigh arrived with 4.7; Opus 4.5 knows only low/medium/high.
    if level == "xhigh" and family in {"opus", "sonnet"} and number < 4.7:
        level = "high"
    if level == "max" and family == "opus" and number < 4.6:
        level = "high"
    return level


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _anthropic_messages(messages: list) -> list[dict]:
    """Normalize history for the Messages API.

    Empty assistant turns are dropped (the API rejects them), legacy
    ``role: system`` history entries become user context, and normalized
    content blocks are serialised.
    """
    normalized: list[dict] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, list):
            content = [content_block_to_dict(block) for block in content]
            if role == "assistant":
                content = [
                    block
                    for block in content
                    if not (block.get("type") == "text" and not str(block.get("text", "")).strip())
                ]
            if not content:
                continue
        elif not isinstance(content, str) or not content.strip():
            continue
        if role == "system":
            text = content if isinstance(content, str) else json.dumps(content)
            normalized.append(
                {"role": "user", "content": f"[Earlier conversation context]\n{text}"}
            )
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _strip_thinking(messages: list[dict]) -> list[dict]:
    stripped = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            content = [
                block
                for block in content
                if not (
                    isinstance(block, dict)
                    and block.get("type") in {"thinking", "redacted_thinking"}
                )
            ]
            if not content:
                continue
        stripped.append({**message, "content": content})
    return stripped


def _is_thinking_binding_error(exc: Exception) -> bool:
    text = str(exc)
    return "thinking" in text and ("signature" in text or "bound to a different" in text)


def _anthropic_usage(usage: Any) -> dict:
    result = {"input": usage.input_tokens, "output": usage.output_tokens}
    for source, key in (
        ("cache_read_input_tokens", "cache_read"),
        ("cache_creation_input_tokens", "cache_creation"),
    ):
        value = getattr(usage, source, None)
        if isinstance(value, int) and not isinstance(value, bool):
            result[key] = value
    return result


def _text_only(content: Any, stop_reason: str = "max_tokens") -> "LLMResponse":
    texts = [
        ContentBlock(type="text", text=str(getattr(block, "text", "")))
        for block in content or []
        if getattr(block, "type", None) == "text" and getattr(block, "text", "")
    ]
    return LLMResponse(content=texts, stop_reason=stop_reason or "max_tokens")


def _anthropic_response(message: Any) -> "LLMResponse":
    if getattr(message, "stop_reason", None) == "refusal":
        details = getattr(message, "stop_details", None)
        raise ProviderRefusal(getattr(details, "category", None))
    if message.stop_reason not in {"tool_use", "end_turn", "pause_turn"} and any(
        block.type == "tool_use" for block in message.content
    ):
        raise IncompleteToolCall(_text_only(message.content, message.stop_reason))
    blocks = []
    for block in message.content:
        if block.type == "text":
            blocks.append(ContentBlock(type="text", text=block.text))
        elif block.type == "tool_use":
            blocks.append(
                ContentBlock(type="tool_use", id=block.id, name=block.name, input=block.input)
            )
    return LLMResponse(
        content=blocks,
        stop_reason=message.stop_reason,
        model=message.model,
        usage=_anthropic_usage(message.usage),
        raw_content=[content_block_to_dict(block) for block in message.content],
    )


class AnthropicProvider(BaseLLMProvider):
    """Native Anthropic Claude API with tool_use support."""

    provider_name = "anthropic"

    def __init__(self, api_key: str):
        import anthropic

        self._client = anthropic.Anthropic(
            api_key=api_key, **_sdk_request_options(anthropic.Timeout)
        )

    def _request(self, model, max_tokens, system, messages, tools, *, streaming: bool):
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": _anthropic_messages(messages),
        }
        if tools:
            # Streamed tool input arrives incrementally, so long file writes
            # show progress instead of one burst at the end of the call.
            kwargs["tools"] = (
                [{**tool, "eager_input_streaming": True} for tool in tools] if streaming else tools
            )
        effort = anthropic_effort(model)
        if effort:
            kwargs["output_config"] = {"effort": effort}
        if _env_flag("MIZAN_ANTHROPIC_PROMPT_CACHE", True):
            kwargs["cache_control"] = {"type": "ephemeral"}
        betas: list[str] = []
        if model in _DEFAULT_FALLBACK_MODELS and _env_flag("MIZAN_ANTHROPIC_FALLBACKS", True):
            betas.append(_FALLBACK_BETA)
            kwargs["fallbacks"] = "default"
        version = claude_version(model)
        if (
            version is not None
            and (version[0] in {"fable", "mythos"} or version[1] >= 4.6)
            and _env_flag("MIZAN_ANTHROPIC_COMPACTION", True)
        ):
            # Server-side compaction keeps one long tool run inside the window
            # and, unlike client-side edits, keeps thinking blocks valid.
            window, _ = model_limits(model)
            betas.append(_COMPACTION_BETA)
            kwargs["context_management"] = {
                "edits": [
                    {
                        "type": "compact_20260112",
                        "trigger": {
                            "type": "input_tokens",
                            "value": max(50_000, min(150_000, window // 2)),
                        },
                    }
                ]
            }
        if betas:
            kwargs["betas"] = betas
        return kwargs

    def _messages_api(self, kwargs: dict):
        return self._client.beta.messages if "betas" in kwargs else self._client.messages

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        # ``temperature`` is accepted for interface parity and never sent:
        # API version 2026-10-21 rejects sampling parameters.
        import anthropic

        kwargs = self._request(model, max_tokens, system, messages, tools, streaming=False)
        try:
            response = self._messages_api(kwargs).create(**kwargs)
        except anthropic.BadRequestError as exc:
            # Rejected before any output: replay without thinking once.
            if not _is_thinking_binding_error(exc):
                raise
            kwargs["messages"] = _strip_thinking(kwargs["messages"])
            response = self._messages_api(kwargs).create(**kwargs)
        return _anthropic_response(response)

    def stream(self, model, max_tokens, system, messages, tools=None, temperature=None):
        kwargs = self._request(model, max_tokens, system, messages, tools, streaming=True)
        return _AnthropicStreamWrapper(
            lambda request: self._messages_api(request).stream(**request), kwargs
        )


# ───── OpenAI-Compatible Provider (OpenAI + OpenRouter) ─────


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    OpenAI-compatible API provider.
    Works with OpenAI, OpenRouter, and any OpenAI-compatible endpoint.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        default_headers: dict | None = None,
        provider_name: str = "openai",
    ):
        from openai import OpenAI, Timeout

        kwargs: dict[str, Any] = {"api_key": api_key, **_sdk_request_options(Timeout)}
        if base_url:
            kwargs["base_url"] = base_url
        if default_headers:
            kwargs["default_headers"] = default_headers
        self._client = OpenAI(**kwargs)
        self.provider_name = provider_name

    @staticmethod
    def _parse_xml_tool_calls(text: str) -> list["ContentBlock"]:
        """Extract tool calls embedded as XML in model text output.

        Handles formats like:
          <invoke name="tool_name"><parameter name="key">value</parameter></invoke>
          <minimax:tool_call>...<invoke name="tool_name">...</invoke></minimax:tool_call>
        """
        # Match <invoke name="...">...</invoke> blocks
        invoke_pattern = re.compile(
            r'<invoke\s+name="([^"]+)"[^>]*>(.*?)</invoke>',
            re.DOTALL,
        )
        param_pattern = re.compile(
            r'<parameter\s+name="([^"]+)"[^>]*>(.*?)</parameter>',
            re.DOTALL,
        )
        tool_blocks: list[ContentBlock] = []
        for match in invoke_pattern.finditer(text):
            tool_name = match.group(1).strip()
            body = match.group(2)
            params: dict = {}
            for param_match in param_pattern.finditer(body):
                key = param_match.group(1).strip()
                value = param_match.group(2).strip()
                # Try to parse JSON values
                try:
                    params[key] = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    params[key] = value
            tool_blocks.append(
                ContentBlock(
                    type="tool_use",
                    id=f"xmltool_{uuid.uuid4().hex[:12]}",
                    name=tool_name,
                    input=params,
                )
            )
        return tool_blocks

    @staticmethod
    def _strip_xml_tool_calls(text: str) -> str:
        """Remove XML tool-call markup from text, keeping surrounding prose."""
        # Remove <minimax:tool_call>...</minimax:tool_call> wrappers
        cleaned = re.sub(
            r"<minimax:tool_call>.*?</minimax:tool_call>",
            "",
            text,
            flags=re.DOTALL,
        )
        # Remove bare <invoke>...</invoke> blocks
        cleaned = re.sub(
            r'<invoke\s+name="[^"]*"[^>]*>.*?</invoke>',
            "",
            cleaned,
            flags=re.DOTALL,
        )
        # Collapse multiple blank lines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    def _convert_tools_to_openai(self, tools: list[dict]) -> list[dict]:
        """Convert Anthropic tool schemas to OpenAI function calling format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get(
                            "input_schema", {"type": "object", "properties": {}}
                        ),
                    },
                }
            )
        return openai_tools

    def _convert_messages_to_openai(self, system: str, messages: list[dict]) -> list[dict]:
        """Convert Anthropic-style messages to OpenAI format.

        Key: OpenAI requires a single assistant message with both content AND
        tool_calls (not separate messages). Tool results must have string content.
        """
        openai_messages = [{"role": "system", "content": system}]

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Collect all parts from this Anthropic message into one OpenAI message
                text_parts = []
                tool_calls = []
                tool_results = []

                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "")
                        if block_type == "tool_result":
                            raw_content = block.get("content", "")
                            # Ensure content is a string
                            if not isinstance(raw_content, str):
                                raw_content = json.dumps(raw_content) if raw_content else ""
                            tool_results.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": block.get("tool_use_id", ""),
                                    "content": raw_content,
                                }
                            )
                        elif block_type == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block.get("id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": block.get("name", ""),
                                        "arguments": json.dumps(block.get("input", {})),
                                    },
                                }
                            )
                        elif block_type == "text":
                            text_parts.append(block.get("text", ""))
                    elif hasattr(block, "type"):
                        # Content block object from Anthropic SDK
                        if block.type == "text":
                            text_parts.append(block.text)
                        elif block.type == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block.id,
                                    "type": "function",
                                    "function": {
                                        "name": block.name,
                                        "arguments": json.dumps(block.input),
                                    },
                                }
                            )

                # Emit a single assistant message with text + tool_calls combined
                if role == "assistant" and (text_parts or tool_calls):
                    assistant_msg: dict[str, Any] = {"role": "assistant"}
                    combined_text = "\n".join(text_parts)
                    if combined_text:
                        assistant_msg["content"] = combined_text
                    elif tool_calls:
                        assistant_msg["content"] = None
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls
                    openai_messages.append(assistant_msg)
                elif text_parts:
                    openai_messages.append({"role": role, "content": "\n".join(text_parts)})

                # Tool results are always separate messages with role="tool"
                openai_messages.extend(tool_results)
            else:
                openai_messages.append({"role": role, "content": str(content)})

        return openai_messages

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        openai_messages = self._convert_messages_to_openai(system, messages)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": openai_messages,
        }
        if tools:
            kwargs["tools"] = self._convert_tools_to_openai(tools)
        if temperature is not None:
            kwargs["temperature"] = temperature

        kwargs.update(_answer_reasoning_options(self.provider_name, model, max_tokens))
        response = self._client.chat.completions.create(
            **_adapt_openai_request(self.provider_name, kwargs)
        )
        choice = response.choices[0]
        message = choice.message

        blocks = []

        # Text content
        if message.content:
            blocks.append(ContentBlock(type="text", text=message.content))

        # Tool calls (structured API)
        if message.tool_calls:
            if choice.finish_reason not in {"tool_calls", "stop"}:
                raise IncompleteToolCall(
                    LLMResponse(
                        content=[ContentBlock(type="text", text=message.content)]
                        if message.content
                        else [],
                        stop_reason="max_tokens",
                    )
                )
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ValueError("Provider returned malformed tool arguments") from exc
                if not isinstance(args, dict):
                    raise ValueError("Provider tool arguments must be an object")
                blocks.append(
                    ContentBlock(
                        type="tool_use",
                        id=tc.id,
                        name=tc.function.name,
                        input=args,
                    )
                )

        # Fallback: parse XML-style tool calls from text (MiniMax, etc.)
        if (
            not message.tool_calls
            and message.content
            and tools
            and choice.finish_reason in {"tool_calls", "stop"}
        ):
            xml_tools = self._parse_xml_tool_calls(message.content)
            if xml_tools:
                # Remove XML from text block, replace with cleaned text
                cleaned = self._strip_xml_tool_calls(message.content).strip()
                blocks = []
                if cleaned:
                    blocks.append(ContentBlock(type="text", text=cleaned))
                blocks.extend(xml_tools)

        # Unknown/filtered finishes are incomplete, never reviewable teacher answers.
        has_tool_blocks = any(b.type == "tool_use" for b in blocks)
        stop_reason = "incomplete"
        if choice.finish_reason == "tool_calls" or has_tool_blocks:
            stop_reason = "tool_use"
        elif choice.finish_reason == "length":
            stop_reason = "max_tokens"
        elif choice.finish_reason == "stop":
            stop_reason = "end_turn"

        usage = {}
        if response.usage is not None:
            raw = (
                response.usage.model_dump()
                if hasattr(response.usage, "model_dump")
                else vars(response.usage)
            )
            usage = {key: value for key, value in raw.items() if value is not None}
            for native, normalized in (("prompt_tokens", "input"), ("completion_tokens", "output")):
                if native in usage:
                    usage[normalized] = usage[native]
        _reasoning_usage(usage, _has_reasoning(message))
        return LLMResponse(
            content=blocks,
            stop_reason=stop_reason,
            model=response.model,
            usage=usage,
        )

    def stream(self, model, max_tokens, system, messages, tools=None, temperature=None):
        return _OpenAIStreamWrapper(
            self._client,
            model,
            max_tokens,
            self._convert_messages_to_openai(system, messages),
            self._convert_tools_to_openai(tools) if tools else None,
            temperature,
            request_options=_answer_reasoning_options(self.provider_name, model, max_tokens),
            provider_name=self.provider_name,
        )


class _BufferedStreamWrapper:
    """Adapter for providers without native deltas; runs in the agent's worker thread."""

    def __init__(self, provider, model, max_tokens, system, messages, tools=None, temperature=None):
        self.provider = provider
        self.kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            temperature=temperature,
        )
        self.response = None

    def __enter__(self):
        self.response = self.provider.create(**self.kwargs)
        return self

    def __exit__(self, *args):
        return False

    @property
    def text_stream(self):
        for block in self.get_final_response().content:
            if block.type == "text" and block.text:
                yield block.text

    def get_final_response(self):
        if self.response is None:
            raise RuntimeError("stream was not entered")
        return self.response


class _AnthropicStreamWrapper:
    def __init__(self, open_stream, request: dict | None = None):
        # ``open_stream(request)`` returns an SDK MessageStreamManager. A bare
        # manager is still accepted for callers that build their own.
        if request is None:
            manager = open_stream
            open_stream = lambda _request: manager  # noqa: E731
        self._open_stream = open_stream
        self._request = request or {}
        self.manager = None
        self.stream = None
        self._progress_callback: Callable[[], None] | None = None

    def set_progress_callback(self, callback: Callable[[], None]) -> None:
        self._progress_callback = callback

    def __enter__(self):
        import anthropic

        self.manager = self._open_stream(self._request)
        try:
            self.stream = self.manager.__enter__()
        except anthropic.BadRequestError as exc:
            # The request was rejected before any output was produced.
            if not _is_thinking_binding_error(exc) or "messages" not in self._request:
                raise
            self._request = {
                **self._request,
                "messages": _strip_thinking(self._request["messages"]),
            }
            self.manager = self._open_stream(self._request)
            self.stream = self.manager.__enter__()
        return self

    def __exit__(self, *args):
        return self.manager.__exit__(*args)

    @property
    def text_stream(self):
        for event in self.stream:
            if getattr(event, "type", None) != "content_block_delta":
                continue
            delta = event.delta
            kind = getattr(delta, "type", None)
            text = getattr(delta, "text", None) if kind == "text_delta" else None
            arguments = getattr(delta, "partial_json", None) if kind == "input_json_delta" else None
            # Thinking/signature deltas show the model is working; they are a
            # liveness signal only and never become answer text.
            thinking = kind in {"thinking_delta", "signature_delta"}
            if (text or arguments or thinking) and self._progress_callback:
                self._progress_callback()
            if text:
                yield text

    def get_final_response(self):
        try:
            message = self.stream.get_final_message()
        except AssertionError as exc:
            raise RuntimeError("Provider stream ended without a completion record") from exc
        if not getattr(message, "stop_reason", None):
            raise RuntimeError("Provider stream ended without a completion record")
        if message.stop_reason not in {"tool_use", "end_turn", "refusal"} and any(
            block.type == "tool_use" for block in message.content
        ):
            raise IncompleteToolCall(_text_only(message.content, message.stop_reason))
        return _anthropic_response(message)


class _OpenAIStreamWrapper:
    def __init__(
        self,
        client,
        model,
        max_tokens,
        messages,
        tools=None,
        temperature=None,
        *,
        request_options=None,
        provider_name: str = "",
    ):
        self._provider_name = provider_name
        self._client, self._model = client, model
        self._max_tokens, self._messages = max_tokens, messages
        self._tools, self._temperature = tools, temperature
        self._stream = None
        self._text = ""
        self._calls: dict[int, dict[str, Any]] = {}
        self._usage: dict[str, Any] = {}
        self._observed_model = ""
        self._finish: str | None = None
        self._stream_exhausted = False
        self._request_options = request_options or {}
        self._reasoning_observed = False
        self._progress_callback: Callable[[], None] | None = None

    def set_progress_callback(self, callback: Callable[[], None]) -> None:
        self._progress_callback = callback

    def __enter__(self):
        kwargs = dict(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=self._messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        if self._tools:
            kwargs["tools"] = self._tools
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        kwargs.update(self._request_options)
        self._stream = self._client.chat.completions.create(
            **_adapt_openai_request(self._provider_name, kwargs)
        )
        return self

    def __exit__(self, *args):
        close = getattr(self._stream, "close", None)
        if close:
            close()
        return False

    @property
    def text_stream(self):
        for chunk in self._stream:
            if getattr(chunk, "error", None) or getattr(chunk, "type", None) == "error":
                raise RuntimeError("Provider stream reported an upstream error")
            if getattr(chunk, "model", None):
                self._observed_model = chunk.model
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                raw = usage.model_dump() if hasattr(usage, "model_dump") else vars(usage).copy()
                self._usage = {"raw": raw}
                for native, normalized in (
                    ("prompt_tokens", "input"),
                    ("completion_tokens", "output"),
                    ("cost", "cost"),
                ):
                    if raw.get(native) is not None:
                        self._usage[normalized] = raw[native]
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            finish = getattr(choice, "finish_reason", None)
            if finish:
                self._finish = {
                    "stop": "end_turn",
                    "length": "max_tokens",
                    "tool_calls": "tool_use",
                }.get(finish, "incomplete")
            delta = choice.delta
            self._reasoning_observed = self._reasoning_observed or _has_reasoning(delta)
            if getattr(delta, "content", None):
                if self._progress_callback:
                    self._progress_callback()
                self._text += delta.content
                yield delta.content
            for part in getattr(delta, "tool_calls", None) or []:
                call = self._calls.setdefault(part.index, {"id": "", "name": "", "arguments": ""})
                call["id"] += getattr(part, "id", None) or ""
                function = getattr(part, "function", None)
                if function:
                    if (
                        getattr(function, "arguments", None) or getattr(function, "name", None)
                    ) and self._progress_callback:
                        self._progress_callback()
                    call["name"] += getattr(function, "name", None) or ""
                    call["arguments"] += getattr(function, "arguments", None) or ""
        self._stream_exhausted = True
        if not self._finish:
            raise RuntimeError("Provider stream ended without a completion record")

    def get_final_response(self):
        if not self._stream_exhausted or not self._finish:
            raise RuntimeError("Provider stream has no completed response")
        if self._calls and self._finish not in {"tool_use", "end_turn"}:
            raise IncompleteToolCall(
                LLMResponse(
                    content=[ContentBlock(type="text", text=self._text)] if self._text else [],
                    stop_reason="max_tokens",
                )
            )
        blocks = [ContentBlock(type="text", text=self._text)] if self._text else []
        for index in sorted(self._calls):
            call = self._calls[index]
            # A malformed tool call must never be executed with silently substituted arguments.
            params = json.loads(call["arguments"] or "{}")
            if not isinstance(params, dict):
                raise ValueError("tool arguments must be an object")
            blocks.append(
                ContentBlock(type="tool_use", id=call["id"], name=call["name"], input=params)
            )
        if (
            self._tools
            and not self._calls
            and self._text
            and self._finish in {"tool_use", "end_turn"}
        ):
            blocks.extend(OpenAICompatibleProvider._parse_xml_tool_calls(self._text))
        if any(b.type == "tool_use" for b in blocks):
            self._finish = "tool_use"
        return LLMResponse(
            blocks,
            self._finish,
            self._observed_model,
            _reasoning_usage(self._usage, self._reasoning_observed),
        )


# ───── Ollama Provider ─────


class OllamaProvider(BaseLLMProvider):
    """Local Ollama API provider."""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434"):
        from openai import OpenAI, Timeout

        # Ollama exposes an OpenAI-compatible API
        self._client = OpenAI(
            api_key="ollama",
            base_url=f"{base_url.rstrip('/')}/v1",
            **_sdk_request_options(Timeout),
        )
        self._base_url = base_url

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        # Reuse OpenAI-compatible logic
        provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
        provider._client = self._client
        provider.provider_name = "ollama"
        return provider.create(model, max_tokens, system, messages, tools, temperature)

    def stream(self, model, max_tokens, system, messages, tools=None, temperature=None):
        provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
        provider._client = self._client
        provider.provider_name = "ollama"
        return provider.stream(model, max_tokens, system, messages, tools, temperature)


# ───── Qwen3 Serverless Provider ─────


class Qwen3ServerlessProvider(BaseLLMProvider):
    """Qwen3-0.6B (Quran/Hadith fine-tune) via a RunPod serverless endpoint.

    Speaks the OpenAI chat-completions protocol (see api/qwen3_client.py).
    Only constructed when QWEN3_ENABLED=1 — create_provider returns None
    otherwise, so the agent keeps its previous provider (the fallback).

    Tool calls are not supported by the fine-tune: ``tools`` are ignored
    (logged) and the model answers in plain text.
    """

    provider_name = "qwen3"
    supports_tools = False

    def __init__(self, config=None) -> None:
        from api.qwen3_client import Qwen3Config

        self.config = config or Qwen3Config.from_env()

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        from api.qwen3_client import Qwen3Unavailable, get_client

        if tools:
            logger.debug("qwen3 provider: ignoring %d tool definitions (unsupported)", len(tools))
        client = get_client(self.config)
        try:
            result = client.generate_sync(
                messages,
                system=system,
                model=model or self.config.model,
                max_tokens=max_tokens,
                temperature=temperature if temperature is not None else 0.7,
            )
        except Qwen3Unavailable as exc:
            raise RuntimeError(f"qwen3 unavailable: [{exc.code}] {exc.detail}") from exc
        return LLMResponse(
            content=[ContentBlock(type="text", text=result.text)],
            stop_reason="end_turn",
            model=result.model,
            usage=result.usage,
        )


# ───── Provider Factory ─────


def ruh_enabled() -> bool:
    return os.getenv("RUH_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def ruh_checkpoint_path() -> str:
    """RUH_MODEL_PATH, else ``ruh_model/checkpoints/latest`` if it holds a model."""
    configured = os.getenv("RUH_MODEL_PATH", "").strip()
    if configured:
        return configured
    candidate = Path(__file__).resolve().parent.parent / "ruh_model" / "checkpoints" / "latest"
    if (candidate / "config.json").is_file() and any(candidate.glob("*.pt")):
        return str(candidate)
    return ""


def configured_provider_name() -> str | None:
    """The operator's ``LLM_PROVIDER``; empty or ``auto`` means auto-detect."""
    name = os.getenv("LLM_PROVIDER", "").strip().lower()
    return None if name in {"", "auto"} else name


def create_provider(
    provider: str | None = None,
    model: str | None = None,
) -> BaseLLMProvider | None:
    """
    Create the appropriate LLM provider based on config.

    Provider selection priority:
    1. Explicit `provider` parameter
    2. Auto-detect from model name
    3. Auto-detect from available API keys

    Returns None if no provider can be configured.
    """
    # Owned mode is an operator-enforced boundary, including model overrides and
    # restored preferences. Teacher support constructs its own isolated adapter.
    from mizan_owned.provider import OwnedProvider, owned_only

    if owned_only() or provider == "mizan-owned" or model == "mizan-owned":
        return cast(BaseLLMProvider, OwnedProvider())
    if provider == "auto":
        provider = None

    # Auto-detect provider from model name, verifying keys exist
    if not provider and model:
        if "/" in model:
            # Namespaced IDs are OpenRouter IDs, including anthropic/claude-*.
            # A native Anthropic key must not silently change this route.
            provider = "openrouter"
        elif model.startswith("claude-"):
            # Claude models: prefer Anthropic if key exists, else route via OpenRouter
            if os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
                provider = "anthropic"
            elif os.getenv("OPENROUTER_API_KEY", ""):
                provider = "openrouter"
        elif model.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")):
            provider = "openai"
        elif model.startswith("ruh"):
            provider = "ruh"
        elif model.startswith(("llama", "mistral", "phi", "gemma", "qwen", "codellama")):
            provider = "ollama"

    # Auto-detect from available API keys
    if not provider:
        if os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
            provider = "anthropic"
        elif os.getenv("OPENROUTER_API_KEY", ""):
            provider = "openrouter"
        elif os.getenv("OPENAI_API_KEY", ""):
            provider = "openai"
        else:
            provider = "anthropic"  # fallback

    # Create the provider
    if provider == "mizan-minimind":
        from providers_minimind import MiniMindRemoteProvider, configured

        if not configured():
            return None
        return cast(
            BaseLLMProvider,
            MiniMindRemoteProvider(
                endpoint_id=os.environ["MINIMIND_ENDPOINT_ID"],
                api_key=os.environ["RUNPOD_API_KEY"],
            ),
        )

    if provider == "mizan-hybrid":
        from mizan_hybrid.provider import create_hybrid_provider_from_env

        return cast(BaseLLMProvider | None, create_hybrid_provider_from_env())

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set")
            return None
        return AnthropicProvider(api_key=api_key)

    elif provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("OPENROUTER_API_KEY not set")
            return None
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": os.getenv(
                    "OPENROUTER_REFERER", "https://github.com/CodeWithJuber/mizan"
                ),
                "X-Title": "MIZAN",
                # Prevent OpenRouter from auto-routing to incompatible models
                "X-Stainless-Retry-Count": "0",
            },
            provider_name="openrouter",
        )

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set")
            return None
        return OpenAICompatibleProvider(api_key=api_key, provider_name="openai")

    elif provider == "ollama":
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        return OllamaProvider(base_url=ollama_url)

    elif provider == "ruh":
        # Remote (RunPod GPU) takes precedence when model is ruh-remote
        if model == "ruh-remote":
            endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "")
            api_key = os.getenv("RUNPOD_API_KEY") or os.getenv("RUNPOD_API_TOKEN") or ""
            if not endpoint_id or not api_key:
                logger.warning("RUNPOD_ENDPOINT_ID or RUNPOD_API_KEY not set")
                return None
            from providers_ruh_remote import RuhRemoteProvider

            return cast(
                BaseLLMProvider | None, RuhRemoteProvider(endpoint_id=endpoint_id, api_key=api_key)
            )
        # Local model: needs RUH_ENABLED and a checkpoint (RUH_MODEL_PATH, or
        # the conventional ruh_model/checkpoints/latest when present).
        if not ruh_enabled():
            logger.warning("Rūḥ model is disabled (set RUH_ENABLED=true)")
            return None
        model_path = ruh_checkpoint_path()
        if not model_path:
            logger.warning("No Rūḥ checkpoint found (set RUH_MODEL_PATH)")
            return None
        from providers_ruh import RuhModelProvider

        device = os.getenv("RUH_DEVICE", "cpu")
        return cast(BaseLLMProvider | None, RuhModelProvider(model_path=model_path, device=device))

    elif provider == "ruh-remote":
        endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "")
        api_key = os.getenv("RUNPOD_API_KEY") or os.getenv("RUNPOD_API_TOKEN") or ""
        if not endpoint_id or not api_key:
            logger.warning("RUNPOD_ENDPOINT_ID or RUNPOD_API_KEY not set")
            return None
        from providers_ruh_remote import RuhRemoteProvider

        return cast(
            BaseLLMProvider | None, RuhRemoteProvider(endpoint_id=endpoint_id, api_key=api_key)
        )

    elif provider == "qwen3":
        from api.qwen3_client import Qwen3Config

        cfg = Qwen3Config.from_env()
        if not cfg.enabled:
            logger.warning("QWEN3_ENABLED is not set — qwen3 provider unavailable")
            return None
        if not cfg.configured:
            logger.warning("QWEN3_ENDPOINT_URL / QWEN3_API_KEY not set")
            return None
        return Qwen3ServerlessProvider(cfg)

    else:
        logger.error(f"Unknown provider: {provider}")
        return None


def normalize_model_for_provider(model: str, provider_name: str) -> str:
    """Translate model IDs between provider formats when needed."""
    # Anthropic → OpenRouter mapping
    if provider_name == "mizan-owned":
        return "mizan-owned"

    _anthropic_to_openrouter = {
        "claude-sonnet-4-20250514": "anthropic/claude-sonnet-4",
        "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    }
    if provider_name == "openrouter" and "/" not in model:
        if model in _anthropic_to_openrouter:
            return _anthropic_to_openrouter[model]
        # OpenRouter writes Claude versions with a dot: claude-opus-5-5 →
        # anthropic/claude-opus-5.5 (verified against its catalog 2026-10-26).
        match = re.fullmatch(r"claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:-(\d))?", model)
        if match:
            family, major, minor = match.groups()
            return f"anthropic/claude-{family}-{major}{'.' + minor if minor else ''}"
    return model


def get_default_model(provider_name: str) -> str:
    """Get the default model for a provider."""
    if provider_name == "mizan-owned":
        return "mizan-owned"
    if provider_name == "mizan-minimind":
        from providers_minimind import MODEL_ID

        return str(MODEL_ID)
    if provider_name == "mizan-hybrid":
        from mizan_hybrid.config import HybridConfig

        return str(HybridConfig.from_env().base_model)

    env_model = os.getenv("DEFAULT_MODEL", "")
    if env_model:
        return normalize_model_for_provider(env_model, provider_name)

    return PROVIDER_DEFAULT_MODELS.get(provider_name, DEFAULT_CLAUDE_MODEL)


# Current defaults, checked against the Anthropic model table and the
# OpenRouter/Ollama catalogs on 2026-10-26. DEFAULT_MODEL overrides them.
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
PROVIDER_DEFAULT_MODELS = {
    "anthropic": DEFAULT_CLAUDE_MODEL,
    "openrouter": "anthropic/claude-opus-5.5",
    "openai": "gpt-6.1-sol",
    "ollama": "qwen3.8",
    "ruh": "ruh-local",
    "qwen3": os.getenv("QWEN3_MODEL", "qwen3-0.6b-quran"),
    "mizan-hybrid": os.getenv("MIZAN_BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507"),
}


# ───── Provider Discovery & Health ─────

# Well-known models per provider for quick selection
PROVIDER_MODELS = {
    "mizan-owned": [
        {"id": "mizan-owned", "name": "Mizan Own Architecture", "context": 8192, "vision": False}
    ],
    "anthropic": [
        {
            "id": "claude-opus-5-5",
            "name": "Claude Opus 5.5",
            "context": 1_000_000,
            "max_output": 128_000,
            "vision": True,
        },
        {
            "id": "claude-sonnet-5-5",
            "name": "Claude Sonnet 5.5",
            "context": 1_000_000,
            "max_output": 128_000,
            "vision": True,
        },
        {
            "id": "claude-haiku-5-5",
            "name": "Claude Haiku 5.5",
            "context": 1_000_000,
            "max_output": 128_000,
            "vision": True,
        },
    ],
    "openai": [
        {
            "id": "gpt-6.1-sol",
            "name": "GPT-6.1 Sol",
            "context": 1_050_000,
            "max_output": 128_000,
            "vision": True,
        },
        {
            "id": "gpt-6-luna",
            "name": "GPT-6 Luna",
            "context": 1_050_000,
            "max_output": 128_000,
            "vision": True,
        },
    ],
    "openrouter": [],  # Fetched dynamically
    "ollama": [],  # Fetched dynamically
    "ruh": [
        {"id": "ruh-local", "name": "Rūḥ Model (Local)", "context": 2048, "vision": False},
        {"id": "ruh-remote", "name": "Rūḥ Model (RunPod GPU)", "context": 2048, "vision": False},
    ],
    "qwen3": [
        {
            "id": os.getenv("QWEN3_MODEL", "qwen3-0.6b-quran"),
            "name": "Qwen3-0.6B (Quran/Hadith, RunPod Serverless)",
            "context": 8192,
            "vision": False,
        },
    ],
    "mizan-minimind": [
        {
            "id": "Zubairshaikh/mizan-full-sft",
            "name": "Mizan MiniMind SFT (Text)",
            "context": 2048,
            "vision": False,
            "tools": False,
        },
    ],
    "mizan-hybrid": [
        {
            "id": os.getenv("MIZAN_BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507"),
            "name": "Mizan Hybrid (Qwen3-4B + own NLP + gates; research)",
            "context": 32768,
            "vision": False,
        },
    ],
}

# ───── Model limits (context window, output cap) ─────
#
# Live values come from the Anthropic Models API (max_input_tokens/max_tokens)
# and the OpenRouter catalog (context_length/max_completion_tokens); the
# static table above and family rules are the offline fallback.

_MODEL_LIMITS: dict[str, tuple[int, int]] = {}


def _limits_key(model: str) -> str:
    return (model or "").strip().lower()


def model_limits(model: str) -> tuple[int, int]:
    """Return ``(context_window_tokens, max_output_tokens)`` for a model."""
    key = _limits_key(model)
    if key in _MODEL_LIMITS:
        return _MODEL_LIMITS[key]
    for entries in PROVIDER_MODELS.values():
        for entry in cast(list[dict[str, Any]], entries):
            if _limits_key(str(entry["id"])) == key:
                context = int(entry.get("context") or 8192)
                return context, int(entry.get("max_output") or min(8192, context // 4))
    version = claude_version(model)
    if version is not None:
        family, number = version
        if family in {"fable", "mythos"} or number >= 4.6:
            return 1_000_000, 128_000
        if number >= 4.5:
            return 200_000, 64_000
        return 200_000, 32_000
    return 32_768, 8_192


def effective_limits(provider: Any, model: str) -> tuple[int, int]:
    """``(context, max_output)`` for one request on ``provider``.

    A provider that serves a fixed window declares it (for example a
    2,048-token worker with a 256-token output cap); that declaration wins
    over the model table, whose fallback for unknown models is 32K.
    """
    context, max_output = model_limits(model)
    declared_context = getattr(provider, "context_window", None)
    if type(declared_context) is int and declared_context > 0:
        context = declared_context
    declared_output = getattr(provider, "max_output_tokens", None)
    if type(declared_output) is int and declared_output > 0:
        max_output = declared_output
    return context, max(1, min(max_output, context))


_RETRYABLE_STATUS = {429, 500, 502, 503, 529}


def provider_retry_delay(exc: BaseException, attempt: int) -> float | None:
    """Seconds to wait before re-sending a request the provider rejected.

    Only explicit HTTP error responses qualify (rate limit, overload, upstream
    error): the provider answered with an error, so nothing was generated or
    billed. Timeouts and dropped connections never qualify, because an
    accepted request may still be running upstream.
    """
    status = getattr(exc, "status_code", None)
    if type(status) is not int or status not in _RETRYABLE_STATUS:
        return None
    if status == 429:
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        try:
            after = float(headers.get("retry-after", "") or 0)
        except (TypeError, ValueError, AttributeError):
            after = 0.0
        return min(max(after, 2.0 * (attempt + 1)), 20.0)
    return float(min(1.5 * 2.0**attempt, 8.0))


def record_model_limits(model: str, context: Any, max_output: Any) -> None:
    try:
        context_value, output_value = int(context or 0), int(max_output or 0)
    except (TypeError, ValueError):
        return
    if context_value > 0:
        output_value = output_value if output_value > 0 else min(8192, context_value // 4)
        _MODEL_LIMITS[_limits_key(model)] = (context_value, min(output_value, context_value))


async def refresh_model_limits() -> int:
    """Refresh live model limits; failures keep the previous/static values."""
    import httpx

    refreshed = 0
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key.startswith("sk-ant-"):
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=anthropic_key, max_retries=0, timeout=15)
            async for info in client.models.list(limit=100):
                record_model_limits(
                    info.id,
                    getattr(info, "max_input_tokens", None),
                    getattr(info, "max_tokens", None),
                )
                refreshed += 1
            await client.close()
        except Exception as exc:
            logger.info("Anthropic model limits unavailable: %s", exc)
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.get("https://openrouter.ai/api/v1/models")
            if response.status_code == 200:
                for entry in response.json().get("data", []):
                    top = entry.get("top_provider") or {}
                    model_id = str(entry.get("id", ""))
                    record_model_limits(
                        model_id,
                        entry.get("context_length"),
                        top.get("max_completion_tokens"),
                    )
                    if model_id:
                        _OPENROUTER_CATALOG[model_id] = {
                            "free": model_id.endswith(":free"),
                            "tools": "tools" in (entry.get("supported_parameters") or []),
                            "context": int(entry.get("context_length") or 0),
                        }
                    refreshed += 1
    except Exception as exc:
        logger.info("OpenRouter model limits unavailable: %s", exc)
    return refreshed


# In-memory active state — updated by switch_provider, read by get_provider_status.
# Falls back to env vars when empty (before any switch).
_active_state: dict[str, str] = {"provider": "", "model": ""}


def set_active_state(provider: str, model: str) -> None:
    """Update in-memory active provider/model after a switch."""
    _active_state["provider"] = provider
    _active_state["model"] = model


def get_provider_status() -> dict:
    """
    Get status of all configured providers.
    Returns which providers have API keys set and are available.
    """
    providers: list[dict[str, Any]] = []

    # Anthropic
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    providers.append(
        {
            "name": "anthropic",
            "display": "Anthropic (Claude)",
            "configured": bool(anthropic_key and anthropic_key != "sk-ant-your-key-here"),
            "models": PROVIDER_MODELS["anthropic"],
            "default_model": PROVIDER_DEFAULT_MODELS["anthropic"],
        }
    )

    # OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    providers.append(
        {
            "name": "openrouter",
            "display": "OpenRouter (300+ models)",
            "configured": bool(openrouter_key),
            "models": PROVIDER_MODELS["openrouter"],
            "default_model": PROVIDER_DEFAULT_MODELS["openrouter"],
        }
    )

    # OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "")
    providers.append(
        {
            "name": "openai",
            "display": "OpenAI",
            "configured": bool(openai_key and openai_key != "sk-your-openai-key-here"),
            "models": PROVIDER_MODELS["openai"],
            "default_model": PROVIDER_DEFAULT_MODELS["openai"],
        }
    )

    # Ollama
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    providers.append(
        {
            "name": "ollama",
            "display": "Ollama (Local)",
            "configured": True,  # Always "configured" — just may not be running
            "base_url": ollama_url,
            "models": PROVIDER_MODELS["ollama"],
            "default_model": PROVIDER_DEFAULT_MODELS["ollama"],
        }
    )

    # Ruh Model (local)
    ruh_enabled = os.getenv("RUH_ENABLED", "").lower() in ("true", "1", "yes")
    ruh_model_path = os.getenv("RUH_MODEL_PATH", "")
    providers.append(
        {
            "name": "ruh",
            "display": "Rūḥ Model (Local)",
            "configured": bool(ruh_enabled and ruh_model_path),
            "models": PROVIDER_MODELS["ruh"],
            "default_model": "ruh-local",
        }
    )

    # Qwen3 serverless (RunPod) — feature-flagged via QWEN3_ENABLED
    qwen3_on = os.getenv("QWEN3_ENABLED", "").lower() in ("true", "1", "yes")
    providers.append(
        {
            "name": "qwen3",
            "display": "Qwen3-0.6B Serverless (Quran/Hadith)",
            "configured": bool(
                qwen3_on and os.getenv("QWEN3_ENDPOINT_URL", "") and os.getenv("QWEN3_API_KEY", "")
            ),
            "models": PROVIDER_MODELS["qwen3"],
            "default_model": os.getenv("QWEN3_MODEL", "qwen3-0.6b-quran"),
        }
    )

    from providers_minimind import configured as minimind_configured

    providers.append(
        {
            "name": "mizan-minimind",
            "display": "Mizan MiniMind SFT (RunPod)",
            "configured": minimind_configured(),
            "models": PROVIDER_MODELS["mizan-minimind"],
            "default_model": get_default_model("mizan-minimind"),
        }
    )

    # Mizan hybrid: pinned research base + bounded own-NLP + deterministic gates.
    from mizan_hybrid.config import HybridConfig

    hybrid_config = HybridConfig.from_env()
    providers.append(
        {
            "name": "mizan-hybrid",
            "display": "Mizan Hybrid (Research)",
            "configured": hybrid_config.configured,
            "models": [
                {
                    "id": hybrid_config.base_model,
                    "name": "Mizan Hybrid (Research)",
                    "context": hybrid_config.context_window,
                    "vision": False,
                    "tools": hybrid_config.base_provider != "mizan-minimind",
                }
            ],
            "default_model": hybrid_config.base_model,
            "base_revision": hybrid_config.base_revision,
            "semantic_or_religious_certification": False,
        }
    )

    from mizan_owned.provider import health as owned_health
    from mizan_owned.provider import owned_only

    providers.append(
        {
            "name": "mizan-owned",
            "display": "Mizan Own Architecture",
            "configured": True,
            "models": PROVIDER_MODELS["mizan-owned"],
            "default_model": "mizan-owned",
            **owned_health(),
        }
    )

    # Determine active provider — prefer in-memory state from switch_provider,
    # then env var, then auto-detect from configured providers.
    active = _active_state["provider"] or configured_provider_name() or ""
    if not active:
        for p in providers:
            if p["configured"] and p["name"] != "ollama":
                active = p["name"]
                break

    if owned_only():
        active = "mizan-owned"

    default_model = (
        get_default_model(active)
        if active == "mizan-owned"
        or (active in {"mizan-hybrid", "mizan-minimind"} and not _active_state["model"])
        else _active_state["model"] or os.getenv("DEFAULT_MODEL", "") or get_default_model(active)
    )

    return {
        "active": active,
        "default_model": default_model,
        "providers": providers,
    }


async def fetch_openrouter_models(
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    free_only: bool = False,
) -> dict:
    """
    Fetch available models from OpenRouter's public API.
    Returns paginated results with search/filter support.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            if resp.status_code != 200:
                return {"models": [], "total": 0, "offset": offset, "limit": limit}

            data = resp.json()
            models_raw = data.get("data", [])

            models = []
            for m in models_raw:
                prompt_price = m.get("pricing", {}).get("prompt", "0")
                is_free = float(prompt_price or "0") == 0.0
                models.append(
                    {
                        "id": m.get("id", ""),
                        "name": m.get("name", m.get("id", "")),
                        "context": m.get("context_length", 0),
                        "pricing": {
                            "prompt": prompt_price,
                            "completion": m.get("pricing", {}).get("completion", "0"),
                        },
                        "free": is_free,
                    }
                )

            # Apply filters
            if search:
                search_lower = search.lower()
                models = [
                    m
                    for m in models
                    if search_lower in m["id"].lower() or search_lower in m["name"].lower()
                ]
            if free_only:
                models = [m for m in models if m["free"]]

            total = len(models)
            paginated = models[offset : offset + limit]

            return {
                "models": paginated,
                "total": total,
                "offset": offset,
                "limit": limit,
            }
    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter models: {e}")
        return {"models": [], "total": 0, "offset": offset, "limit": limit}


async def fetch_ollama_models() -> list[dict]:
    """Fetch locally available Ollama models."""
    import httpx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            if resp.status_code != 200:
                return []

            data = resp.json()
            models = []
            for m in data.get("models", []):
                models.append(
                    {
                        "id": m.get("name", ""),
                        "name": m.get("name", ""),
                        "size": m.get("size", 0),
                        "context": 0,
                    }
                )
            return models
    except Exception:
        return []


async def check_provider_health(provider_name: str) -> dict:
    """
    Quick health check for a provider — verifies the API key works
    by making a minimal request.
    """
    import httpx

    if provider_name == "mizan-owned":
        from mizan_owned.provider import health

        return {**health(), "healthy": True}

    if provider_name == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return {"provider": "anthropic", "healthy": False, "error": "No API key"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2026-10-21",
                    },
                )
                return {"provider": "anthropic", "healthy": resp.status_code == 200}
        except Exception as e:
            return {"provider": "anthropic", "healthy": False, "error": str(e)}

    elif provider_name == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return {"provider": "openrouter", "healthy": False, "error": "No API key"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                data = resp.json() if resp.status_code == 200 else {}
                return {
                    "provider": "openrouter",
                    "healthy": resp.status_code == 200,
                    "usage": data.get("data", {}).get("usage", 0),
                    "limit": data.get("data", {}).get("limit", None),
                }
        except Exception as e:
            return {"provider": "openrouter", "healthy": False, "error": str(e)}

    elif provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return {"provider": "openai", "healthy": False, "error": "No API key"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                return {"provider": "openai", "healthy": resp.status_code == 200}
        except Exception as e:
            return {"provider": "openai", "healthy": False, "error": str(e)}

    elif provider_name == "ollama":
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{ollama_url}/api/tags")
                return {
                    "provider": "ollama",
                    "healthy": resp.status_code == 200,
                    "models": len(resp.json().get("models", [])) if resp.status_code == 200 else 0,
                }
        except Exception:
            return {"provider": "ollama", "healthy": False, "error": "Ollama not running"}

    elif provider_name == "qwen3":
        from api.qwen3_client import Qwen3Config

        cfg = Qwen3Config.from_env()
        if not cfg.enabled or not cfg.configured:
            return {"provider": "qwen3", "healthy": False, "error": "Qwen3 not enabled/configured"}
        return {
            "provider": "qwen3",
            "healthy": True,
            "endpoint_host": cfg.endpoint_host(),
            "model": cfg.model,
            "note": "config check only; use /v1/qwen3/health?probe=true for a live probe",
        }

    elif provider_name == "mizan-minimind":
        from providers_minimind import configured

        # Do not wake a paid GPU for a settings health check.
        return {
            "provider": provider_name,
            "healthy": configured(),
            "probe": "configuration_only",
            "model": get_default_model(provider_name),
            "note": "No inference job submitted; worker liveness is not verified",
        }

    elif provider_name == "mizan-hybrid":
        from mizan_hybrid.config import HybridConfig

        cfg = HybridConfig.from_env()
        if not cfg.configured:
            return {
                "provider": "mizan-hybrid",
                "healthy": False,
                "error": "Mizan hybrid not enabled/configured",
            }
        if cfg.base_provider != "openai-compatible":
            result = await check_provider_health(cfg.base_provider)
            return {**result, "provider": "mizan-hybrid", "base_provider": cfg.base_provider}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(
                    f"{cfg.base_url}/models",
                    headers={"Authorization": f"Bearer {cfg.base_api_key}"},
                )
            model_ids = set()
            if resp.status_code == 200:
                model_ids = {item.get("id") for item in resp.json().get("data", [])}
            healthy = resp.status_code == 200 and cfg.base_model in model_ids
            return {
                "provider": "mizan-hybrid",
                "healthy": healthy,
                "model": cfg.base_model,
                "base_revision": cfg.base_revision,
                "semantic_or_religious_certification": False,
                **({} if healthy else {"error": "Expected pinned model is not available"}),
            }
        except Exception:
            logger.warning("Mizan hybrid health probe failed", exc_info=True)
            return {
                "provider": "mizan-hybrid",
                "healthy": False,
                "error": "Mizan hybrid endpoint is unavailable",
            }

    return {"provider": provider_name, "healthy": False, "error": "Unknown provider"}
