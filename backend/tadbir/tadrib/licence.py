"""Which teachers' output MIZAN's own student may learn from (docs/tadrib.md).

The owner's decisions (31 Oct 2026): never Anthropic or OpenAI output, only a
model whose licence allows training on what it writes, and only output one of
MIZAN's checks passed. The rules are the ones ``mizan_reply.data`` enforces for
its records (``TEACHER_LICENCES``, ``FORBIDDEN_TEACHERS``; its copies are kept
equal by a test, since that module needs torch).

A teacher is known by the model id the provider says served the call. Each id
on record names its licence, the card it was read from and when; an id not on
record teaches nothing, and so does a distillation of a forbidden vendor's
model.
"""

from __future__ import annotations

TEACHER_LICENCES = frozenset(
    {"apache-2.0", "mit", "deepseek-terms-of-use", "deepseek-model-license"}
)
FORBIDDEN_TEACHERS = frozenset({"anthropic", "openai"})

# model id (as OpenRouter names it) -> its licence, where it was read, when
TEACHERS: dict[str, dict[str, str]] = {
    "deepseek/deepseek-chat-v3-0324": {
        "licence": "mit",
        "card": "https://huggingface.co/deepseek-ai/DeepSeek-V3-0324",
        "read": "2026-10-31",
    },
}


def _vendor(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else ""


def forbidden(model: str) -> bool:
    model = model.strip().lower()
    return (
        _vendor(model) in FORBIDDEN_TEACHERS
        or "claude" in model
        or model.startswith(("gpt-", "o1", "o3", "o4"))
        or "distill" in model
    )


def licence_of(model: str) -> str | None:
    """The licence on record for this teacher, or None when it may not teach."""
    model = model.strip().lower()
    if not model or forbidden(model):
        return None
    found = TEACHERS.get(model)
    if found is None or found["licence"] not in TEACHER_LICENCES:
        return None
    return found["licence"]


def allowed(model: str) -> bool:
    return licence_of(model) is not None
