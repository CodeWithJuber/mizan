"""Fahm (فهم): MIZAN's own understanding of a request.

Understanding is weighed, not matched by hand-written cues:

- the **language** is the posterior of Lughah (``lughah.py``), a naive Bayes
  model over letters and letter sequences, with the chat's earlier messages
  as its prior;
- the **intent** is the posterior of Qasd (``qasd.py``), a naive Bayes model
  over the request's words and over what MIZAN's parsers find in it, fitted
  on examples and on MIZAN's own verified work.

Parsing stays exact, because it is reading, not guessing: a Quran or hadith
reference, a calculation, a date, a link, a file name, a code block, a grid
puzzle and a schedule are each read by a grammar, and those findings are the
evidence Qasd weighs. MIZAN then takes the intents in order of probability and
plans the first whose details it can build from the message. When
conversation is more probable than every buildable action, it answers in
words. Nothing here calls a language model.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from . import amanah, calc, hadith, lughah, project, qasd, qiyas, quran, silsila, waqt


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
            "entities": {k: v for k, v in self.entities.items() if k not in {"code", "puzzle"}},
        }


def _selected_project() -> str | None:
    """The coding project this chat is bound to, if any."""
    try:
        from workspace.context import bound_workspace_id
    except ImportError:  # pragma: no cover - the workspace package always ships
        return None
    selected = bound_workspace_id()
    return str(selected) if selected else None


def _user_texts(history: list[dict] | None) -> list[str]:
    return [
        str(turn.get("content") or "")
        for turn in (history or [])[-12:]
        if turn.get("role") == "user" and str(turn.get("content") or "").strip()
    ]


def detect_language(text: str, history: list[dict] | None = None) -> str:
    return lughah.language(text, prior=_user_texts(history))


# ── grammars: exact readers whose findings are evidence ─────────────────

_CODE_LABELS = {
    "py": "python", "python": "python", "python3": "python", "js": "javascript",
    "javascript": "javascript", "node": "javascript", "sh": "shell", "bash": "shell",
    "shell": "shell", "zsh": "shell",
}  # fmt: skip


_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9+#-]*)[^\n]*\n(.*?)```", re.DOTALL)


def _runnable(match: re.Match) -> tuple[str, str] | None:
    if not match[2].strip():
        return None
    language = _CODE_LABELS.get(match[1].lower())
    if language is None:
        language = "python" if re.search(r"\bprint\(|\bdef |\bimport ", match[2]) else ""
    return (match[2].strip("\n"), language) if language else None


def _fenced_code(text: str) -> tuple[str, str] | None:
    match = _FENCE.search(text)
    return _runnable(match) if match else None


def fenced_programs(text: str) -> list[tuple[str, str]]:
    """Every fenced block in the text that MIZAN can run, with its language."""
    return [found for match in _FENCE.finditer(text) if (found := _runnable(match))]


_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# A file in the selected project, named in the user's words (`sales.csv`, app.log).
_FILE_NAME = re.compile(
    r"(?<![\w/.-])`?([A-Za-z0-9_][\w./-]{0,120}\.(?:py|js|mjs|cjs|sh|csv|tsv|json|jsonl|log|txt|"
    r"md|xml|ya?ml|ini|toml|html|css))`?(?![\w-])",
    re.IGNORECASE,
)
_DATA_FILE = re.compile(r"\.(?:csv|tsv|json|jsonl|log|xml)$", re.IGNORECASE)
_RUNNABLE = re.compile(r"\.(?:py|js|mjs|cjs|sh)$", re.IGNORECASE)
_JAVASCRIPT = re.compile(r"\b(?:javascript|node|js)\b", re.IGNORECASE)


def _own_words(message: str) -> str:
    """The message without pasted material (a region that is only a link stays)."""
    own = _IMAGE.sub(" ", message)
    for region in amanah.pasted(message):
        if not _URL.fullmatch(region.strip().rstrip(".,;)")):
            own = own.replace(region, " ")
    return own


def named_files(message: str) -> list[str]:
    """File names the user wrote in their own words (links removed), in order."""
    own = _URL.sub(" ", _own_words(message))
    seen: list[str] = []
    for name in _FILE_NAME.findall(own):
        name = name.strip("`./")
        if name and name not in seen:
            seen.append(name)
    return seen[:12]


def plain_words(message: str) -> str:
    """The user's words, without code blocks, links and file names (those are evidence)."""
    text = re.sub(r"```.*?(?:```|$)", " ", message or "", flags=re.DOTALL)
    text = _FILE_NAME.sub(" ", _URL.sub(" ", _IMAGE.sub(" ", text)))
    return text


