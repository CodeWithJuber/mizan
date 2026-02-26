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
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mizan.providers")


# ───── Normalized Response Types ─────

@dataclass
class ContentBlock:
    """A single block in an LLM response (text or tool_use)."""
    type: str  # "text" or "tool_use"
    text: str = ""
    id: str = ""           # tool_use block id
    name: str = ""         # tool name
    input: Dict = field(default_factory=dict)  # tool input params


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    content: List[ContentBlock]
    stop_reason: str = "end_turn"  # "end_turn" or "tool_use"
    model: str = ""
    usage: Dict = field(default_factory=dict)


# ───── Provider Interface ─────

class BaseLLMProvider:
    """Base class for all LLM providers."""

    provider_name: str = "base"

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[Dict],
        tools: List[Dict] = None,
    ) -> LLMResponse:
        raise NotImplementedError

    def stream(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[Dict],
    ):
        """Streaming interface for chat (no tools). Returns a context manager."""
        raise NotImplementedError


# ───── Anthropic Provider ─────

class AnthropicProvider(BaseLLMProvider):
    """Native Anthropic Claude API with tool_use support."""

    provider_name = "anthropic"

    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def create(self, model, max_tokens, system, messages, tools=None):
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        blocks = []
        for block in response.content:
            if block.type == "text":
                blocks.append(ContentBlock(type="text", text=block.text))
            elif block.type == "tool_use":
                blocks.append(ContentBlock(
                    type="tool_use",
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))

        return LLMResponse(
            content=blocks,
            stop_reason=response.stop_reason,
            model=response.model,
            usage={"input": response.usage.input_tokens, "output": response.usage.output_tokens},
        )

    def stream(self, model, max_tokens, system, messages):
        return self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )


# ───── OpenAI-Compatible Provider (OpenAI + OpenRouter) ─────

class OpenAICompatibleProvider(BaseLLMProvider):
    """
    OpenAI-compatible API provider.
    Works with OpenAI, OpenRouter, and any OpenAI-compatible endpoint.
    """

    def __init__(self, api_key: str, base_url: str = None,
                 default_headers: Dict = None, provider_name: str = "openai"):
        from openai import OpenAI
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if default_headers:
            kwargs["default_headers"] = default_headers
        self._client = OpenAI(**kwargs)
        self.provider_name = provider_name

    def _convert_tools_to_openai(self, tools: List[Dict]) -> List[Dict]:
        """Convert Anthropic tool schemas to OpenAI function calling format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return openai_tools

    def _convert_messages_to_openai(self, system: str, messages: List[Dict]) -> List[Dict]:
        """Convert Anthropic-style messages to OpenAI format."""
        openai_messages = [{"role": "system", "content": system}]

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Handle Anthropic-style content blocks
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_result":
                            openai_messages.append({
                                "role": "tool",
                                "tool_call_id": block.get("tool_use_id", ""),
                                "content": block.get("content", ""),
                            })
                        elif block.get("type") == "text":
                            openai_messages.append({"role": role, "content": block.get("text", "")})
                    else:
                        # It's a content block object from Anthropic
                        if hasattr(block, "type"):
                            if block.type == "text":
                                openai_messages.append({"role": role, "content": block.text})
                            elif block.type == "tool_use":
                                openai_messages.append({
                                    "role": "assistant",
                                    "tool_calls": [{
                                        "id": block.id,
                                        "type": "function",
                                        "function": {
                                            "name": block.name,
                                            "arguments": json.dumps(block.input),
                                        },
                                    }],
                                })
            else:
                openai_messages.append({"role": role, "content": str(content)})

        return openai_messages

    def create(self, model, max_tokens, system, messages, tools=None):
        openai_messages = self._convert_messages_to_openai(system, messages)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": openai_messages,
        }
        if tools:
            kwargs["tools"] = self._convert_tools_to_openai(tools)

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        blocks = []

        # Text content
        if message.content:
            blocks.append(ContentBlock(type="text", text=message.content))

        # Tool calls
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                blocks.append(ContentBlock(
                    type="tool_use",
                    id=tc.id,
                    name=tc.function.name,
                    input=args,
                ))

        # Map finish_reason
        stop_reason = "end_turn"
        if choice.finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif choice.finish_reason == "stop":
            stop_reason = "end_turn"

        return LLMResponse(
            content=blocks,
            stop_reason=stop_reason,
            model=response.model,
            usage={
                "input": response.usage.prompt_tokens if response.usage else 0,
                "output": response.usage.completion_tokens if response.usage else 0,
            },
        )

    def stream(self, model, max_tokens, system, messages):
        """Return an OpenAI streaming wrapper that mimics Anthropic's interface."""
        openai_messages = self._convert_messages_to_openai(system, messages)
        return _OpenAIStreamWrapper(self._client, model, max_tokens, openai_messages)


class _OpenAIStreamWrapper:
    """Wraps OpenAI streaming to provide a text_stream interface like Anthropic."""

    def __init__(self, client, model, max_tokens, messages):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._messages = messages
        self._stream = None

    def __enter__(self):
        self._stream = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=self._messages,
            stream=True,
        )
        return self

    def __exit__(self, *args):
        pass

    @property
    def text_stream(self):
        for chunk in self._stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ───── Ollama Provider ─────

