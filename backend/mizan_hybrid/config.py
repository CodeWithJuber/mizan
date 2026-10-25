"""Configuration for the opt-in Mizan hybrid research runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_BASE_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes"}


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, "") or default)
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


@dataclass(frozen=True)
class HybridConfig:
    """Runtime settings; the API key is never included in ``safe_dict``."""

    enabled: bool = False
    base_provider: str = "openai-compatible"
    base_model: str = DEFAULT_BASE_MODEL
    base_revision: str = DEFAULT_BASE_REVISION
    base_url: str = ""
    base_api_key: str = ""
    source_registry_path: str = ""
    nlp_advisory: bool = True
    target_language: str = "any"
    max_gate_retries: int = 1
    retry_max_tokens: int = 4096
    audit_log_path: str = ""

    @classmethod
    def from_env(cls) -> HybridConfig:
        return cls(
            enabled=_flag("MIZAN_HYBRID_ENABLED"),
            base_provider=os.getenv("MIZAN_BASE_PROVIDER", "openai-compatible").strip(),
            base_model=os.getenv("MIZAN_BASE_MODEL", DEFAULT_BASE_MODEL).strip()
            or DEFAULT_BASE_MODEL,
            base_revision=os.getenv("MIZAN_BASE_REVISION", DEFAULT_BASE_REVISION).strip()
            or DEFAULT_BASE_REVISION,
            base_url=os.getenv("MIZAN_BASE_URL", "").strip().rstrip("/"),
            base_api_key=os.getenv("MIZAN_BASE_API_KEY", "").strip(),
            source_registry_path=os.getenv("MIZAN_SOURCE_REGISTRY", "").strip(),
            nlp_advisory=_flag("MIZAN_NLP_ADVISORY", True),
            target_language=os.getenv("MIZAN_TARGET_LANGUAGE", "any").strip().lower() or "any",
            max_gate_retries=_integer("MIZAN_GATE_MAX_RETRIES", 1, 0, 2),
            retry_max_tokens=_integer("MIZAN_RETRY_MAX_TOKENS", 4096, 1, 32768),
            audit_log_path=os.getenv("MIZAN_AUDIT_LOG", "").strip(),
        )

    @property
    def configured(self) -> bool:
        if not self.enabled or not self.base_model or not self.base_provider:
            return False
        if self.base_provider == "openai-compatible":
            return bool(self.base_url and self.base_api_key)
        return True

    @property
    def registry_file(self) -> Path | None:
        return Path(self.source_registry_path) if self.source_registry_path else None

    def safe_dict(self) -> dict[str, object]:
        """Return operator-safe metadata without credentials or source contents."""
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "base_provider": self.base_provider,
            "base_model": self.base_model,
            "base_revision": self.base_revision,
            "base_url": self.base_url,
            "source_registry_configured": bool(self.source_registry_path),
            "nlp_advisory": self.nlp_advisory,
            "target_language": self.target_language,
            "max_gate_retries": self.max_gate_retries,
            "retry_max_tokens": self.retry_max_tokens,
            "audit_log_configured": bool(self.audit_log_path),
        }