def evidence(message: str) -> list[str]:
    """What MIZAN's parsers find in a message, as tokens for Qasd to weigh."""
    from knowledge import hf_hub

    found: list[str] = []
    if quran.parse_reference(message) is not None:
        found.append("qref")
    if hadith.parse_reference(message) is not None:
        found.append("href")
    if waqt.parse(message) is not None:
        found.append("date")
    if qiyas.parse(message) is not None:
        found.append("grid")
    if silsila._run_of_numbers(message) is not None:
        found.append("seq")
    if _fenced_code(message) is not None:
        found.append("code")
    expression = calc.find_expression(message)
    if expression:
        found.append("expr")
        # How much of the message the calculation is, in quarters (expr0 … expr4).
        share = len(re.sub(r"\s+", "", expression)) / (len(re.sub(r"\s+", "", message)) or 1)
        found.append(f"expr{round(4 * share)}")
    own = _own_words(message)
    if _URL.search(own):
        found.append("hf" if hf_hub.parse_link(own) is not None else "url")
    for name in named_files(message):
        found.append(
            "datafile"
            if _DATA_FILE.search(name)
            else "runfile"
            if _RUNNABLE.search(name)
            else "file"
        )
    if amanah.pasted(message):
        found.append("pasted")
    if _trigger(message) is not None:
        found.append("schedule")
    if _prayer_named(message):
        found.append("prayer")
    words = len(re.findall(r"\w+", message))
    found.append(f"len{words.bit_length()}")  # length on a log₂ scale
    return found


# ── schedules (Muraqabah): time grammar ─────────────────────────────────

_SEND = re.compile(
    r"\b(?:bhej(?:o|na|iye|en|a\s+karo)|send|remind|yaad\s+dila(?:o|na|iye|ya\s+karo)|"
    r"bata(?:o|na|iye|ya\s+karo)|notify|alert|message\s+karo)\b",
    re.IGNORECASE,
)
_PRAYER_NAMES = {
    "fajr": "fajr", "fajar": "fajr", "zuhr": "dhuhr", "zohar": "dhuhr", "zuhar": "dhuhr",
    "dhuhr": "dhuhr", "duhr": "dhuhr", "asr": "asr", "asar": "asr", "maghrib": "maghrib",
    "magrib": "maghrib", "isha": "isha", "esha": "isha", "ishaa": "isha",
}  # fmt: skip
_FAST_TIMES = {"sehri": "fajr", "sahri": "fajr", "suhoor": "fajr", "iftar": "maghrib",
               "iftari": "maghrib"}  # fmt: skip
_PRAYER = r"(fajr|fajar|zuhr|zohar|zuhar|dhuhr|duhr|asr|asar|maghrib|magrib|isha|esha|ishaa)"
_MINUTES = r"(?:\d{1,3}\s*(?:min|mins|minute|minutes|mint|minat)\s*)?"
_RELATIVE = re.compile(
    _PRAYER
    + r"(?:\s+(?:ki\s+)?(?:namaz|namaaz|salah|salat|prayer))?\s*(?:ke|ki|se)?\s*"
    + _MINUTES
    + r"(baad|bad|after|pehle|before)|\b"
    + _MINUTES
    + r"(after|before)\s+"
    + _PRAYER,
    re.IGNORECASE,
)
_EVENING = re.compile(r"\b(?:shaam|sham|evening|raat|night)\b", re.IGNORECASE)
_FILLER = re.compile(r"^(?:mujhe|mujhko|me|please|plz|zara|ek|aur)\b\s*", re.IGNORECASE)
_EVERY = re.compile(
    r"\b(?:har\s+(?:roz|din|subah|shaam|sham|raat)|every\s+(?:day|morning|evening|night)|"
    r"daily|rozana|roz)\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|baje)\b", re.IGNORECASE)
