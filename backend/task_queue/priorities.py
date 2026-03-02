"""Islamic jurisprudence-based task priority levels."""

from enum import IntEnum


class TaskPriority(IntEnum):
    """Priority levels derived from Usul al-Fiqh maqasid framework.

    DHARURAH  - Necessity: security alerts, critical errors
    HAJAH     - Need: user-facing requests
    TAHSINIYYAH - Improvement: background learning, optimization
    TAKMILIYYAH - Complementary: analytics, telemetry
    """

    DHARURAH = 0
    HAJAH = 1
    TAHSINIYYAH = 2
    TAKMILIYYAH = 3
