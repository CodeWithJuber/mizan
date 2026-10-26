"""Projects MIZAN builds itself: blueprints, static checks and safe repairs.

MIZAN chooses the files of a project from its own blueprints, asks Lisan to
write each one, saves them through the coding-workspace tools and checks the
result: links between the files, element ids, CSS structure, JavaScript
syntax in the sandbox, Python tests and a clean run. Lisan only writes and
corrects file contents; MIZAN decides what is checked and when it is done.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class FileSpec:
    path: str
    purpose: str


@dataclass(frozen=True)
class Blueprint:
    kind: str
    label: str
    files: tuple[FileSpec, ...]


BLUEPRINTS = {
    "web": Blueprint(
        "web",
        "small static web app (HTML, CSS and JavaScript, no build step)",
        (
            FileSpec(
                "index.html",
                "the page markup; links style.css in the head and loads app.js at the end of "
                "the body; gives an id to every element app.js uses",
            ),
            FileSpec("style.css", "the styles; clean, readable and usable at phone width"),
            FileSpec(
                "app.js",
                "the behaviour in plain JavaScript; looks elements up by the ids in index.html",
            ),
        ),
    ),
    "python": Blueprint(
        "python",
        "small Python program (standard library only) with unittest tests",
        (
            FileSpec(
                "main.py",
                "the program: well-named functions, and a main() that demonstrates them with "
                "sample data and exits; guarded by if __name__ == '__main__'; never reads input",
            ),
            FileSpec(
                "test_main.py",
                "unittest tests for the functions in main.py (import them from main)",
            ),
        ),
    ),
}

_NOUN = (
    r"(?:app|apps|application|website|web\s*site|webpage|web\s*page|landing\s*page|homepage|"
    r"site|game|calculator|todo|to-do|portfolio|dashboard|quiz|timer|stopwatch|clock|"
    r"converter|tracker|counter|form|page|project|tool|cli)"
)
_MAKE = (
    r"(?:build|create|make|develop|code|generate|banao|banaao|bnao|bana\s*do|bana\s*ke\s*do|"
    r"bana\s*dijiye|tayyar\s+karo|likho)"
)
_REQUEST = re.compile(
    rf"\b{_MAKE}\b[^.\n?]{{0,80}}\b{_NOUN}\b|\b{_NOUN}\b[^.\n?]{{0,80}}\b{_MAKE}\b"
    r"|(?:ویب\s*سائٹ|ایپ|گیم|کیلکولیٹر)[^.\n؟]{0,60}(?:بناؤ|بنا\s*دو|بنائیں)"
    r"|(?:वेबसाइट|ऐप|गेम|कैलकुलेटर)[^.\n?]{0,60}(?:बनाओ|बना\s*दो|बनाएं|बनाइए)",
    re.IGNORECASE,
)
# Asking how to build something is a question, not a request to build it.
_QUESTION = re.compile(
    r"\b(?:how|kaise|kaisay|kese|why|kyun|kyon|steps|tutorial|guide|sikhao|seekhna|explain)\b"
    r"|کیسے|कैसे",
    re.IGNORECASE,
)
# Stacks beyond the blueprints go to the general agent loop.
_BEYOND = re.compile(
    r"\b(?:react|next\.?js|vue|angular|svelte|django|flask|fastapi|express|laravel|php|"
    r"database|sql|mongo\w*|firebase|supabase|backend|server|api|login|auth\w*|android|ios|"
    r"flutter|kotlin|swift|java|c\+\+|rust|golang|typescript|docker|deploy)\b",
    re.IGNORECASE,
)
_PYTHON = re.compile(r"\b(?:python|py|cli|command\s*line|terminal|console)\b", re.IGNORECASE)
_STOP = {
    "a", "an", "the", "ek", "simple", "small", "basic", "new", "nice", "beautiful", "chhota",
    "chota", "sa", "si", "mera", "meri", "my", "me", "mujhe", "ke", "liye", "for", "please",
    "plz", "build", "create", "make", "develop", "code", "generate", "banao", "bana", "bnao",
    "do", "likho", "python", "py", "web", "html", "js", "javascript", "achha", "accha",
    "sundar", "ki", "ka", "mein", "aur", "and", "with", "mere", "hamara", "hamare",
    "jo", "jisme", "about", "of",
}  # fmt: skip


def detect(message: str) -> dict | None:
    """The project a message asks MIZAN to build, or None."""
    if not _REQUEST.search(message) or _QUESTION.search(message) or _BEYOND.search(message):
        return None
    kind = "python" if _PYTHON.search(message) else "web"
    return {"kind": kind, "name": project_name(message)}


_SCRIPT_NOUNS = {
    "کیلکولیٹر": "Calculator", "ایپ": "app", "ویب سائٹ": "Website", "گیم": "Game",
    "कैलकुलेटर": "Calculator", "ऐप": "app", "वेबसाइट": "Website", "गेम": "Game",
}  # fmt: skip


def project_name(message: str) -> str:
    """A short name from the request's own words ("Calculator app", "Quiz game")."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", message)
    noun = re.compile(_NOUN + r"$", re.IGNORECASE)
    for index, word in enumerate(words):
        if noun.match(word):
            end = index + 1
            while end < len(words) and end - index < 3 and noun.match(words[end]):
                end += 1
            before = [w for w in words[max(0, index - 3) : index] if w.lower() not in _STOP]
            name = " ".join([*before[-2:], *words[index:end]])
            return (name[:1].upper() + name[1:])[:60]
    found = sorted(
        (message.find(text), english) for text, english in _SCRIPT_NOUNS.items() if text in message
    )
    if found:
        name = " ".join(english for _position, english in found[:2])
        return name[:1].upper() + name[1:]
    return "MIZAN project"


