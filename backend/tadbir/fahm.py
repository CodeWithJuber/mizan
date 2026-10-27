"""Fahm (فهم): MIZAN's own understanding of a request.

Deterministic and inspectable: language from script and lexicon, intent from
recognizers that also extract what the plan needs (code, expression, Quran or
hadith reference, URL, search query). Nothing here calls a language model; requests
it cannot place confidently go back to the general agent loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import calc, hadith, project, quran, waqt

_HINGLISH = {
    "hai", "hain", "karo", "kro", "kya", "kyu", "kyun", "mein", "nahi", "nahin", "nhi",
    "bhai", "batao", "bata", "kaise", "kaisa", "mujhe", "tum", "tumhe", "tumhare", "aap",
    "apna", "aur", "yeh", "woh", "kar", "karke", "sakte", "sakta", "chahiye", "kitna",
    "kitne", "hota", "hoti", "dikhao", "sunao", "likho", "chalao", "padho", "samjhao",
    "matlab", "accha", "theek", "haan", "lekin", "bhi", "toh", "abhi", "phir", "kuch",
    "sab", "koi", "paas", "wala", "wali", "liye", "tarjuma", "karna", "karni", "hoga",
    "ka", "ki", "ke", "ko", "se", "ye", "ek", "banao", "bnao", "banaiye", "jisme", "jismein",
    "sakein", "sake", "jodo", "dena", "dijiye",
}  # fmt: skip
_URDU_LETTERS = set("ٹڈڑںےھہگپچژکی")
_RUN = r"(?:\brun\b|\bexecute\b|\bexec\b|\bchala\w*|\bchalao\b|चला|چلا|\bchalake\b)"
_CODE_WORDS = r"\b(?:python|code|script|program|javascript|node|bash|shell|function)\b"


@dataclass
class Understanding:
    intent: str
    language: str
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "language": self.language,
            "confidence": round(self.confidence, 2),
            "entities": {k: v for k, v in self.entities.items() if k != "code"},
        }


def _selected_project() -> str | None:
    """The coding project this chat is bound to, if any."""
    try:
        from workspace.context import bound_workspace_id
    except ImportError:  # pragma: no cover - the workspace package always ships
        return None
    selected = bound_workspace_id()
    return str(selected) if selected else None


def detect_language(text: str) -> str:
    arabic = re.findall(r"[؀-ۿ]", text)
    devanagari = re.findall(r"[ऀ-ॿ]", text)
    latin = re.findall(r"[A-Za-z]", text)
    if arabic and len(arabic) >= max(len(latin), len(devanagari)):
        return "ur" if any(ch in _URDU_LETTERS for ch in arabic) else "ar"
    if devanagari and len(devanagari) >= len(latin):
        return "hi"
    words = set(re.findall(r"[a-z]+", text.lower()))
    strong = words & (_HINGLISH - {"ka", "ki", "ke", "ko", "se", "ye", "toh", "bhi", "koi"})
    if len(strong) >= 2 or (len(strong) == 1 and (len(words & _HINGLISH) >= 2 or len(words) <= 6)):
        return "hi-latn"
    return "en"


def _fenced_code(text: str) -> tuple[str, str] | None:
    match = re.search(r"```[ \t]*([A-Za-z0-9+#-]*)[^\n]*\n(.*?)```", text, re.DOTALL)
    if not match or not match[2].strip():
        return None
    label = match[1].lower()
    language = {
        "py": "python", "python": "python", "python3": "python", "js": "javascript",
        "javascript": "javascript", "node": "javascript", "sh": "shell", "bash": "shell",
        "shell": "shell", "zsh": "shell",
    }.get(label)  # fmt: skip
    if language is None:
        language = "python" if re.search(r"\bprint\(|\bdef |\bimport ", match[2]) else ""
    return (match[2].strip("\n"), language) if language else None


_CAPABILITY = re.compile(
    r"\b(?:do you have|have you got|you have|any)\s+(?:any\s+)?(?:tools?|abilities|capabilit\w*)"
    r"|\bwhat can you do\b|\bwhat are your (?:tools|capabilities|abilities)\b"
    r"|\b(?:tools?|kya kya)\b[^?.!\n]{0,30}\b(?:hai|hain|he|kar sakte|kar sakta)\b"
    r"|\b(?:tumhare|aapke|tere)\s+paas\b[^?.!\n]{0,30}\btools?\b"
    r"|\bkya\s+kya\s+kar\s+sakte\b|\bkya\s+kar\s+sakte\s+ho\b"
    r"|کیا کر سکتے|کون سے ٹولز|क्या कर सकते",
    re.IGNORECASE,
)
_SEARCH = re.compile(
    r"\b(?:search|google|look\s+up|find\s+online|browse\s+for|khojo|dhundo|dhoondo|"
    r"search\s+karo|internet\s+(?:par|pe|se))\b|\blatest\b|\bnews\b|\btoday'?s\b|\baaj\s+ki\b",
    re.IGNORECASE,
)
_READ = re.compile(
    r"\b(?:read|summari[sz]e|summary|padho|padh\s*kar|kya\s+likha|explain\s+this\s+page|"
    r"open|kholo|dekho)\b",
    re.IGNORECASE,
)
_RECALL = re.compile(
    r"\bwhat did i (?:tell|say|share)\b|\bdo you remember\b|\bremember when\b|"
    r"\byaad\s+hai\b|\bmaine\s+(?:kya|jo)\s+(?:bataya|kaha)\b|یاد ہے|याद है",
    re.IGNORECASE,
)
_BUILD = re.compile(
    r"\b(?:write|create|make|build|likho|banao|bana\s*do)\b[^.\n]{0,60}"
    r"\b(?:program|script|code|function)\b"
    r"|\b(?:program|script|code|function)\b[^.\n]{0,80}\b(?:likho|banao|bana\s*do|likh\s*do)\b",
    re.IGNORECASE,
)
_COMPUTE_VERB = re.compile(
    r"\b(?:calculate|compute|solve|evaluate|kitna|kitne|kya\s+hai|what\s+is|how\s+much|"
    r"hisab|nikalo|batao|equals?)\b|=\s*\??\s*$|\?\s*$",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_EXPLAIN = re.compile(
    r"\b(?:tafsee?r|tafsir|explain|explanation|meaning|matlab|samjhao|sharh|sharah|tashreeh)\b"
    r"|تفسیر|تفسير|شرح|تشریح|व्याख्या|तशरीह",
    re.IGNORECASE,
)


def understand(text: str) -> Understanding:
    message = text.strip()
    language = detect_language(message)
    words = re.findall(r"\w+", message)

    if _CAPABILITY.search(message) and len(words) <= 25:
        return Understanding("capabilities", language, 0.9)

    explain = bool(_EXPLAIN.search(message))
    reference = quran.parse_reference(message)
    if reference is not None:
        return Understanding("quran", language, 0.95, {"reference": reference, "explain": explain})

    narration = hadith.parse_reference(message)
    if narration is not None:
        return Understanding("hadith", language, 0.95, {"reference": narration, "explain": explain})

    when = waqt.parse(message)
    if when is not None and len(words) <= 25:
        return Understanding("waqt", language, 0.9, {"request": when})

    fenced = _fenced_code(message)
    asks_run = bool(re.search(_RUN, message, re.IGNORECASE))
    if fenced and (asks_run or len(message) - len(fenced[0]) < 40):
        code, code_language = fenced
        return Understanding(
            "run_code", language, 0.9, {"code": code, "code_language": code_language}
        )

    expression = calc.find_expression(message)
    if expression:
        wants_python = asks_run and re.search(_CODE_WORDS, message, re.IGNORECASE)
        compact = re.sub(r"\s+", "", message)
        dominant = len(re.sub(r"\s+", "", expression)) >= 0.4 * max(1, len(compact))
        if wants_python:
            normalized = calc.normalize(expression)
            return Understanding(
                "run_code",
                language,
                0.9,
                {
                    "code": f"print({normalized})",
                    "code_language": "python",
                    "expression": expression,
                    "generated_by": "mizan",
                },
            )
        asked = re.search(re.escape(expression) + r"\s*(?:=\s*)?\?", message)
        if dominant or asked or _COMPUTE_VERB.search(message):
            return Understanding(
                "compute", language, 0.9 if dominant else 0.8, {"expression": expression}
            )

    url = _URL.search(message)
    if url and (_READ.search(message) or len(message) - len(url[0]) < 25):
        return Understanding("web_read", language, 0.85, {"url": url[0].rstrip(").,;")})

    if _BUILD.search(message) and asks_run:
        code_language = (
            "javascript" if re.search(r"\b(?:javascript|node|js)\b", message, re.I) else "python"
        )
        return Understanding(
            "build_and_run", language, 0.8, {"request": message, "code_language": code_language}
        )

    build = project.detect(message)
    if build is not None:
        return Understanding("build_project", language, 0.8, build)

    if _selected_project() and project.change_request(message):
        return Understanding("edit_project", language, 0.75, {"request": message})

    if _RECALL.search(message):
        return Understanding("recall", language, 0.8, {"query": message})

    if _SEARCH.search(message) and not url:
        query = _SEARCH.sub(" ", message)
        query = re.sub(
            r"\b(?:karo|kro|please|for|about|ke\s+baare\s+mein|par|pe|me|mein)\b",
            " ",
            query,
            flags=re.I,
        )
        query = re.sub(r"\s+", " ", query).strip(" ?.!,:")
        if len(query) >= 2:  # "latest AI news" leaves "AI"
            return Understanding("web_search", language, 0.75, {"query": message.strip()[:300]})

    return Understanding("converse", language, 0.0)


# Clause boundaries between independent requests ("Bukhari 1 aur Surah Ikhlas").
_CLAUSE = re.compile(
    r"\s*,?\s*\b(?:aur\s+phir|aur|and\s+then|and|then|phir|also)\b\s*|\s*[;\n]+\s*"
    r"|(?<!\S)(?:اور|और)(?!\S)",
    re.IGNORECASE,
)


def _clauses(text: str) -> list[str]:
    message = text.strip()
    if len(message) > 1000 or "```" in message or _URL.search(message):
        return []
    parts = [part.strip(" ,.?!؟") for part in _CLAUSE.split(message)]
    parts = [part for part in parts if part]
    return parts if 2 <= len(parts) <= 4 else []


def partly_understood(text: str) -> bool:
    """Several requests, some of which MIZAN's recognisers cannot place on their own."""
    understood = [understand(part) for part in _clauses(text)]
    known = [u for u in understood if u.intent not in {"converse", "capabilities"}]
    return (
        bool(known)
        and len(known) < len(understood)
        and any(
            u.intent == "converse" and actionable(part)
            for part, u in zip(_clauses(text), understood, strict=True)
        )
    )