_OFFSET = re.compile(r"\b(\d{1,3})\s*(?:min|mins|minute|minutes|mint|minat)\b", re.IGNORECASE)
_AYAH_WORD = re.compile(r"\b(?:ayat|ayah|aayat|verse)\b|آیت|آية|आयत", re.IGNORECASE)
_REMINDER = re.compile(
    r"\bremind\s+me\s+(?:to|about|of)\s+(.+)|(?:^|\s)(.+?)\s+(?:ka|ki|ke)?\s*yaad\s+dila",
    re.IGNORECASE,
)


def _prayer_named(message: str) -> str | None:
    for word in re.findall(r"[a-z]+", message.lower()):
        if word in _PRAYER_NAMES:
            return _PRAYER_NAMES[word]
        if word in _FAST_TIMES:
            return _FAST_TIMES[word]
    return None


def _trigger(message: str) -> dict | None:
    """When a standing request fires: around a prayer, or daily at a clock time."""
    relative = _RELATIVE.search(message)
    if relative:
        name = (relative.group(1) or relative.group(4) or "").lower()
        direction = (relative.group(2) or relative.group(3) or "").lower()
        before = direction in {"pehle", "before"}
        offset = _OFFSET.search(message)
        minutes = int(offset.group(1)) if offset else (30 if before else 20)
        return {"kind": "prayer", "prayer": _PRAYER_NAMES[name],
                "offset": -minutes if before else minutes}  # fmt: skip
    clock = _CLOCK.search(message)
    if clock and _EVERY.search(message):
        hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
        meridiem = clock.group(3).lower().replace(".", "")
        if (meridiem == "pm" or (meridiem == "baje" and _EVENING.search(message))) and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            return None
        return {"kind": "daily", "time": f"{hour:02d}:{minute:02d}"}
    return None


def watch_request(message: str) -> dict | None:
    """The schedule and task of a standing request, when the message has a schedule."""
    trigger = _trigger(message)
    if trigger is None:
        return None
    if _AYAH_WORD.search(message) and quran.parse_reference(message) is None:
        return {"trigger": trigger, "task": "ayah_of_the_day", "title": "Ayah of the day"}
    reminder = _REMINDER.search(message)
    if reminder:
        what = _bare((reminder.group(1) or reminder.group(2) or "").strip(" .!?"))
        if what:
            return {
                "trigger": trigger,
                "task": f"remind:{what[:300]}",
                "title": f"Reminder: {what[:60]}",
            }
    what = _bare(_SEND.sub(" ", message))
    if not what:
        return None
    # Anything else is a request MIZAN runs each time, in the user's own words.
    return {"trigger": trigger, "task": what[:300], "title": what[:60]}


def _bare(text: str) -> str:
    """The thing asked for, without its schedule and filler words."""
    text = _RELATIVE.sub(" ", _CLOCK.sub(" ", _EVERY.sub(" ", _OFFSET.sub(" ", text))))
    text = re.sub(r"\s+", " ", text).strip(" ,.!?")
    for _ in range(3):
        text = _FILLER.sub("", text).strip(" ,.!?")
    return text


# ── Hugging Face ────────────────────────────────────────────────────────


_HUB_NAME = re.compile(r"hugging\s*face|huggingface|\bhf\b", re.IGNORECASE)  # the platform's name


def hub_request(message: str) -> dict | None:
    """List an account, inspect a repository, or import a file the user names."""
    from knowledge import hf_hub

    own = _own_words(message)
    link = hf_hub.parse_link(own)
    kinds = [kind for kind in ("datasets", "models", "spaces")
             if re.search(kind[:-1], message, re.IGNORECASE)] or ["datasets", "models"]  # fmt: skip
    if re.search(r"\btrain", message, re.IGNORECASE) and "models" not in kinds:
        kinds.append("models")  # "datasets / training": the trained models too
    if link is None:
        # Without a link, the request must name the platform it is about.
        if not _HUB_NAME.search(own):
            return None
        return {"action": "repos", "owner": "", "kinds": kinds}
    if "owner" in link:
        return {"action": "repos", "owner": link["owner"], "kinds": kinds}
    named = [name for name in named_files(own) if "." in name]
    path = link.get("path") or (named[0] if named else None)
    entities = {"repo": link["repo"], "kind": link["kind"], "revision": link["revision"]}
    if path:
        return {"action": "import", "path": path, **entities}
    return {"action": "files", **entities}


# ── building each intent's plan from the message ────────────────────────


