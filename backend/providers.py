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

    Agent-level recovery is separate, so SDK retries are disabled by default
    instead of silently multiplying the agent's own attempts.
    """
    try:
        seconds = float(os.getenv("MIZAN_LLM_TIMEOUT_SECONDS", "60"))
        if not math.isfinite(seconds):
            raise ValueError("non-finite timeout")
    except ValueError:
        logger.warning("Invalid MIZAN_LLM_TIMEOUT_SECONDS; using 60 seconds")
        seconds = 60.0
    seconds = max(1.0, min(seconds, 180.0))
    try:
        retries = int(os.getenv("MIZAN_LLM_MAX_RETRIES", "0"))
    except ValueError:
        logger.warning("Invalid MIZAN_LLM_MAX_RETRIES; disabling SDK retries")
        retries = 0
    return {
        "timeout": timeout_type(seconds, connect=min(5.0, seconds)),
        "max_retries": max(0, min(retries, 2)),
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


class AnthropicProvider(BaseLLMProvider):
    """Native Anthropic Claude API with tool_use support."""

    provider_name = "anthropic"

    def __init__(self, api_key: str):
        import anthropic

        self._client = anthropic.Anthropic(
            api_key=api_key, **_sdk_request_options(anthropic.Timeout)
        )

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self._client.messages.create(**kwargs)

        blocks = []
        for block in response.content:
            if block.type == "text":
                blocks.append(ContentBlock(type="text", text=block.text))
            elif block.type == "tool_use":
                blocks.append(
                    ContentBlock(
                        type="tool_use",
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        return LLMResponse(
            content=blocks,
            stop_reason=response.stop_reason,
            model=response.model,
            usage={"input": response.usage.input_tokens, "output": response.usage.output_tokens},
        )

    def stream(self, model, max_tokens, system, messages, tools=None, temperature=None):
        kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        return _AnthropicStreamWrapper(self._client.messages.stream(**kwargs))


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
        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        blocks = []

        # Text content
        if message.content:
            blocks.append(ContentBlock(type="text", text=message.content))

        # Tool calls (structured API)
        if message.tool_calls:
            if choice.finish_reason not in {"tool_calls", "stop"}:
                raise ValueError("Provider returned an incomplete tool call")
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
    def __init__(self, manager):
        self.manager = manager
        self.stream = None

    def __enter__(self):
        self.stream = self.manager.__enter__()
        return self

    def __exit__(self, *args):
        return self.manager.__exit__(*args)

    @property
    def text_stream(self):
        return self.stream.text_stream

    def get_final_response(self):
        try:
            message = self.stream.get_final_message()
        except AssertionError as exc:
            raise RuntimeError("Provider stream ended without a completion record") from exc
        if not getattr(message, "stop_reason", None):
            raise RuntimeError("Provider stream ended without a completion record")
        blocks = []
        for block in message.content:
            if block.type == "text":
                blocks.append(ContentBlock(type="text", text=block.text))
            elif block.type == "tool_use":
                if message.stop_reason not in {"tool_use", "end_turn"}:
                    raise ValueError("Provider returned an incomplete tool call")
                blocks.append(
                    ContentBlock(type="tool_use", id=block.id, name=block.name, input=block.input)
                )
        return LLMResponse(
            blocks,
            message.stop_reason,
            message.model,
            {"input": message.usage.input_tokens, "output": message.usage.output_tokens},
        )


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
    ):
        self._client, self._model = client, model
        self._max_tokens, self._messages = max_tokens, messages
        self._tools, self._temperature = tools, temperature
        self._stream = None
        self._text = ""
        self._calls = {}
        self._usage = {}
        self._observed_model = ""
        self._finish: str | None = None
        self._stream_exhausted = False
        self._request_options = request_options or {}
        self._reasoning_observed = False

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
        self._stream = self._client.chat.completions.create(**kwargs)
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
                self._text += delta.content
                yield delta.content
            for part in getattr(delta, "tool_calls", None) or []:
                call = self._calls.setdefault(part.index, {"id": "", "name": "", "arguments": ""})
                call["id"] += getattr(part, "id", None) or ""
                function = getattr(part, "function", None)
                if function:
                    call["name"] += getattr(function, "name", None) or ""
                    call["arguments"] += getattr(function, "arguments", None) or ""
        self._stream_exhausted = True
        if not self._finish:
            raise RuntimeError("Provider stream ended without a completion record")

    def get_final_response(self):
        if not self._stream_exhausted or not self._finish:
            raise RuntimeError("Provider stream has no completed response")
        if self._calls and self._finish not in {"tool_use", "end_turn"}:
            raise ValueError("Provider returned an incomplete tool call")
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
        elif model.startswith(("gpt-", "o1", "o3", "chatgpt")):
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
        # Local model
        model_path = os.getenv("RUH_MODEL_PATH", "")
        if not model_path:
            logger.warning("RUH_MODEL_PATH not set")
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
        "claude-opus-4-6": "anthropic/claude-opus-4.6",
        "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
        "claude-sonnet-4-20250514": "anthropic/claude-sonnet-4",
        "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    }
    if provider_name == "openrouter" and "/" not in model:
        return _anthropic_to_openrouter.get(model, model)
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

    defaults = {
        "anthropic": "claude-sonnet-4-20250514",
        "openrouter": "anthropic/claude-sonnet-4",
        "openai": "gpt-4o",
        "ollama": "llama3.2",
        "ruh": "ruh-local",
        "qwen3": os.getenv("QWEN3_MODEL", "qwen3-0.6b-quran"),
        "mizan-hybrid": os.getenv("MIZAN_BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507"),
    }
    return defaults.get(provider_name, "claude-sonnet-4-20250514")


# ───── Provider Discovery & Health ─────

# Well-known models per provider for quick selection
PROVIDER_MODELS = {
    "mizan-owned": [
        {"id": "mizan-owned", "name": "Mizan Own Architecture", "context": 8192, "vision": False}
    ],
    "anthropic": [
        {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "context": 200000, "vision": True},
        {
            "id": "claude-sonnet-4-20250514",
            "name": "Claude Sonnet 4",
            "context": 200000,
            "vision": True,
        },
        {
            "id": "claude-haiku-4-5-20251001",
            "name": "Claude Haiku 4.5",
            "context": 200000,
            "vision": True,
        },
    ],
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o", "context": 128000, "vision": True},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context": 128000, "vision": True},
        {"id": "o3-mini", "name": "o3 Mini", "context": 200000, "vision": False},
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
            "default_model": "claude-sonnet-4-20250514",
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
            "default_model": "anthropic/claude-sonnet-4",
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
            "default_model": "gpt-4o",
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
            "default_model": "llama3.2",
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
    active = _active_state["provider"] or os.getenv("LLM_PROVIDER", "")
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
                        "anthropic-version": "2023-06-01",
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
