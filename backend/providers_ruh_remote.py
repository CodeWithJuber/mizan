"""Ruh Remote LLM Provider for MIZAN (via RunPod Serverless).

Calls the RunPod serverless endpoint (GPU) instead of running the model
locally on CPU. The endpoint speaks OpenAI chat-completion format.

Env vars:
    RUNPOD_ENDPOINT_ID: e.g. "6o38qhvti4knkk"
    RUNPOD_API_KEY: RunPod API key
"""

import logging

from providers import BaseLLMProvider, ContentBlock, LLMResponse

logger = logging.getLogger("mizan.providers.ruh_remote")


class RuhRemoteProvider(BaseLLMProvider):
    """Remote Ruh Model provider via RunPod Serverless."""

    provider_name = "ruh-remote"

    def __init__(self, endpoint_id: str, api_key: str) -> None:
        self.endpoint_id = endpoint_id
        self.api_key = api_key
        self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"

    def _poll_until_done(self, job_id: str, headers: dict, timeout_s: int = 300) -> dict:
        """Poll RunPod /status/{job_id} until COMPLETED, FAILED, or timeout."""
        import json
        import time
        import urllib.request

        url = f"{self.base_url}/status/{job_id}"
        deadline = time.time() + timeout_s
        delay = 2.0

        while time.time() < deadline:
            # URL is hardcoded to https://api.runpod.ai - S310 false positive
            req = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    result = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                logger.warning("RunPod status poll failed: %s", exc)
                time.sleep(delay)
                continue

            status = result.get("status")
            if status == "COMPLETED":
                return result
            if status == "FAILED":
                raise ValueError(f"RunPod job failed: {result}")

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
        import json
        import urllib.request

        # Build messages with system prompt
        runpod_messages = []
        if system:
            runpod_messages.append({"role": "system", "content": system})
        runpod_messages.extend(messages)

        payload = {
            "input": {
                "messages": runpod_messages,
                "max_tokens": max_tokens,
                "temperature": temperature if temperature is not None else 1.0,
            }
        }

        url = f"{self.base_url}/runsync"
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

        # Handle async: /runsync may return IN_QUEUE/IN_PROGRESS instead of
        # waiting. Poll /status/{id} until COMPLETED or FAILED.
        status = result.get("status")
        if status in ("IN_QUEUE", "IN_PROGRESS"):
            job_id = result.get("id")
            if not job_id:
                raise ValueError(f"RunPod returned {status} without job id: {result}")
            result = self._poll_until_done(job_id, headers)

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
            stop_reason=choices[0].get("finish_reason", "end_turn"),
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            model=model,
        )