def _quran(intent: str, message: str, language: str) -> Understanding | None:
    reference = quran.parse_reference(message)
    if reference is None:
        return None
    return Understanding(
        "quran",
        language,
        0.0,
        {
            "reference": reference,
            "explain": intent == "quran_explain",
            "question": intent == "quran_question",
        },
    )


def _quran_search(_intent: str, message: str, language: str) -> Understanding | None:
    # A message that names a reference is read by the reference recipe instead.
    if quran.parse_reference(message) is not None:
        return None
    return Understanding("quran_search", language, 0.0, {"query": message})


def _hadith(intent: str, message: str, language: str) -> Understanding | None:
    narration = hadith.parse_reference(message)
    if narration is None:
        return None
    explain = intent == "hadith_explain"
    return Understanding("hadith", language, 0.0, {"reference": narration, "explain": explain})


def _run_code(_intent: str, message: str, language: str) -> Understanding | None:
    fenced = _fenced_code(message)
    if fenced:
        code, code_language = fenced
        return Understanding(
            "run_code", language, 0.0, {"code": code, "code_language": code_language}
        )
    expression = calc.find_expression(message)
    if not expression:
        return None
    return Understanding(
        "run_code",
        language,
        0.0,
        {
            "code": f"print({calc.normalize(expression)})",
            "code_language": "python",
            "expression": expression,
            "generated_by": "mizan",
        },
    )


def _in_project(intent: str, message: str, language: str) -> Understanding | None:
    if not _selected_project():
        return None
    names = named_files(message)
    if intent == "run_file":
        runnable = [name for name in names if _RUNNABLE.search(name)]
        return Understanding("run_file", language, 0.0, {"path": runnable[0]}) if runnable else None
    if intent == "project_task":
        if not any(_DATA_FILE.search(name) for name in names):
            return None
        return Understanding("project_task", language, 0.0, {"request": message, "files": names})
    return Understanding("edit_project", language, 0.0, {"request": message})


def _web_read(_intent: str, message: str, language: str) -> Understanding | None:
    # Only a link in the user's own words is read; a link inside pasted text or
    # a Markdown image is material (and may be a way to send data out).
    own = _own_words(message)
    url = _URL.search(own)
    if not url:
        return None
    # Every link in the user's own words, in order: when one page is gone,
    # MIZAN reads the next one the user gave.
    urls = list(dict.fromkeys(found.rstrip(").,;") for found in _URL.findall(own)))[:4]
    return Understanding("web_read", language, 0.0, {"url": url[0].rstrip(").,;"), "urls": urls})


def _browse(_intent: str, message: str, language: str) -> Understanding | None:
    """Use a page in MIZAN's browser sandbox (Shahid): the sites are the hosts of
    the links in the user's own words, never of a link inside pasted text."""
    own = _own_words(message)
    urls = list(dict.fromkeys(found.rstrip(").,;") for found in _URL.findall(own)))[:4]
    if not urls:
        return None
    from . import shahid

    origins = shahid.origins_from(urls)
    if not origins or not shahid.available():
        return None
    return Understanding(
        "browse", language, 0.0, {"url": shahid.https(urls[0]), "urls": urls, "origins": origins}
    )


def _sequence(message: str) -> dict | None:
    """The terms a sequence question gives: with one missing inside it, the
    known terms at their positions; otherwise the run of numbers."""
    missing = silsila.with_gap(message)
    if missing is not None:
        seq, positions, gap = missing
        return {"sequence": seq, "positions": positions, "gap": gap}
    found = silsila._run_of_numbers(message)
    return None if found is None else {"sequence": found}


def _simple(intent: str, entities: dict | None = None):
    def build(_intent: str, message: str, language: str) -> Understanding | None:
        return Understanding(intent, language, 0.0, dict(entities or {}))

    return build


def _with(intent: str, read):
    def build(_intent: str, message: str, language: str) -> Understanding | None:
        found = read(message)
        return None if found is None else Understanding(intent, language, 0.0, found)

    return build


