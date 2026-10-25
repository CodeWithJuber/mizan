"""Opt-in Mizan hybrid runtime: base LLM + own NLP + deterministic gates."""

from mizan_hybrid.config import DEFAULT_BASE_MODEL, DEFAULT_BASE_REVISION, HybridConfig
from mizan_hybrid.gates import (
    AuditLog,
    Decision,
    Outcome,
    SourceRecord,
    SourceRegistry,
    admit_source,
    gate_response,
    validate_grade_claim,
)
from mizan_hybrid.provider import MizanHybridProvider, create_hybrid_provider_from_env

__all__ = [
    "DEFAULT_BASE_MODEL",
    "DEFAULT_BASE_REVISION",
    "AuditLog",
    "Decision",
    "HybridConfig",
    "MizanHybridProvider",
    "Outcome",
    "SourceRecord",
    "SourceRegistry",
    "admit_source",
    "create_hybrid_provider_from_env",
    "gate_response",
    "validate_grade_claim",
]
