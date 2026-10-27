"""Administrator-managed runtime settings.

Every operator setting MIZAN reads from the environment can also be changed by
an administrator in the UI. Saved values live in
``$MIZAN_DATA_DIR/runtime_settings.json`` (API keys and tokens sealed with the
data key) and are applied to the process environment at startup, before
modules read them, and immediately when saved. A saved value wins over the
server's ``.env``; resetting it restores the server's own value.

``apply`` says when a change takes effect:

- ``live``: the next request reads it.
- ``provider``: the active model is rebuilt for every agent right away.
- ``restart``: read once at startup; the UI shows "restart required".
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Kind = Literal["text", "int", "float", "bool", "choice", "secret", "url"]
Apply = Literal["live", "provider", "restart"]


@dataclass(frozen=True)
class Setting:
    key: str
    group: str
    label: str
    kind: Kind
    description: str
    default: str = ""
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    apply: Apply = "live"
    allow_empty: bool = True


_PROVIDERS = (
    "auto",
    "anthropic",
    "openrouter",
    "openai",
    "ollama",
    "ruh",
    "ruh-remote",
    "qwen3",
    "mizan-hybrid",
    "mizan-owned",
    "mizan-minimind",
)
_BOOL = ("true", "false")

SETTINGS: tuple[Setting, ...] = (
    # ── Orchestration ──
    Setting("MIZAN_ORCHESTRATION", "Model", "Who directs the work", "choice",
            "mizan: MIZAN's own architecture (Tadbir) plans, runs every tool and verifies; the "
            "language model only writes words and code and never controls a tool. hybrid: what "
            "MIZAN does not recognise goes to the model-driven agent loop. llm: the model "
            "drives the agent loop. strict is the former name of mizan.",
            "mizan", ("mizan", "hybrid", "strict", "llm")),
    Setting("MIZAN_DEBUG_MODE", "Model", "Debug mode (base model vs MIZAN)", "choice",
            "Who may send one message to the base model alone and to MIZAN side by side, with "
            "MIZAN's full trace: admins, every signed-in user, or no one. A comparison runs "
            "the model twice.",
            "admins", ("admins", "users", "off")),
    Setting("MIZAN_IMTIHAN_CONCURRENCY", "Model", "AGI test tasks at once", "int",
            "How many AGI test tasks run at the same time (each runs both arms). Chats are "
            "never queued behind a run: every run of an agent works on its own copy.",
            "4", minimum=1, maximum=8),
    Setting("MIZAN_MUHASABA", "Model", "Self-review (Muhasaba)", "choice",
            "Once a day MIZAN re-checks the answers the model gave in words: arithmetic and "
            "quoted Quran or hadith text. Where it proves one wrong it posts a correction in "
            "that chat. Users can stop it with the chat preference muhasaba: off.",
            "on", ("on", "off")),
    Setting("MIZAN_TRUTH_GATE", "Model", "Truth Gate (Sidq)", "choice",
            "Before an answer is shown MIZAN checks what it can prove: arithmetic, quoted "
            "Quran and hadith text, actions claimed with no receipt, and links it never "
            "found. strict corrects or removes what is wrong, flag only marks it, off skips "
            "the check.",
            "strict", ("strict", "flag", "off")),
    Setting("MIZAN_AHL_DHIKR", "Model", "Ask sources (Ahl al-Dhikr)", "choice",
            "When a question asks about the world and the answer is in the language model's "
            "own words, MIZAN asks its sources about each claim before the answer is shown "
            "(what it settled before, Wikipedia, a web search) and shows what they say. What "
            "a source settles is kept, so the same claim comes from memory next time.",
            "on", ("on", "off")),
    Setting("MIZAN_CONTACT", "Model", "Contact for sources", "text",
            "How the sites MIZAN reads (Wikipedia and others) can reach this server's "
            "operator, sent in MIZAN's User-Agent as their policies ask, for example an "
            "email address. Empty sends only the project's address.",
            ""),
    Setting("MIZAN_AMANAH", "Model", "Injection check (Amanah)", "choice",
            "Outside text (pages, files, tool results, pasted text) is checked for "
            "instructions aimed at the AI. evidence adds a model trained on licensed "
            "prompt-injection datasets to the patterns; rules uses the patterns alone.",
            "evidence", ("evidence", "rules")),
    Setting("MIZAN_MURAQABAH", "Model", "Watchers (Muraqabah)", "choice",
            "Each user's watchers run on schedule (daily, around prayers, on Hijri days, or "
            "when a page changes), quiet during salah, within a daily attention budget.",
            "on", ("on", "off")),
    Setting("MIZAN_HARNESS_EVOLUTION", "Model", "Instruction renewal (Tajdid)", "choice",
            "After repeated failures MIZAN asks the model to rewrite one of its code "
            "instructions, tries the new version on part of the work, and keeps it only when "
            "MIZAN's own checks show it is better.",
            "on", ("on", "off")),
    Setting("MIZAN_BUDGET_DAILY_USD", "Model", "Daily spending limit per user (USD)", "float",
            "Hard limit on what each user's model calls may cost per local day. Every call is "
            "checked before it is sent and its answer length capped to what is left, so no "
            "call can overspend. Administrators are not limited unless you set a limit for "
            "them; users can lower their own. Empty: no limit.", "", minimum=0),
    Setting("MIZAN_BUDGET_MONTHLY_USD", "Model", "Monthly spending limit per user (USD)",
            "float",
            "Hard limit on what each user's model calls may cost per calendar month, checked "
            "the same way as the daily limit. Empty: no limit.", "", minimum=0),
    Setting("MIZAN_BUDGET_UNPRICED", "Model", "Models with no known price", "choice",
            "While a spending limit applies, a model MIZAN has no price for cannot be kept "
            "inside it. refuse blocks such calls; allow lets them run and charges what the "
            "provider reports.", "refuse", ("refuse", "allow")),
    Setting("MIZAN_LISAN_MODELS", "Model", "Models for code work (Wazn)", "text",
            "Optional comma-separated model IDs, cheapest first. MIZAN sends code work to the "
            "cheapest model whose verified success is high enough and moves one step up after "
            "each failed attempt. Empty uses the agent's model.", ""),
    Setting("MIZAN_LISAN_READINESS", "Model", "Readiness for a cheaper model", "float",
            "How often (0.05-0.99) a cheaper model's work must verify before MIZAN gives it "
            "the work first.", "0.7", (), 0.05, 0.99),
    # ── Model ──
    Setting("LLM_PROVIDER", "Model", "Provider", "choice",
            "auto picks Anthropic, then OpenRouter, then OpenAI from the configured keys.",
            "auto", _PROVIDERS, apply="provider"),
    Setting("DEFAULT_MODEL", "Model", "Default model", "text",
            "Model ID for agents, e.g. claude-opus-5-5 or anthropic/claude-opus-5.5 on "
            "OpenRouter. Empty uses the provider's default.", "", apply="provider"),
    Setting("MIZAN_OPENROUTER_FALLBACKS", "Model", "OpenRouter fallbacks", "text",
            "auto: free tool-capable fallbacks for a free model; none; or a comma list of "
            "model IDs.", "auto"),
    Setting("MIZAN_CHAT_EFFORT", "Model", "Claude effort", "choice",
            "How much the Claude model thinks per answer.", "high",
            ("low", "medium", "high", "xhigh", "max")),
    Setting("MIZAN_CHAT_TEMPERATURE", "Model", "Temperature (non-Claude)", "float",
            "Sampling temperature for other providers; Claude ignores it.", "0.5", (), 0, 1),
    Setting("MIZAN_CHAT_MAX_OUTPUT_TOKENS", "Model", "Max output tokens", "int",
            "Per-call output budget; empty uses the model's cap.", "", (), 256, 128000),
    Setting("MIZAN_SUPPORT_MODEL", "Model", "Teacher model (OpenRouter)", "text",
            "Explicit model for the teacher/support endpoint only.", ""),
    Setting("MIZAN_OWNED_ONLY", "Model", "Owned model only", "bool",
            "Block hosted inference entirely and use only MIZAN's own model.", "false",
            _BOOL, apply="provider"),
    # ── API keys ──
    Setting("ANTHROPIC_API_KEY", "API keys", "Anthropic API key", "secret",
            "Starts with sk-ant-. Without it Claude models route through OpenRouter.",
            apply="provider"),
    Setting("OPENROUTER_API_KEY", "API keys", "OpenRouter API key", "secret",
            "Access to 300+ hosted models.", apply="provider"),
    Setting("OPENAI_API_KEY", "API keys", "OpenAI API key", "secret", "", apply="provider"),
    Setting("MIZAN_BASE_API_KEY", "API keys", "Hybrid base model API key", "secret",
            "Key for the OpenAI-compatible base model endpoint.", apply="restart"),
    Setting("HF_TOKEN", "API keys", "Hugging Face token", "secret",
            "Lets MIZAN list and import your datasets and models from Hugging Face, private "
            "ones included, for admins only. MIZAN only reads with it; a read-only token is "
            "enough."),
    Setting("ARC_API_KEY", "API keys", "ARC-AGI-3 API key", "secret",
            "Lets MIZAN's explorer play the official ARC-AGI-3 games (AGI Test)."),
    # ── Chat limits ──
    Setting("MIZAN_CHAT_MAX_STEPS", "Chat limits", "Tool steps per answer", "int",
            "Tool rounds per run before a progress report.", "100", (), 1, 1000),
    Setting("MIZAN_CHAT_MAX_CONTINUATIONS", "Chat limits", "Auto-continuations", "int",
            "Continuations of a length-limited answer.", "20", (), 0, 200),
    Setting("MIZAN_CHAT_TOOL_RESULT_CHARS", "Chat limits", "Tool result characters", "int",
            "Characters of one tool result sent back to the model.", "20000", (), 2000, 500000),
    Setting("MIZAN_CONTEXT_HISTORY_TOKENS", "Chat limits", "History budget (tokens)", "int",
            "Older turns beyond this become a running summary.", "150000", (), 2000, 2000000),
    Setting("MIZAN_CONTEXT_FILL", "Chat limits", "Context share for history", "float",
            "Share of the model's context window used for history.", "0.5", (), 0.1, 0.8),
    Setting("MIZAN_ANTHROPIC_COMPACTION", "Chat limits", "Claude server compaction", "bool",
            "Let Claude compact very long single runs.", "true", _BOOL),
    Setting("MIZAN_CHAT_TOOL_SCHEMA_LIMIT", "Chat limits", "Tools offered per request", "int",
            "Tool definitions sent per request, including discovery.", "8", (), 2, 32),
    Setting("MIZAN_CHAT_TOOL_SCHEMA_BYTES", "Chat limits", "Tool definition bytes", "int",
            "Size budget for the tool definitions per request.", "12288", (), 4096, 65536),
    Setting("MIZAN_LLM_FIRST_PROGRESS_SECONDS", "Chat limits", "First progress timeout (s)",
            "int", "Wait for first visible text or tool progress.", "60", (), 1, 180),
    Setting("MIZAN_LLM_BUFFERED_FIRST_PROGRESS_SECONDS", "Chat limits",
            "First progress timeout, non-streaming (s)", "int", "", "180", (), 1, 900),
    Setting("MIZAN_LLM_PROGRESS_SECONDS", "Chat limits", "Progress timeout (s)", "int",
            "Wait between meaningful progress.", "60", (), 1, 180),
    Setting("MIZAN_LLM_MAX_CALL_SECONDS", "Chat limits", "Max model call (s)", "int",
            "", "600", (), 1, 1800),
    Setting("MIZAN_CHAT_RUN_SECONDS", "Chat limits", "Max chat run (s)", "int",
            "Context, queue and agent execution together.", "1800", (), 30, 7200),
    # ── Learning & memory ──
    Setting("MIZAN_OWNED_LEARNING_AUTORUN", "Learning & memory", "Automatic own-model training",
            "bool", "Train when a human-approved bundle appears; never uses raw chats.", "true",
            _BOOL),
    Setting("MIZAN_MEMORY_MAINTENANCE", "Learning & memory", "Memory maintenance", "bool",
            "Hourly consolidation, dream replay and forgetting.", "true", _BOOL,
            apply="restart"),
    Setting("MIZAN_MEMORY_MAINTENANCE_SECONDS", "Learning & memory",
            "Maintenance interval (s)", "int", "", "3600", (), 60, 86400),
    Setting("DEEP_FACULTY_LOOP", "Learning & memory", "Active faculty loop", "bool",
            "Let Basira/Hawa/Hikmah actively gate and redirect the agent (default advisory).",
            "false", _BOOL, apply="restart"),
    Setting("RUH_ENABLED", "Learning & memory", "Ruh model", "bool",
            "Enable the local Ruh provider (needs a checkpoint).", "false", _BOOL,
            apply="restart"),
    # ── NLP & hybrid ──
    Setting("MIZAN_NLP_NATIVE_WSD", "NLP & hybrid", "Native Arabic sense disambiguation", "bool",
            "Use mizan.nlp's native WSD paths and tool.", "false", _BOOL, apply="restart"),
    Setting("MIZAN_NLP_ADVISORY", "NLP & hybrid", "NLP advisory notes", "bool",
            "", "true", _BOOL, apply="restart"),
    Setting("MIZAN_TARGET_LANGUAGE", "NLP & hybrid", "Target language", "text",
            "any, or a language code the hybrid gate enforces.", "any", apply="restart"),
    Setting("MIZAN_GATE_MAX_RETRIES", "NLP & hybrid", "Gate retries", "int",
            "", "1", (), 0, 2, apply="restart"),
    Setting("MIZAN_RETRY_MAX_TOKENS", "NLP & hybrid", "Gate retry tokens", "int",
            "", "4096", (), 64, 65536, apply="restart"),
    Setting("MIZAN_HYBRID_ENABLED", "NLP & hybrid", "Hybrid runtime", "bool",
            "Route through the hybrid base model with MIZAN's gates.", "false", _BOOL,
            apply="restart"),
    Setting("MIZAN_BASE_PROVIDER", "NLP & hybrid", "Hybrid base provider", "text",
            "", "openai-compatible", apply="restart"),
    Setting("MIZAN_BASE_MODEL", "NLP & hybrid", "Hybrid base model", "text",
            "", "", apply="restart"),
    Setting("MIZAN_BASE_URL", "NLP & hybrid", "Hybrid base URL", "url", "", "",
            apply="restart"),
    Setting("MIZAN_BASE_CONTEXT_WINDOW", "NLP & hybrid", "Hybrid context window", "int",
            "", "32768", (), 512, 2000000, apply="restart"),
    # ── Connectors, skills, coding ──
    Setting("MIZAN_PUBLIC_URL", "Connectors & coding", "Public URL", "url",
            "OAuth callback base when a proxy rewrites Host; empty uses the request.", ""),
    Setting("MIZAN_MCP_HOST_STDIO", "Connectors & coding", "Local MCP servers on host",
            "choice", "Who may run stdio MCP servers on the backend host; others use the "
            "sandbox.", "admin", ("admin", "all", "off")),
    Setting("MIZAN_MCP_ALLOW_PRIVATE_HOSTS", "Connectors & coding",
            "Private hosts connectors may reach", "text", "Comma-separated host names.", ""),
    Setting("MIZAN_PROJECT_SKILLS", "Connectors & coding", "Project skills", "bool",
            "Load .agents/skills and .claude/skills from the bound project.", "true", _BOOL),
    # ── Channels ──
    Setting("TELEGRAM_BOT_TOKEN", "Channels", "Telegram bot token", "secret", "",
            apply="restart"),
    Setting("DISCORD_BOT_TOKEN", "Channels", "Discord bot token", "secret", "",
            apply="restart"),
    Setting("SLACK_APP_TOKEN", "Channels", "Slack app token", "secret", "", apply="restart"),
    Setting("WHATSAPP_TOKEN", "Channels", "WhatsApp token", "secret", "", apply="restart"),
    Setting("MIZAN_STT", "Channels", "Voice input (Sama')", "choice",
            "on lets people speak to MIZAN (the composer microphone and Telegram voice notes). "
            "Speech is turned into text on this server; the audio is kept nowhere.", "on",
            ("on", "off")),
    Setting("MIZAN_STT_MODEL_SIZE", "Channels", "Voice model size", "choice",
            "tiny is fastest; small hears Urdu, Hindi and Arabic best but needs about 500 MB "
            "of memory and more time. Downloaded once into the data volume.", "base",
            ("tiny", "base", "small")),
    Setting("MIZAN_STT_DAILY_SECONDS", "Channels", "Voice seconds per user per day", "int",
            "How many seconds of speech each non-admin user may send per day.", "1800",
            minimum=0),
)  # fmt: skip

BY_KEY = {item.key: item for item in SETTINGS}
_lock = threading.RLock()
_baseline: dict[str, str | None] = {}
_started: dict[str, str | None] = {}


@dataclass
class Change:
    applied: list[str] = field(default_factory=list)
    provider_changed: bool = False
    model_changed: bool = False
    restart_required: list[str] = field(default_factory=list)


def _path() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data")) / "runtime_settings.json"


def _read() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}
    values = data.get("values") if isinstance(data, dict) else None
    return {k: v for k, v in (values or {}).items() if k in BY_KEY and isinstance(v, dict)}


def _write(values: dict[str, dict[str, Any]]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"version": 1, "values": values}, handle, indent=1, sort_keys=True)
    os.replace(temporary, path)


def _seal(value: str) -> str:
    from connectors.secrets import seal

    return str(seal(value))


def _unseal(value: str) -> str:
    from connectors.secrets import unseal

    return str(unseal(value))


def normalize(setting: Setting, value: Any) -> str:
    """Validate an administrator's value; return its environment string."""
    if value is None:
        raise ValueError("A value is required")
    if setting.kind == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return "true"
        if text in {"0", "false", "no", "off"}:
            return "false"
        raise ValueError("Expected true or false")
    text = str(value).strip()
    if "\n" in text or "\r" in text or "\x00" in text or len(text) > 4000:
        raise ValueError("Value must be a single line")
    if not text:
        if setting.kind == "secret" or not setting.allow_empty:
            raise ValueError("Value cannot be empty; use reset instead")
        return ""
    if setting.kind == "choice":
        if text.lower() not in setting.choices:
            raise ValueError(f"Choose one of: {', '.join(setting.choices)}")
        return text.lower()
    if setting.kind in {"int", "float"}:
        try:
            number = float(text) if setting.kind == "float" else int(text)
        except ValueError:
            raise ValueError(
                f"Expected {'a number' if setting.kind == 'float' else 'an integer'}"
            ) from None
        if not math.isfinite(number):
            raise ValueError("Expected a finite number")
        if setting.minimum is not None and number < setting.minimum:
            raise ValueError(f"Minimum is {setting.minimum:g}")
        if setting.maximum is not None and number > setting.maximum:
            raise ValueError(f"Maximum is {setting.maximum:g}")
        return str(number)
    if setting.kind == "url" and not re.fullmatch(r"https?://[^\s/$.?#][^\s]*", text):
        raise ValueError("Expected an http(s) URL")
    if (
        setting.kind == "text"
        and setting.key == "DEFAULT_MODEL"
        and not re.fullmatch(r"[A-Za-z0-9._:/@+-]{1,200}", text)
    ):
        raise ValueError("Model IDs use letters, digits and . _ : / @ + -")
    return text