_BUILDERS = {
    "capabilities": _simple("capabilities"),
    "watch": _with("watch", watch_request),
    "salah": _with("salah", lambda m: {"prayer": _prayer_named(m)}),
    "quran": _quran,
    "quran_question": _quran,
    "quran_explain": _quran,
    "quran_search": _quran_search,
    "hadith": _hadith,
    "hadith_explain": _hadith,
    "waqt": _with(
        "waqt", lambda m: (lambda w: None if w is None else {"request": w})(waqt.parse(m))
    ),
    "qiyas": _with(
        "qiyas", lambda m: (lambda p: None if p is None else {"puzzle": p})(qiyas.parse(m))
    ),
    "silsila": _with("silsila", lambda m: _sequence(m)),
    # "Karo koshish": about a sequence asked earlier; Tadbir takes it from the chat.
    "silsila_follow": _with(
        "silsila_follow",
        lambda m: (
            None if silsila._run_of_numbers(m) is not None else {"harder": qasd.facet("harder", m)}
        ),
    ),
    "run_code": _run_code,
    # "?", "Jawab nahi aaya": the request before this one went unanswered;
    # Tadbir takes it from the chat.
    "again_follow": _simple("again_follow"),
    # "Run this code": a program shown earlier in the chat; Tadbir takes it from there.
    "run_follow": _with("run_follow", lambda m: None if _fenced_code(m) else {}),
    "run_file": _in_project,
    "project_task": _in_project,
    "edit_project": _in_project,
    "compute": _with(
        "compute",
        lambda m: (lambda e: {"expression": e, "explain": qasd.facet("explain", m)} if e else None)(
            calc.find_expression(m)
        ),
    ),
    "hf_hub": _with("hf_hub", hub_request),
    "web_read": _web_read,
    "browse": _browse,
    "build_and_run": _with(
        "build_and_run",
        lambda m: {
            "request": m,
            "code_language": "javascript" if _JAVASCRIPT.search(m) else "python",
        },
    ),
    "build_project": _with("build_project", project.blueprint),
    "recall": _with("recall", lambda m: {"query": m}),
    # "Yaad rakhna ki ...": the user's own words are kept as they are.
    "remember": _with("remember", lambda m: {"note": m.strip()[:2000]} if m.strip() else None),
    "web_search": _with("web_search", lambda m: {"query": m.strip()[:300]}),
    # "Dhundo pahle": a search with no topic of its own; Tadbir takes the topic from the chat.
    "search_bare": _simple("search_bare"),
}


def understand(text: str, history: list[dict] | None = None, overlay: Any = None) -> Understanding:
    message = text.strip()
    language = detect_language(message, history)
    # The chat so far is the prior: in a conversation, a message that reads only
    # a little like a request stays conversation (qasd.prior).
    earlier = qasd.earlier_messages(history)
    project = bool(_selected_project())
    ranked = qasd.ranked(message, project=project, overlay=overlay, earlier=earlier)
    # MAP first over families of recipes (a request to make something is one
    # family whether it builds or edits), conversation, and "an action MIZAN
    # could not build from these words" (the mass of the families that failed;
    # that goes on as conversation, where Lisan may map the wording). Within the
    # chosen family, the most probable intent MIZAN can build is the plan.
    unbuilt = 0.0
    # The actions that outranked conversation and had evidence, but that MIZAN
    # could not build from these words: Lisan may map those (``actionable``).
    mappable = 0.0
    before = _families(
        sorted(qasd.prior(project, overlay, earlier).items(), key=lambda item: -item[1])
    )
    baseline = {family: mass for family, mass, _members in before}
    families = _families(ranked)
    for family, mass, members in families:
        if family == "converse" or unbuilt > mass:
            break
        if mass <= baseline.get(family, 0.0):
            # The words did not make this kind of request any more likely than
            # it was before reading them ("?"): no evidence to act on.
            continue
        if mass <= 0.5:
            # Not decisive: MIZAN acts on a kind of request only when it is more
            # probable than every other reading together. Below that it does not
            # guess an action from the likeliest crumb ("Garbage area 👇 कुलडी"
            # is not a website request because "website" is its likeliest single
            # reading); Lisan may read the wording (``actionable``). A fixed
            # answer reads nothing in the message ("Tum pagal ho?" is not a
            # question about tools), so it is never mapped.
            unbuilt += mass
            if family not in FIXED_ANSWERS:
                mappable += sum(p for intent, p in members if intent not in _WORDS_ONLY)
            continue
        for intent, _probability in members:
            build = _BUILDERS.get(intent)
            built: Understanding | None = build(intent, message, language) if build else None
            if built is not None:
                built.confidence = mass
                return built
        unbuilt += mass
        mappable += sum(p for intent, p in members if intent not in _WORDS_ONLY)
    conversation = next((mass for family, mass, _m in families if family == "converse"), 0.0)
    # The root or wazn of an Arabic word: answered from the Quranic Arabic
    # Corpus (Sarf), the analyzer /api/v1/root-analyze uses, never from the
    # model. A yes/no facet learned from seeds; asked only when no request
    # above was decisive.
    targets = sarf_targets(message)
    if targets and qasd.facet("sarf", message):
        return Understanding(
            "sarf", language, qasd.facet_model("sarf").posterior(message)["yes"], {"words": targets}
        )
    return Understanding(
        "converse",
        language,
        0.0,
        {"posterior": dict(ranked[:3]), "mappable": mappable, "conversation": conversation},
    )


