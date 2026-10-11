"""Qwen3 serverless client for MIZAN.

Talks to the fine-tuned Qwen3-0.6B (Quran/Hadith) model hosted on a RunPod
serverless endpoint that speaks the OpenAI chat-completions protocol::

    POST {QWEN3_ENDPOINT_URL}/v1/chat/completions
    Authorization: Bearer {QWEN3_API_KEY}

Env vars:
    QWEN3_ENABLED          "1"/"true"/"yes" to enable (default: off)
    QWEN3_ENDPOINT_URL     base URL, e.g. https://<id>.runpod.net
    QWEN3_API_KEY          bearer token for the endpoint
    QWEN3_MODEL            model id sent in the payload (default: qwen3-0.6b-quran)
    QWEN3_TIMEOUT_SECONDS  per-request timeout (default: 60)
    QWEN3_MAX_RETRIES      retries after the first attempt (default: 3)
    QWEN3_BACKOFF_BASE     base backoff in seconds (default: 0.5)

Failure contract: when the feature is disabled, unconfigured, or the
endpoint is unreachable/failing after retries, every entry point raises
:class:`Qwen3Unavailable` — a typed signal so callers can fall back to the
pre-existing (deterministic) behavior. Client errors (4xx) raise
:class:`Qwen3RequestError` instead: those are config bugs, not fallbacks.

Container rule: stdlib + httpx only. No ``backend.*`` imports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("mizan.api.qwen3_client")

DEFAULT_MODEL = "qwen3-0.6b-quran"
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 0.5
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class Qwen3Error(Exception):
    """Base error for the Qwen3 serverless integration."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


class Qwen3Unavailable(Qwen3Error):
    """The endpoint cannot serve this request right now — or the feature is
    off. Callers should fall back to the pre-existing behavior."""


class Qwen3RequestError(Qwen3Error):
    """The endpoint rejected the request (4xx). Not retryable — a config or
    payload bug, not a fallback situation."""


