"""Ruh Remote LLM Provider for MIZAN (via RunPod Serverless).

Calls the RunPod serverless endpoint (GPU) instead of running the model
locally on CPU. The endpoint speaks OpenAI chat-completion format.

Env vars:
    RUNPOD_ENDPOINT_ID: e.g. "your-endpoint-id"
    RUNPOD_API_KEY: RunPod API key
"""

import logging
import re
from typing import cast

from providers import BaseLLMProvider, ContentBlock, LLMResponse

logger = logging.getLogger("mizan.providers.ruh_remote")


class RuhRemoteProvider(BaseLLMProvider):
    """Remote Ruh Model provider via RunPod Serverless."""

    provider_name = "ruh-remote"
    supports_tools = False
    submission_path = "runsync"

    def __init__(self, endpoint_id: str, api_key: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", endpoint_id):
            raise ValueError("Invalid RunPod endpoint ID")
        self.endpoint_id = endpoint_id
        self.api_key = api_key
        self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"

    def _poll_until_done(self, job_id: str, headers: dict, timeout_s: int = 300) -> dict:
        """Poll RunPod /status/{job_id} until COMPLETED, FAILED, or timeout."""
        import json
        import time
        import urllib.error
        import urllib.request

        url = f"{self.base_url}/status/{job_id}"
        deadline = time.monotonic() + timeout_s
        delay = 2.0

        while time.monotonic() < deadline:
            # URL is hardcoded to https://api.runpod.ai - S310 false positive
            req = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    result = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in {400, 401, 403, 404}:
                    raise ValueError(f"RunPod status unavailable (HTTP {exc.code})") from exc
                logger.warning("RunPod status poll HTTP %s", exc.code)
                time.sleep(delay)
                continue
            except Exception as exc:
                logger.warning("RunPod status poll failed: %s", exc)
                time.sleep(delay)
                continue

            status = result.get("status")
            if status == "COMPLETED":
                return cast(dict, result)
            if status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
                raise ValueError(f"RunPod job ended with status {status}")

            # IN_QUEUE or IN_PROGRESS — wait and retry with backoff
            time.sleep(delay)
            delay = min(delay * 1.5, 10.0)

        raise TimeoutError(f"RunPod job {job_id} did not complete in {timeout_s}s")

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Generate a response via the RunPod endpoint."""
        payload = {"input": self._build_input(max_tokens, system, messages, tools, temperature)}
        result = self._run_job(payload)
        return self._parse_output(result)

    def _build_input(self, max_tokens, system, messages, tools, temperature) -> dict:
        runpod_messages = [{"role": "system", "content": system}] if system else []
        runpod_messages.extend(messages)
        return {
            "messages": runpod_messages,
            "max_tokens": max_tokens,
            "temperature": temperature if temperature is not None else 1.0,
        }

    def _run_job(self, payload: dict) -> dict:
        """Run the queue protocol independently of the worker's model protocol."""
        import json
        import urllib.request

        url = f"{self.base_url}/{self.submission_path}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        data = json.dumps(payload).encode("utf-8")
        # URL is hardcoded to https://api.runpod.ai - S310 false positive
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # noqa: S310

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
                result = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.error("RunPod request failed: %s", exc)
            raise

        if not isinstance(result, dict):
            raise ValueError("RunPod returned a malformed job envelope")

        # Handle async: /runsync may return IN_QUEUE/IN_PROGRESS instead of
        # waiting. Poll /status/{id} until COMPLETED or FAILED.
        status = result.get("status")
        if status in ("IN_QUEUE", "IN_PROGRESS"):
            job_id = result.get("id")
            if not job_id:
                raise ValueError(f"RunPod returned {status} without job id: {result}")
            result = self._poll_until_done(job_id, headers)

        status = result.get("status")
        if status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
            raise ValueError(f"RunPod job ended with status {status}")
        if status != "COMPLETED":
            raise ValueError("RunPod did not return a completed job")
        if not isinstance(result.get("output"), dict) or result["output"].get("error"):
            raise ValueError("RunPod worker returned an error or malformed output")
        return cast(dict, result)

    def _parse_output(self, result: dict) -> LLMResponse:
        # Parse response: {"output": {"choices": [...], "usage": {...}}}
        # or {"output": {...}} directly
        output = result.get("output", {})
        if isinstance(output, dict) and "choices" in output:
            choices = output["choices"]
        else:
            # Fallback: output is the choices dict directly
            choices = output.get("choices", [])

        if not choices:
            raise ValueError(f"Empty response from RunPod: {result}")

        content = choices[0].get("message", {}).get("content", "")
        usage = output.get("usage", {})

        # Build LLMResponse
        blocks = [ContentBlock(type="text", text=content)] if content else []

        return LLMResponse(
            content=blocks,
            stop_reason={"stop": "end_turn", "length": "max_tokens"}.get(
                choices[0].get("finish_reason"), "incomplete"
            ),
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            model=output.get("model", ""),
        )