def understand_parts(text: str) -> list[tuple[str, Understanding]] | None:
    """Two to four independent requests in one message, every one of them a recipe."""
    message = text.strip()
    parts = _clauses(message)
    if not parts:
        return None
    understood = [(part, understand(part)) for part in parts]
    if any(u.intent in {"converse", "capabilities"} for _part, u in understood):
        return None
    language = detect_language(message)
    for _part, u in understood:
        u.language = language
    return understood


_ACTION_CUES = re.compile(
    r"\d|https?://|\b(?:python|code|program|script|run|execute|calculate|compute|sum|total|"
    r"search|find|latest|news|quran|qur'an|surah|ayah|ayat|verse|fibonacci|prime|factorial|"
    r"kitna|kitne|nikalo|dhundo|khojo|chalao|hadith|hadees|hadis|bukhari|tirmidhi|nawawi|"
    r"app|website|game|banao|bana|build|create|date|tarikh|hijri|eid|show|list|get|fetch|send|"
    r"remember|save|open|check|dikhao|bhejo|rakho|repo|repos|issues?|email|mail|calendar|"
    r"event|file|files|note|notes|tasks?|reminder|connector|skill)\b"
    r"|سورة|سورہ|آیت|آية|حديث|حدیث|सूरह|आयत|हदीस",
    re.IGNORECASE,
)


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९", "0123456789" * 3)


