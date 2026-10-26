"""Wall-clock provider budgets, independent of SDK socket inactivity timers."""

import math
import os
from dataclasses import dataclass


def bounded_seconds(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        if not math.isfinite(value):
            raise ValueError("non-finite duration")
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


@dataclass(frozen=True)
class ProviderLimits:
    first_progress: float
    progress: float
    total: float


def provider_limits() -> ProviderLimits:
    # Sixty seconds matches the default SDK I/O budget, but comments and
    # hidden reasoning cannot indefinitely postpone the first usable output.
    return ProviderLimits(
        bounded_seconds("MIZAN_LLM_FIRST_PROGRESS_SECONDS", 60, minimum=1, maximum=180),
        bounded_seconds("MIZAN_LLM_PROGRESS_SECONDS", 60, minimum=1, maximum=180),
        bounded_seconds("MIZAN_LLM_MAX_CALL_SECONDS", 300, minimum=1, maximum=900),
    )


class ProviderDeadlineExceeded(TimeoutError):
    def __init__(self, phase: str):
        self.phase = phase
        super().__init__("The response model exceeded its configured wait limit")


def chat_run_seconds() -> float:
    return bounded_seconds("MIZAN_CHAT_RUN_SECONDS", 900, minimum=30, maximum=3600)