def apply_saved() -> None:
    """At startup: put saved values into the environment (they win over .env)."""
    with _lock:
        for key, entry in _read().items():
            _baseline.setdefault(key, os.environ.get(key))
            try:
                value = _unseal(entry["value"]) if entry.get("sealed") else str(entry["value"])
            except Exception:  # noqa: BLE001 - an unreadable secret must not stop startup
                continue
            os.environ[key] = value
        for setting in SETTINGS:
            _started.setdefault(setting.key, os.environ.get(setting.key))


def update(changes: dict[str, Any], actor: str) -> Change:
    """Validate every change, persist them together, then apply them."""
    unknown = sorted(set(changes) - BY_KEY.keys())
    if unknown:
        raise KeyError(", ".join(unknown))
    normalized: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    for key, value in changes.items():
        if value is None:
            normalized[key] = None
            continue
        try:
            normalized[key] = normalize(BY_KEY[key], value)
        except ValueError as exc:
            errors[key] = str(exc)
    if errors:
        raise ValueError(json.dumps(errors))
    result = Change()
    with _lock:
        saved = _read()
        for key, value in normalized.items():
            setting = BY_KEY[key]
            before = os.environ.get(key)
            _baseline.setdefault(key, before if key not in saved else _baseline.get(key))
            if value is None:
                saved.pop(key, None)
                original = _baseline.get(key)
                if original is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original
            else:
                saved[key] = {
                    "value": _seal(value) if setting.kind == "secret" else value,
                    "sealed": setting.kind == "secret",
                    "updated_at": time.time(),
                    "updated_by": actor,
                }
                os.environ[key] = value
            if os.environ.get(key) != before:
                result.applied.append(key)
                if setting.apply == "provider":
                    result.provider_changed = True
                    if key in {"LLM_PROVIDER", "DEFAULT_MODEL"}:
                        result.model_changed = True
        _write(saved)
    result.restart_required = restart_pending()
    return result


def restart_pending() -> list[str]:
    return [
        item.key
        for item in SETTINGS
        if item.apply == "restart" and os.environ.get(item.key) != _started.get(item.key)
    ]


def public_view() -> dict[str, Any]:
    saved = _read()
    pending = set(restart_pending())
    rows = []
    for setting in SETTINGS:
        current = os.environ.get(setting.key)
        source = (
            "admin" if setting.key in saved else "environment" if current is not None else "default"
        )
        row = asdict(setting)
        row["choices"] = list(setting.choices)
        row["source"] = source
        row["restart_pending"] = setting.key in pending
        if setting.kind == "secret":
            row["value"] = None
            row["is_set"] = bool(current)
        else:
            row["value"] = current if current is not None else setting.default
            row["is_set"] = current is not None
        entry = saved.get(setting.key)
        row["updated_at"] = entry.get("updated_at") if entry else None
        rows.append(row)
    groups = list(dict.fromkeys(item.group for item in SETTINGS))
    return {"groups": groups, "settings": rows, "restart_required": sorted(pending)}
