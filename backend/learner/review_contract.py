"""Provenance rules for captured model output; review is not original authorship."""

import hashlib
import json
import math

DEFAULT_MIN_QUALITY = 0.8


def validate_quality(score: float) -> None:
    if isinstance(score, bool) or not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("Quality score must be between 0.0 and 1.0")


def content_hash(prompt: str, response: str, provider: str, model: str) -> str:
    payload = json.dumps(
        [prompt, response, provider, model], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()