class OllamaProvider(BaseLLMProvider):
    """Local Ollama API provider."""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434"):
        from openai import OpenAI
        # Ollama exposes an OpenAI-compatible API
        self._client = OpenAI(
            api_key="ollama",
            base_url=f"{base_url.rstrip('/')}/v1",
        )
        self._base_url = base_url

    def create(self, model, max_tokens, system, messages, tools=None):
        # Reuse OpenAI-compatible logic
        provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
        provider._client = self._client
        provider.provider_name = "ollama"
        return provider.create(model, max_tokens, system, messages, tools)

    def stream(self, model, max_tokens, system, messages):
        openai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            if isinstance(msg["content"], str):
                openai_messages.append({"role": msg["role"], "content": msg["content"]})
        return _OpenAIStreamWrapper(self._client, model, max_tokens, openai_messages)


# ───── Provider Factory ─────

def create_provider(
    provider: str = None,
    model: str = None,
) -> Optional[BaseLLMProvider]:
    """
    Create the appropriate LLM provider based on config.

    Provider selection priority:
    1. Explicit `provider` parameter
    2. Auto-detect from model name
    3. Auto-detect from available API keys

    Returns None if no provider can be configured.
    """
    # Auto-detect provider from model name
    if not provider and model:
        if model.startswith(("claude-", "anthropic/")):
            provider = "anthropic"
        elif model.startswith(("gpt-", "o1", "o3", "chatgpt")):
            provider = "openai"
        elif "/" in model:
            # Slash in model name like "google/gemini-2.0-flash" → OpenRouter
            provider = "openrouter"
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
                "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://github.com/CodeWithJuber/mizan"),
                "X-Title": "MIZAN",
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

    else:
        logger.error(f"Unknown provider: {provider}")
        return None


def get_default_model(provider_name: str) -> str:
    """Get the default model for a provider."""
    env_model = os.getenv("DEFAULT_MODEL", "")
    if env_model:
        return env_model

    defaults = {
        "anthropic": "claude-sonnet-4-20250514",
        "openrouter": "anthropic/claude-sonnet-4",
        "openai": "gpt-4o",
        "ollama": "llama3.2",
    }
    return defaults.get(provider_name, "claude-sonnet-4-20250514")


# ───── Provider Discovery & Health ─────

# Well-known models per provider for quick selection
PROVIDER_MODELS = {
    "anthropic": [
        {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "context": 200000, "vision": True},
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "context": 200000, "vision": True},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", "context": 200000, "vision": True},
    ],
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o", "context": 128000, "vision": True},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context": 128000, "vision": True},
        {"id": "o3-mini", "name": "o3 Mini", "context": 200000, "vision": False},
    ],
    "openrouter": [],  # Fetched dynamically
    "ollama": [],  # Fetched dynamically
}


def get_provider_status() -> Dict:
    """
    Get status of all configured providers.
    Returns which providers have API keys set and are available.
    """
    providers = []

    # Anthropic
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    providers.append({
        "name": "anthropic",
        "display": "Anthropic (Claude)",
        "configured": bool(anthropic_key and anthropic_key != "sk-ant-your-key-here"),
        "models": PROVIDER_MODELS["anthropic"],
        "default_model": "claude-sonnet-4-20250514",
    })

    # OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    providers.append({
        "name": "openrouter",
        "display": "OpenRouter (300+ models)",
        "configured": bool(openrouter_key),
        "models": PROVIDER_MODELS["openrouter"],
        "default_model": "anthropic/claude-sonnet-4",
    })

    # OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "")
    providers.append({
        "name": "openai",
        "display": "OpenAI",
        "configured": bool(openai_key and openai_key != "sk-your-openai-key-here"),
        "models": PROVIDER_MODELS["openai"],
        "default_model": "gpt-4o",
    })

    # Ollama
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    providers.append({
        "name": "ollama",
        "display": "Ollama (Local)",
        "configured": True,  # Always "configured" — just may not be running
        "base_url": ollama_url,
        "models": PROVIDER_MODELS["ollama"],
        "default_model": "llama3.2",
    })

    # Determine active provider
    active = os.getenv("LLM_PROVIDER", "")
    if not active:
        for p in providers:
            if p["configured"] and p["name"] != "ollama":
                active = p["name"]
                break

    return {
        "active": active,
        "default_model": os.getenv("DEFAULT_MODEL", get_default_model(active)),
        "providers": providers,
    }


async def fetch_openrouter_models(limit: int = 50) -> List[Dict]:
    """
    Fetch available models from OpenRouter's public API.
    Returns a curated list of popular models.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            if resp.status_code != 200:
                return []

            data = resp.json()
            models_raw = data.get("data", [])

            # Sort by popularity and return curated list
            models = []
            for m in models_raw[:limit]:
                models.append({
                    "id": m.get("id", ""),
                    "name": m.get("name", m.get("id", "")),
                    "context": m.get("context_length", 0),
                    "pricing": {
                        "prompt": m.get("pricing", {}).get("prompt", "0"),
                        "completion": m.get("pricing", {}).get("completion", "0"),
                    },
                })

            return models
    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter models: {e}")
        return []


async def fetch_ollama_models() -> List[Dict]:
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
                models.append({
                    "id": m.get("name", ""),
                    "name": m.get("name", ""),
                    "size": m.get("size", 0),
                    "context": 0,
                })
            return models
    except Exception:
        return []


async def check_provider_health(provider_name: str) -> Dict:
    """
    Quick health check for a provider — verifies the API key works
    by making a minimal request.
    """
    import httpx

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

    return {"provider": provider_name, "healthy": False, "error": "Unknown provider"}