@cache
def _sarf_frame() -> frozenset[str]:
    """The Arabic words of the question's own frame (ما، جذر، كلمة، وزن), learned
    from the seeds: those that appear in more than one of them."""
    from . import sarf

    counts: dict[str, int] = {}
    for text, label in qasd.facet_examples("sarf"):
        if label == "yes":
            for word in {sarf.fold(w) for w in sarf.words(text)}:
                counts[word] = counts.get(word, 0) + 1
    return frozenset(word for word, count in counts.items() if count > 1)


def sarf_targets(message: str) -> list[str]:
    """The Arabic words a root question asks about (at most six)."""
    from . import sarf

    found = sarf.words(message)
    asked = [word for word in found if sarf.fold(word) not in _sarf_frame()]
    return (asked or found[-1:])[:6]


# Families of recipes: intents that are kinds of one request.
FAMILIES = {
    "quran": ("quran", "quran_question", "quran_explain", "quran_search"),
    "hadith": ("hadith", "hadith_explain"),
    "search": ("web_search", "search_bare"),
    "sequence": ("silsila", "silsila_follow"),
    "code": ("run_code", "build_and_run", "run_file", "run_follow"),
    "make": ("build_project", "edit_project", "project_task"),
    "page": ("web_read", "browse"),
}
_FAMILY = {intent: family for family, members in FAMILIES.items() for intent in members}
# Recipes whose answer is the same whatever the message says.
FIXED_ANSWERS = frozenset({"capabilities"})


def _families(ranked: list[tuple[str, float]]) -> list[tuple[str, float, list[tuple[str, float]]]]:
    """The posterior summed by family, most probable first, each with its members."""
    grouped: dict[str, list[tuple[str, float]]] = {}
    for intent, probability in ranked:
        grouped.setdefault(_FAMILY.get(intent, intent), []).append((intent, probability))
    found = [(family, sum(p for _i, p in members), members) for family, members in grouped.items()]
    return sorted(found, key=lambda item: -item[1])


def bare_search(text: str) -> bool:
    """A search request with no topic of its own ("Dhundo pahle", "search it"):
    the most probable intent of the message is a topicless search."""
    ranked = qasd.ranked(text or "", project=bool(_selected_project()))
    return bool(ranked) and ranked[0][0] == "search_bare"


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


_WORDS_ONLY = {
    "converse",
    "capabilities",
    "silsila_follow",
    "search_bare",
    "run_follow",
    "again_follow",
}


def _decisive_action(text: str) -> str | None:
    """The family of action a clause asks for, when Qasd finds that family more
    probable than all the alternatives together (P > ½); otherwise None."""
    families = _families(qasd.ranked(text, project=bool(_selected_project())))
    if families and families[0][0] != "converse" and families[0][1] > 0.5:
        return families[0][0]
    return None


def partly_understood(text: str, whole: Understanding | None = None) -> bool:
    """Several requests, some of which MIZAN's recognisers cannot place on their own.

    A clause MIZAN cannot place counts only when it is decisively an action of
    its own (its top action has P > ½) and not the action the whole message was
    understood as ("…program likho … aur run karo" is one request; "twelve
    squared, then Bukhari 1" is two)."""
    clauses = _clauses(text)
    understood = [understand(part) for part in clauses]
    known = [u for u in understood if u.intent not in _WORDS_ONLY]
    whole_intent = _FAMILY.get(whole.intent, whole.intent) if whole is not None else None
    return (
        bool(known)
        and len(known) < len(understood)
        and any(
            u.intent == "converse"
            and (action := _decisive_action(part)) is not None
            and action != whole_intent
            for part, u in zip(clauses, understood, strict=True)
        )
    )