class Qwen3ResponseError(Qwen3Error):
    """The endpoint answered, but the payload was not usable."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


@dataclass
class Qwen3Config:
    enabled: bool = False
    endpoint_url: str = ""
    api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_s: float = DEFAULT_BACKOFF_BASE_S
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Qwen3Config:
        def _float(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, "") or default)
            except ValueError:
                return default

        def _int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, "") or default)
            except ValueError:
                return default

        return cls(
            enabled=_env_flag("QWEN3_ENABLED", False),
            endpoint_url=os.getenv("QWEN3_ENDPOINT_URL", "").strip().rstrip("/"),
            api_key=os.getenv("QWEN3_API_KEY", "").strip(),
            model=os.getenv("QWEN3_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            timeout_s=_float("QWEN3_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_S),
            max_retries=max(0, _int("QWEN3_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
            backoff_base_s=_float("QWEN3_BACKOFF_BASE", DEFAULT_BACKOFF_BASE_S),
        )

    @property
    def configured(self) -> bool:
        return bool(self.endpoint_url and self.api_key)

    def endpoint_host(self) -> str:
        """Host only — safe to log/expose; never the key."""
        try:
            return self.endpoint_url.split("://", 1)[1].split("/", 1)[0]
        except IndexError:
            return ""


def qwen3_enabled() -> bool:
    """Feature flag + minimal config check, read live from the environment."""
    cfg = Qwen3Config.from_env()
    return cfg.enabled and cfg.configured


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — shared by sync/async paths and the provider)
# ---------------------------------------------------------------------------


def chat_completions_url(config: Qwen3Config) -> str:
    return f"{config.endpoint_url}{CHAT_COMPLETIONS_PATH}"


def auth_headers(config: Qwen3Config) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
    }


def build_chat_payload(
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str | None = None,
    stream: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chat_messages: list[dict[str, str]] = []
    if system:
        chat_messages.append({"role": "system", "content": system})
    chat_messages.extend(messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if extra:
        payload.update(extra)
    return payload


def extract_text(data: dict[str, Any]) -> str:
    try:
        choices = data["choices"]
        text = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise Qwen3ResponseError("bad_payload", f"no choices[0].message.content: {exc}") from exc
    if not isinstance(text, str):
        raise Qwen3ResponseError("bad_payload", "choices[0].message.content is not a string")
    return text


def extract_usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage")
    return dict(usage) if isinstance(usage, dict) else {}


def is_retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status < 600


def backoff_delay(attempt: int, base: float) -> float:
    """Deterministic exponential backoff: base * 2**attempt, capped at 30s."""
    return min(base * (2**attempt), 30.0)


@dataclass
class Qwen3Result:
    text: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class Qwen3Client:
    """Thin OpenAI-compatible client with retry/backoff and typed errors."""

    def __init__(self, config: Qwen3Config | None = None) -> None:
        self.config = config or Qwen3Config.from_env()

    def _require_ready(self) -> None:
        if not self.config.enabled:
            raise Qwen3Unavailable("qwen3_disabled", "QWEN3_ENABLED is not set")
        if not self.config.configured:
            raise Qwen3Unavailable(
                "qwen3_not_configured", "QWEN3_ENDPOINT_URL / QWEN3_API_KEY not set"
            )

    def _payload(self, messages: list[dict[str, str]], stream: bool, **opts: Any) -> dict[str, Any]:
        return build_chat_payload(
            messages,
            model=opts.get("model") or self.config.model,
            max_tokens=int(opts.get("max_tokens", 1024)),
            temperature=float(opts.get("temperature", 0.7)),
            system=opts.get("system"),
            stream=stream,
            extra=opts.get("extra"),
        )

    def _raise_for_status(self, status: int, body: str) -> None:
        if is_retryable_status(status):
            raise Qwen3Unavailable(
                "qwen3_retryable_status", f"endpoint returned HTTP {status}: {body[:200]}"
            )
        if status in (401, 403):
            raise Qwen3RequestError("qwen3_auth", f"endpoint rejected credentials (HTTP {status})")
        raise Qwen3RequestError("qwen3_rejected", f"endpoint returned HTTP {status}: {body[:200]}")

    # -- sync -----------------------------------------------------------

    def generate_sync(self, messages: list[dict[str, str]], **opts: Any) -> Qwen3Result:
        """Blocking generation (used by the sync provider path)."""
        self._require_ready()
        url = chat_completions_url(self.config)
        payload = self._payload(messages, stream=False, **opts)
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                with httpx.Client(timeout=self.config.timeout_s) as client:
                    resp = client.post(url, headers=auth_headers(self.config), json=payload)
                if resp.status_code != 200:
                    self._raise_for_status(resp.status_code, resp.text)
                data = resp.json()
                return Qwen3Result(
                    text=extract_text(data),
                    model=data.get("model", self.config.model),
                    usage=extract_usage(data),
                    raw=data,
                )
            except (Qwen3RequestError, Qwen3ResponseError):
                raise
            except Qwen3Unavailable as exc:
                last_error = exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = Qwen3Unavailable("qwen3_transport", f"{type(exc).__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001 — normalize unexpected failures
                last_error = Qwen3Unavailable("qwen3_error", f"{type(exc).__name__}: {exc}")
            if attempt < self.config.max_retries:
                delay = backoff_delay(attempt, self.config.backoff_base_s)
                logger.warning(
                    "qwen3 generate attempt %d failed (%s); retrying in %.1fs",
                    attempt + 1,
                    last_error,
                    delay,
                )
                time.sleep(delay)
        raise Qwen3Unavailable(
            "qwen3_exhausted",
            f"all {self.config.max_retries + 1} attempts failed: {last_error}",
        )

    # -- async ----------------------------------------------------------

    async def generate(self, messages: list[dict[str, str]], **opts: Any) -> Qwen3Result:
        """Async generation."""
        self._require_ready()
        url = chat_completions_url(self.config)
        payload = self._payload(messages, stream=False, **opts)
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout_s) as client:
                    resp = await client.post(url, headers=auth_headers(self.config), json=payload)
                if resp.status_code != 200:
                    self._raise_for_status(resp.status_code, resp.text)
                data = resp.json()
                return Qwen3Result(
                    text=extract_text(data),
                    model=data.get("model", self.config.model),
                    usage=extract_usage(data),
                    raw=data,
                )
            except (Qwen3RequestError, Qwen3ResponseError):
                raise
            except Qwen3Unavailable as exc:
                last_error = exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = Qwen3Unavailable("qwen3_transport", f"{type(exc).__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001 — normalize unexpected failures
                last_error = Qwen3Unavailable("qwen3_error", f"{type(exc).__name__}: {exc}")
            if attempt < self.config.max_retries:
                delay = backoff_delay(attempt, self.config.backoff_base_s)
                logger.warning(
                    "qwen3 generate attempt %d failed (%s); retrying in %.1fs",
                    attempt + 1,
                    last_error,
                    delay,
                )
                await asyncio.sleep(delay)
        raise Qwen3Unavailable(
            "qwen3_exhausted",
            f"all {self.config.max_retries + 1} attempts failed: {last_error}",
        )

    async def generate_stream(
        self, messages: list[dict[str, str]], **opts: Any
    ) -> AsyncIterator[str]:
        """Yield text deltas from a streaming chat-completions call.

        If the endpoint does not speak SSE, falls back to one non-streaming
        call and yields the full text once. Any failure raises
        Qwen3Unavailable (callers fall back).
        """
        self._require_ready()
        url = chat_completions_url(self.config)
        payload = self._payload(messages, stream=True, **opts)
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout_s) as client:
                    async with client.stream(
                        "POST", url, headers=auth_headers(self.config), json=payload
                    ) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            self._raise_for_status(
                                resp.status_code, body.decode("utf-8", "replace")
                            )
                        content_type = resp.headers.get("content-type", "")
                        if "text/event-stream" not in content_type:
                            # Not SSE — degrade to a single non-streaming call.
                            logger.info(
                                "qwen3 endpoint did not return SSE; using non-streaming fallback"
                            )
                            result = await self.generate(messages, **opts)
                            yield result.text
                            return
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            chunk = line[5:].strip()
                            if chunk == "[DONE]":
                                return
                            try:
                                data = json.loads(chunk)
                            except json.JSONDecodeError:
                                continue
                            choices = data.get("choices") or []
                            if not choices:
                                continue
                            delta = (choices[0].get("delta") or {}).get("content")
                            if delta:
                                yield delta
                        return
            except (Qwen3RequestError, Qwen3ResponseError):
                raise
            except Qwen3Unavailable as exc:
                last_error = exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = Qwen3Unavailable("qwen3_transport", f"{type(exc).__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001 — normalize unexpected failures
                last_error = Qwen3Unavailable("qwen3_error", f"{type(exc).__name__}: {exc}")
            if attempt < self.config.max_retries:
                await asyncio.sleep(backoff_delay(attempt, self.config.backoff_base_s))
        raise Qwen3Unavailable(
            "qwen3_exhausted",
            f"all {self.config.max_retries + 1} attempts failed: {last_error}",
        )

    async def health(self, *, probe: bool = False) -> dict[str, Any]:
        """Config report; with probe=True also runs a 1-token generation."""
        report: dict[str, Any] = {
            "enabled": self.config.enabled,
            "configured": self.config.configured,
            "endpoint_host": self.config.endpoint_host(),
            "model": self.config.model,
            "timeout_s": self.config.timeout_s,
            "max_retries": self.config.max_retries,
        }
        if not probe:
            return report
        try:
            result = await self.generate(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
            )
            report["reachable"] = True
            report["probe_model"] = result.model
        except Qwen3Error as exc:
            report["reachable"] = False
            report["probe_error"] = {"code": exc.code, "detail": exc.detail}
        return report


def get_client(config: Qwen3Config | None = None) -> Qwen3Client:
    """Fresh client from the current environment (no stale-config caching)."""
    return Qwen3Client(config or Qwen3Config.from_env())
