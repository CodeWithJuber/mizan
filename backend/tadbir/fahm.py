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

from . import amanah, calc, hadith, project, qiyas, quran, silsila, waqt

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


# Quranic text is fully vowelled: a word with two or more marks is quoted, not the user's own.
_VOWEL_MARKS = re.compile("[\u064b-\u0652\u0670\u06d6-\u06ed]")
_ARABIC_SCRIPT_WORD = re.compile("[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]+")


def _own_script(text: str) -> str:
    """The text without quoted, vowelled Arabic, when the user's own words remain."""
    stripped = _ARABIC_SCRIPT_WORD.sub(
        lambda word: " " if len(_VOWEL_MARKS.findall(word.group(0))) >= 2 else word.group(0), text
    )
    return stripped if re.search(r"[^\W\d_]{2,}", stripped) else text


def detect_language(text: str) -> str:
    text = _own_script(text)
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
# The request needs something current or outside MIZAN, so a search may answer it.
_CURRENT = re.compile(
    r"\b(?:now|abhi|current\w*|this\s+(?:week|month|year)|today|tonight|yesterday|kal|aaj|"
    r"score|price|prices|rate|weather|stock|news|latest|recent\w*|update\w*|20[2-9]\d)\b",
    re.IGNORECASE,
)
# The message brings its own material to work on: not a request to search.
_PROVIDED = re.compile(
    r"\b(?:here\s+is|here's|based\s+(?:only\s+)?on\s+(?:this|the\s+following)|using\s+it|"
    r"this\s+(?:page|text|review|email|article|output|document|passage)|tool\s+output)\b"
    r"|\n---\n|^---$",
    re.IGNORECASE | re.MULTILINE,
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
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# A question about a page the user names ("According to <url>, what was …?").
_ASKS = re.compile(
    r"[?؟]|\baccording\s+to\b|\b(?:what|which|who|when|where|how\s+(?:many|much))\b|"
    r"\b(?:find|tell\s+me|cite|give\s+me|kya|kitna|kitne|batao|kis|kin|kaun|kaisa|kaise)\b|"
    r"(?<!\w)(?:ما|ماذا|من|لمن|كيف|متى|أين|هل|كم|کیا|کون|کس|کب|کہاں|کتنا|کیسے|क्या|कौन|किस)(?!\w)",
    re.IGNORECASE,
)
# A file in the selected project, named in the user's words (`sales.csv`, app.log).
_FILE_NAME = re.compile(
    r"(?<![\w/.-])`?([A-Za-z0-9_][\w./-]{0,120}\.(?:py|js|mjs|cjs|sh|csv|tsv|json|jsonl|log|txt|"
    r"md|xml|ya?ml|ini|toml|html|css))`?(?![\w-])",
    re.IGNORECASE,
)
_DATA_FILE = re.compile(r"\.(?:csv|tsv|json|jsonl|log|xml)$", re.IGNORECASE)
_RUNNABLE = re.compile(r"\.(?:py|js|mjs|cjs|sh)$", re.IGNORECASE)
# Work over data: compute, count, sort, filter, total… ("hisab karo", "gino").
_DATA_VERB = re.compile(
    r"\b(?:compute|calculate|count|counts|total|totals|sum|average|mean|median|sort|sorted|"
    r"group|aggregate|work\s+out|tally|filter|which|how\s+many|extract|parse|convert|merge|"
    r"dedupe|deduplicate|summari[sz]e\s+the\s+(?:numbers|data)|hisab|gino|ginti|nikalo)\b",
    re.IGNORECASE,
)


def named_files(message: str) -> list[str]:
    """File names the user wrote in their own words (links removed), in order."""
    own = _URL.sub(" ", _own_words(message))
    seen: list[str] = []
    for name in _FILE_NAME.findall(own):
        name = name.strip("`./")
        if name and name not in seen:
            seen.append(name)
    return seen[:12]


def _project_request(message: str, asks_run: bool) -> Understanding | None:
    """Work on the selected project's files: run a file, or process its data."""
    if not _selected_project():
        return None
    names = named_files(message)
    if not names:
        return None
    language = detect_language(message)
    runnable = [name for name in names if _RUNNABLE.search(name)]
    if asks_run and runnable and not _BUILD.search(message) and not project.change_request(message):
        return Understanding("run_file", language, 0.85, {"path": runnable[0]})
    if any(_DATA_FILE.search(name) for name in names) and _DATA_VERB.search(message):
        return Understanding("project_task", language, 0.8, {"request": message, "files": names})
    if _WRITE_FROM.search(message) and len(names) >= 2:
        # "Summarise notes.txt into summary.md": language work Lisan writes into a file.
        return Understanding("edit_project", language, 0.75, {"request": message})
    return None


_WRITE_FROM = re.compile(
    r"\b(?:summari[sz]e|translate|rewrite|reformat|document|describe|outline|condense|"
    r"khulasa|tarjuma)\b",
    re.IGNORECASE,
)


def _own_words(message: str) -> str:
    """The message without pasted material (a region that is only a link stays)."""
    own = _IMAGE.sub(" ", message)
    for region in amanah.pasted(message):
        if not _URL.fullmatch(region.strip().rstrip(".,;)")):
            own = own.replace(region, " ")
    return own


_EXPLAIN = re.compile(
    r"\b(?:tafsee?r|tafsir|explain|explanation|meaning|matlab|samjhao|sharh|sharah|tashreeh)\b"
    r"|تفسیر|تفسير|شرح|تشریح|व्याख्या|तशरीह",
    re.IGNORECASE,
)


_WATCH_CUE = re.compile(
    r"\b(?:bhej(?:o|na|iye|en|a\s+karo)|send|remind|yaad\s+dila(?:o|na|iye|ya\s+karo)|"
    r"bata(?:o|na|iye|ya\s+karo)|notify|alert|message\s+karo)\b",
    re.IGNORECASE,
)
_PRAYER_NAMES = {
    "fajr": "fajr", "fajar": "fajr", "zuhr": "dhuhr", "zohar": "dhuhr", "zuhar": "dhuhr",
    "dhuhr": "dhuhr", "duhr": "dhuhr", "asr": "asr", "asar": "asr", "maghrib": "maghrib",
    "magrib": "maghrib", "isha": "isha", "esha": "isha", "ishaa": "isha",
}  # fmt: skip
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
_SALAH_WORD = "(" + _PRAYER[1:-1] + "|sehri|sahri|suhoor|iftar|iftari)"
_SALAH_TIME = re.compile(
    r"(?:" + _PRAYER + r"|namaz|namaaz|nam[aā]z|prayer|salah|salat|sehri|sahri|suhoor|iftar|iftari)"
    r"\s*(?:ka|ki|ke|of)?\s*(?:time|times|timing|timings|waqt|waqat|auqat|kab)\b"
    r"|\b(?:prayer|namaz|salah)\s+times?\b|\bwhen\s+is\s+" + _PRAYER,
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


def watch_request(message: str) -> dict | None:
    """A standing request ("every day after Fajr, send me an ayah"), or None."""
    if not _WATCH_CUE.search(message):
        return None
    relative = _RELATIVE.search(message)
    clock = _CLOCK.search(message)
    trigger: dict | None = None
    if relative:
        name = (relative.group(1) or relative.group(4) or "").lower()
        direction = (relative.group(2) or relative.group(3) or "").lower()
        before = direction in {"pehle", "before"}
        offset = _OFFSET.search(message)
        minutes = int(offset.group(1)) if offset else (30 if before else 20)
        trigger = {"kind": "prayer", "prayer": _PRAYER_NAMES[name],
                   "offset": -minutes if before else minutes}  # fmt: skip
    elif clock and _EVERY.search(message):
        hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
        meridiem = clock.group(3).lower().replace(".", "")
        if (meridiem == "pm" or (meridiem == "baje" and _EVENING.search(message))) and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            return None
        trigger = {"kind": "daily", "time": f"{hour:02d}:{minute:02d}"}
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
    what = _bare(_WATCH_CUE.sub(" ", message))
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


def understand(text: str) -> Understanding:
    message = text.strip()
    language = detect_language(message)
    words = re.findall(r"\w+", message)

    if _CAPABILITY.search(message) and len(words) <= 25:
        return Understanding("capabilities", language, 0.9)

    standing = watch_request(message)
    if standing is not None:
        return Understanding("watch", language, 0.9, standing)

    salah = _SALAH_TIME.search(message)
    if salah and len(words) <= 20:
        named = next((m.lower() for m in re.findall(_SALAH_WORD, message, re.IGNORECASE) if m), "")
        prayer = {"sehri": "fajr", "sahri": "fajr", "suhoor": "fajr", "iftar": "maghrib",
                  "iftari": "maghrib"}.get(named, _PRAYER_NAMES.get(named))  # fmt: skip
        return Understanding("salah", language, 0.9, {"prayer": prayer})

    explain = bool(_EXPLAIN.search(message))
    # "Write a function format_citation … 'Surah 2, Ayah 255'": code, not a lookup.
    writes_code = bool(_BUILD.search(message))
    reference = None if writes_code else quran.parse_reference(message)
    if reference is not None:
        # "What did the people say in 2:71?": a question about what the ayah says.
        questioned = bool(_ASKS.search(message)) and not explain and len(words) > 4
        return Understanding(
            "quran",
            language,
            0.95,
            {"reference": reference, "explain": explain, "question": questioned},
        )

    narration = None if writes_code else hadith.parse_reference(message)
    if narration is not None:
        return Understanding("hadith", language, 0.95, {"reference": narration, "explain": explain})

    asks_run = bool(re.search(_RUN, message, re.IGNORECASE))
    when = waqt.parse(message)
    # "a program that prints today's date, run it" is a program, not a date question.
    if when is not None and len(words) <= 25 and not (_BUILD.search(message) and asks_run):
        return Understanding("waqt", language, 0.9, {"request": when})

    puzzle = qiyas.parse(message)
    if puzzle is not None:
        return Understanding("qiyas", language, 0.9, {"puzzle": puzzle})

    sequence = silsila.parse(message)
    if sequence is not None:
        return Understanding("silsila", language, 0.9, {"sequence": sequence})

    fenced = _fenced_code(message)
    if fenced and (asks_run or len(message) - len(fenced[0]) < 40):
        code, code_language = fenced
        return Understanding(
            "run_code", language, 0.9, {"code": code, "code_language": code_language}
        )

    on_project = _project_request(message, asks_run)
    if on_project is not None:
        return on_project

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

    hub = hub_request(message)
    if hub is not None:
        return Understanding("hf_hub", language, 0.85, hub)

    # Only a link in the user's own words is read; a link inside pasted text or
    # a Markdown image is material (and may be a way to send data out).
    own = _own_words(message)
    url = _URL.search(own)
    asks_about_page = (
        _ASKS.search(message) and project.detect(message) is None and not _BUILD.search(message)
    )
    if url and (_READ.search(message) or asks_about_page or len(message) - len(url[0]) < 25):
        # Every link in the user's own words, in order: when one page is gone,
        # MIZAN reads the next one the user gave.
        urls = list(dict.fromkeys(found.rstrip(").,;") for found in _URL.findall(own)))[:4]
        return Understanding(
            "web_read", language, 0.85, {"url": url[0].rstrip(").,;"), "urls": urls}
        )

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

    if _SEARCH.search(message) and not url and not _PROVIDED.search(message):
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


_HUB_WORD = re.compile(r"\b(?:hugging\s*face|huggingface|hf)\b", re.IGNORECASE)
_HUB_LIST = re.compile(
    r"\b(?:list|show|dikhao|dikha\s*do|batao|kaun\s+se|kya\s+kya|which|what|mere|my|apne)\b",
    re.IGNORECASE,
)
_HUB_IMPORT = re.compile(
    r"\b(?:import|download|le\s*aao|lao|laao|utha\w*|daal\w*|copy|bring|fetch|project\s+me)\b",
    re.IGNORECASE,
)


def hub_request(message: str) -> dict | None:
    """A request about Hugging Face: list an account, inspect a repository, import a file."""
    from knowledge import hf_hub

    own = _own_words(message)
    link = hf_hub.parse_link(own)
    kinds = [kind for kind in ("datasets", "models", "spaces")
             if re.search(kind[:-1], message, re.IGNORECASE)] or ["datasets", "models"]  # fmt: skip
    if re.search(r"\btrain", message, re.IGNORECASE) and "models" not in kinds:
        kinds.append("models")  # "datasets / training": the trained models too
    if link is None:
        if _HUB_WORD.search(own) and _HUB_LIST.search(own) and len(own.split()) <= 25:
            return {"action": "repos", "owner": "", "kinds": kinds}
        return None
    if "owner" in link:
        return {"action": "repos", "owner": link["owner"], "kinds": kinds}
    named = [name for name in named_files(own) if "." in name]
    path = link.get("path") or (named[0] if named and _HUB_IMPORT.search(own) else None)
    entities = {"repo": link["repo"], "kind": link["kind"], "revision": link["revision"]}
    if path:
        return {"action": "import", "path": path, **entities}
    return {"action": "files", **entities}


_NO_TOPIC = re.compile(
    r"\b(?:pahle|pehle|abhi|please|plz|it|this|that|isko|ise|usko|use|internet|web|online|"
    r"google|par|pe|se|me|mein|karo|kro|kar|do|for|now|jaldi|first|then|again|phir|dobara|"
    r"karke|dekho|bhai|yaar|tum|aap|zara|na|toh|bhi|ab|you|can|could|the|on|and|aur|ek|baar)\b",
    re.IGNORECASE,
)


_SEARCH_VERB = re.compile(
    r"\b(?:search|google|look\s+up|find\s+online|browse\s+for|khojo|dhundo|dhoondo|"
    r"search\s+karo)\b",
    re.IGNORECASE,
)


def bare_search(text: str) -> bool:
    """A search request with no topic of its own ("Dhundo pahle", "search it")."""
    rest = _NO_TOPIC.sub(" ", _SEARCH_VERB.sub(" ", text or ""))
    return bool(_SEARCH_VERB.search(text or "")) and not re.search(r"[^\W\d_]{2,}", rest)


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
    elif intent == "silsila":
        sequence = silsila._run_of_numbers(message)
        if sequence is None:
            return None  # only terms the user actually wrote
        entities["sequence"] = sequence
    elif intent == "web_search":
        query = str(parsed.get("query", "")).strip()[:300]
        if len(query) < 3:
            return None
        if not (_SEARCH.search(message) or _CURRENT.search(message)):
            return None  # general knowledge: answered in words, not by searching
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