def _covers(whole: Understanding, part: Understanding) -> bool:
    """The whole message's plan already holds everything this part asks for:
    the same kind of recipe, and each of the part's entities contained in the
    whole's (a clause within the whole request, the same reference)."""
    if _FAMILY.get(whole.intent, whole.intent) != _FAMILY.get(part.intent, part.intent):
        return False
    for key, value in part.entities.items():
        held = whole.entities.get(key)
        if isinstance(value, str) and isinstance(held, str):
            if value.strip().casefold() not in held.casefold():
                return False
        elif held != value:
            return False
    return True


def understand_parts(text: str) -> list[tuple[str, Understanding]] | None:
    """Two to four independent requests in one message, every one of them a recipe."""
    message = text.strip()
    parts = _clauses(message)
    if not parts:
        return None
    understood = [(part, understand(part)) for part in parts]
    if any(u.intent in _WORDS_ONLY for _part, u in understood):
        return None
    # One request or several? The simpler explanation wins:
    # - when one plan for the whole message already holds what every part asks
    #   for, it is one request ("write a function that … and returns …": the
    #   program's request is the whole text; "Bukhari 1 and Bukhari 2" is two,
    #   because one plan holds only one reference);
    # - when the parts are different actions, the split is kept only if it
    #   explains the message better than the whole does: the joint probability
    #   of the parts against the whole message's probability ("Every morning
    #   after Fajr send an ayah and the Hijri date" is one watcher).
    whole = understand(message)
    if whole.intent not in _WORDS_ONLY:
        if all(_covers(whole, u) for _part, u in understood):
            return None
        joint = math.prod(u.confidence for _part, u in understood)
        if len({u.intent for _part, u in understood}) > 1 and whole.confidence >= joint:
            return None
    language = detect_language(message)
    for _part, u in understood:
        u.language = language
    return understood


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९", "0123456789" * 3)


def actionable(understanding: Understanding) -> bool:
    """MIZAN finds an action more probable than conversation, but could not build it.

    Only the kinds of request that each outranked conversation, with more
    evidence than before reading the words, count (``understand``); many small
    readings spread over unrelated actions are uncertainty, not a request.
    Then Lisan may map the wording, and MIZAN validates the mapping."""
    if understanding.intent != "converse":
        return False
    entities = understanding.entities or {}
    return float(entities.get("mappable") or 0.0) > float(entities.get("conversation") or 0.0)


def validate_parsed(parsed: dict, message: str, language: str) -> Understanding | None:
    """MIZAN's checks on Lisan's proposed mapping; anything doubtful is rejected."""
    intent = parsed.get("intent")
    entities: dict[str, Any] = {"understood_by": "lisan"}
    if intent == "compute":
        expression = str(parsed.get("expression", ""))[:300]
        if calc.find_expression(expression) is None:
            return None  # not a calculation (for example a bare number)
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
        entities.update(
            reference=narration, explain=qasd.prefers(message, "hadith_explain", "hadith")
        )
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
    elif intent == "silsila":
        sequence = _sequence(message)
        if sequence is None:
            return None  # only terms the user actually wrote
        entities.update(sequence)
    elif intent == "web_search":
        query = str(parsed.get("query", "")).strip()[:300]
        if len(query) < 3:
            return None
        # General knowledge is answered in words; a search is for what is
        # current or outside MIZAN, as MIZAN's own model judges the message.
        if not (qasd.facet("current", message) or qasd.prefers(message, "web_search", "converse")):
            return None
        entities["query"] = query
    elif intent == "watch":
        from automation import muraqabah

        try:
            trigger = muraqabah.validate_trigger(dict(parsed.get("when") or {}))
        except (ValueError, TypeError):
            return None
        job = str(parsed.get("task", "")).strip()
        if not job or watch_request(job) is not None or len(job) > 500:
            return None  # the task is what to do each time, never another schedule
        entities["trigger"] = trigger
        entities["task"] = job
        entities["title"] = str(parsed.get("title") or job)[:80]
    elif intent == "web_read":
        url = str(parsed.get("url", "")).strip()
        # Only a link the user actually wrote, never one the model invented or
        # one inside pasted material.
        if not _URL.fullmatch(url) or url not in _own_words(message):
            return None
        entities["url"] = url
    else:
        return None
    return Understanding(str(intent), language, 0.6, entities)
