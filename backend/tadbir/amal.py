"""Amal (عمل): MIZAN runs any permitted tool itself.

For work no recipe covers (a connector, a skill, memory, a project action),
MIZAN chooses the tool. It ranks the user's permitted tools by BM25 between
the need and each tool's name and description, and weights each by that
tool's posterior reliability from earlier receipts. Lisan only fills in the
arguments from the request. MIZAN validates them against the tool's JSON
Schema before the tool runs through the agent's gate (Fitrah, Izn,
approvals). Host-level tools (shell, raw files, raw HTTP, Python on the
host) are never chosen; MIZAN works through its sandboxed and gated tools.
"""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, validators

from core.adaptive import bm25_scores, tokenize

# Native tools MIZAN may choose; every other native tool is host-level or
# internal to the model loop.
SAFE_NATIVE = {
    "recall_memory",
    "query_knowledge",
    "activate_skill",
    "read_skill_file",
    "disambiguate_sense",
}


def candidates(agent: Any, allowed: Any) -> list[dict]:
    """The tools MIZAN may choose for this user, with their schemas."""
    native = set(getattr(agent, "tools", {}) or {})
    found = []
    for schema in agent.get_tool_schemas():
        name = str(schema.get("name", ""))
        if not name or (name in native and name not in SAFE_NATIVE):
            continue
        if allowed(name):
            found.append(schema)
    return found


# Words that say nothing about which tool is meant.
_GENERIC = {
    "the", "and", "for", "with", "from", "into", "find", "get", "show", "give", "take", "make",
    "time", "learn", "can", "you", "please", "all", "some", "use", "help", "this", "that",
    "what", "how", "want", "need", "try", "kar", "karo", "batao", "dikhao", "mere", "mera",
}  # fmt: skip


def stem(word: str) -> str:
    """A light English suffix fold, so "issues"/"issue" and "listing"/"list" meet:
    plural -ies/-es/-s, -ing and -ed (never below three letters)."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
        return word[:-1] if len(word) > 3 and word[-1] == word[-2] else word
    if len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
        return word[:-1] if len(word) > 3 and word[-1] == word[-2] else word
    return word


def _terms(text: str) -> list[str]:
    return [stem(word) for word in tokenize(text)]


def _name_words(name: str) -> str:
    """A tool's own name as words (``mcp__github__list_issues`` → github list issues)."""
    parts = name.split("__")
    core = parts[2:] if name.startswith("mcp__") and len(parts) > 2 else parts
    words = " ".join(core).replace("_", " ").replace("-", " ")
    server = parts[1].replace("_", " ") if name.startswith("mcp__") and len(parts) > 1 else ""
    return f"{server} {words}".strip()


def choose(agent: Any, tools: list[dict], need: str, request: str) -> dict | None:
    """MIZAN's choice: relevance to the need, weighted by the tool's reliability.

    Words are compared after a light suffix fold (``stem``), and a tool's own name
    counts twice, so "list my issues" meets ``list_issues``. A tool must share at
    least two of the need's meaningful words (one when the need has only one), so a
    vague request is never matched to an unrelated tool.
    """
    if not tools:
        return None
    documents = [
        _terms(
            f"{_name_words(tool['name'])} {_name_words(tool['name'])} {tool.get('description', '')}"
        )
        for tool in tools
    ]
    meaningful = {stem(word) for word in tokenize(need) if len(word) > 2 and word not in _GENERIC}
    required = min(2, len(meaningful))
    scores = bm25_scores(_terms(f"{need} {need} {request}"), documents)
    best, best_score = None, 0.0
    for tool, document, score in zip(tools, documents, scores, strict=True):
        if score <= 0 or not required or len(meaningful & set(document)) < required:
            continue
        try:
            reliability = agent.adaptive.beta(f"tool:{tool['name']}", forgetting=0.98).mean
        except Exception:  # noqa: BLE001 - no store: relevance alone decides
            reliability = 0.5
        weighted = score * (0.5 + 0.5 * reliability)
        if weighted > best_score:
            best, best_score = tool, weighted
    return best


def restrict(arguments: Any, schema: dict | None) -> Any:
    """Only the arguments the tool declares: Lisan's extra fields never reach a tool."""
    if not isinstance(arguments, dict) or not isinstance(schema, dict):
        return arguments
    declared = schema.get("properties")
    if not isinstance(declared, dict):
        return arguments
    return {key: value for key, value in arguments.items() if key in declared}


def problems(arguments: Any, schema: dict | None) -> list[str]:
    """Why these arguments do not fit the tool's JSON Schema (empty when they do)."""
    if not isinstance(arguments, dict):
        return ["the arguments must be a JSON object"]
    if not isinstance(schema, dict) or not schema:
        return []
    cls = validators.validator_for(schema, default=Draft202012Validator)
    try:
        cls.check_schema(schema)
    except SchemaError:
        return []  # the tool's own schema is malformed: its gate still validates
    found = sorted(cls(schema).iter_errors(arguments), key=lambda error: list(error.path))
    return [
        f"{'/'.join(str(part) for part in error.path) or '(root)'}: {error.message}"
        for error in found[:8]
    ]


def facts(name: str, arguments: dict, result: Any) -> dict:
    text = json.dumps(result, ensure_ascii=False, default=str)
    return {"tool": name, "arguments": arguments, "result": text[:6000]}