def actionable(text: str) -> bool:
    """Worth asking Lisan to map the wording to an action (cheap pre-check)."""
    return bool(_ACTION_CUES.search(text)) and len(text) <= 2000


def validate_parsed(parsed: dict, message: str, language: str) -> Understanding | None:
    """MIZAN's checks on Lisan's proposed mapping; anything doubtful is rejected."""
    intent = parsed.get("intent")
    entities: dict[str, Any] = {"understood_by": "lisan"}
    if intent == "compute":
        expression = str(parsed.get("expression", ""))[:300]
        try:
            calc.evaluate(expression)
        except calc.CalcError:
            return None
        entities["expression"] = expression
    elif intent == "build_and_run":
        request = str(parsed.get("request", "")).strip()[:1500]
        code_language = parsed.get("language", "python")
        if len(request) < 8 or code_language not in {"python", "javascript"}:
            return None
        entities.update(
            request=f"{message}\n\n(Program to write: {request})", code_language=code_language
        )
    elif intent == "quran":
        try:
            surah = int(str(parsed.get("surah", "")))
            start = parsed.get("ayah_start")
            end = parsed.get("ayah_end") or start
            reference = quran._validated(
                surah, int(start) if start else None, int(end) if end else None
            )
        except (TypeError, ValueError):
            return None
        if reference is None:
            return None
        entities.update(reference=reference, explain=False)
    elif intent == "hadith":
        try:
            number = int(str(parsed.get("number", "")))
        except ValueError:
            return None
        # The number must be the user's own, never one the model supplied from
        # memory for a topic ("the hadith about intention").
        digits = re.findall(r"\d+", message.translate(_DIGITS))
        narration = hadith.validated(str(parsed.get("collection", "")), number)
        if narration is None or str(number) not in digits:
            return None
        entities.update(reference=narration, explain=bool(_EXPLAIN.search(message)))
    elif intent == "build_project":
        kind = parsed.get("kind", "web")
        if kind not in project.BLUEPRINTS or project.out_of_scope(message):
            return None
        entities.update(kind=kind, name=project.project_name(message))
    elif intent == "use_tool":
        need = str(parsed.get("need", "")).strip()[:200]
        if len(need) < 3:
            return None
        entities.update(need=need, request=message)
    elif intent == "edit_project":
        change = str(parsed.get("request", "")).strip()[:1500]
        if not _selected_project() or len(change) < 4:
            return None
        entities["request"] = f"{message}\n\n(Change: {change})"
    elif intent == "web_search":
        query = str(parsed.get("query", "")).strip()[:300]
        if len(query) < 3:
            return None
        entities["query"] = query
    elif intent == "web_read":
        url = str(parsed.get("url", "")).strip()
        # Only a link the user actually wrote, never one the model invented.
        if not _URL.fullmatch(url) or url not in message:
            return None
        entities["url"] = url
    else:
        return None
    return Understanding(str(intent), language, 0.6, entities)