# ── static checks MIZAN runs itself ──────────────────────────────────────


class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.styles: set[str] = set()
        self.scripts: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "link" and "stylesheet" in values.get("rel", "").lower() and values.get("href"):
            self.styles.add(_local(values["href"]))
        if tag == "script" and values.get("src"):
            self.scripts.add(_local(values["src"]))


def _local(reference: str) -> str:
    return reference.split("?")[0].split("#")[0].removeprefix("./")


def scan_html(html: str) -> _Scan:
    scan = _Scan()
    scan.feed(html)
    scan.close()
    return scan


def link_assets(html: str, css: str = "style.css", js: str = "app.js") -> tuple[str, bool]:
    """Make index.html load the project's CSS and JS (MIZAN's own repair)."""
    scan = scan_html(html)
    changed = False
    if css not in scan.styles:
        tag = f'<link rel="stylesheet" href="{css}">'
        html, count = re.subn(r"</head>", f"  {tag}\n</head>", html, count=1, flags=re.I)
        html = html if count else f"{tag}\n{html}"
        changed = True
    if js not in scan.scripts:
        tag = f'<script src="{js}"></script>'
        html, count = re.subn(r"</body>", f"  {tag}\n</body>", html, count=1, flags=re.I)
        html = html if count else f"{html}\n{tag}\n"
        changed = True
    return html, changed


_ID_LOOKUP = re.compile(
    r"getElementById\(\s*['\"]([\w-]+)['\"]\s*\)"
    r"|querySelector(?:All)?\(\s*['\"]#([\w-]+)['\"]\s*\)"
)
_ID_CREATED = re.compile(
    r"\.id\s*=\s*['\"]([\w-]+)['\"]|setAttribute\(\s*['\"]id['\"]\s*,\s*['\"]([\w-]+)['\"]"
    r"|\bid=\\?['\"]([\w-]+)\\?['\"]"
)


def missing_ids(html: str, js: str) -> list[str]:
    """Element ids app.js looks up that neither index.html nor app.js creates."""
    used = {a or b for a, b in _ID_LOOKUP.findall(js)}
    created = {a or b or c for a, b, c in _ID_CREATED.findall(js)}
    return sorted(used - scan_html(html).ids - created)


def css_balanced(css: str) -> bool:
    text = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    text = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", "", text)
    depth = 0
    for char in text:
        depth += {"{": 1, "}": -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0


def extract_files(reply: str, allowed: set[str]) -> dict[str, str]:
    """Fenced blocks whose info string names one of the project's files."""
    found: dict[str, str] = {}
    for info, body in re.findall(r"```[ \t]*([^\n`]*)\n(.*?)```", reply, re.DOTALL):
        for token in re.split(r"[\s:=\"'`]+", info):
            path = _local(token)
            if path in allowed:
                found[path] = body.strip("\n") + "\n"
                break
    return found
