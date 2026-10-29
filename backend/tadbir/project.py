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


def out_of_scope(message: str) -> bool:
    """A stack beyond the blueprints, or (as MIZAN's intent model reads it) a
    question about building rather than a request to build."""
    from . import qasd

    return bool(_BEYOND.search(message)) or qasd.prefers(message, "converse", "build_project")


def blueprint(message: str) -> dict | None:
    """The blueprint and name of a project to build; None for stacks beyond them."""
    if _BEYOND.search(message):
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


def extract_files(reply: str, allowed: set[str], *, new_files: bool = False) -> dict[str, str]:
    """Fenced blocks whose info string names one of the project's files.

    With ``new_files``, a block may also create a file at a new, safe path.
    """
    found: dict[str, str] = {}
    for info, body in re.findall(r"```[ \t]*([^\n`]*)\n(.*?)```", reply, re.DOTALL):
        if _SEARCH in body:
            continue  # an edit block (extract_edits), never a whole file
        for token in re.split(r"[\s:=\"'`]+", info):
            path = _local(token)
            if path in allowed or (new_files and editable(path)):
                found[path] = body.strip("\n") + "\n"
                break
    return found


_SEARCH = "<<<<<<< SEARCH"
_EDIT_PAIR = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n?>>>>>>> REPLACE", re.DOTALL)


def extract_edits(reply: str, allowed: set[str]) -> dict[str, list[tuple[str, str]]]:
    """Edit blocks (a path, then SEARCH/REPLACE pairs) for files the project has."""
    found: dict[str, list[tuple[str, str]]] = {}
    for info, body in re.findall(r"```[ \t]*([^\n`]*)\n(.*?)```", reply, re.DOTALL):
        if _SEARCH not in body:
            continue
        for token in re.split(r"[\s:=\"'`]+", info):
            path = _local(token)
            if path in allowed:
                found.setdefault(path, []).extend(_EDIT_PAIR.findall(body))
                break
    return {path: pairs for path, pairs in found.items() if pairs}


def apply_edits(
    edits: dict[str, list[tuple[str, str]]], originals: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Each file with its edits applied in order, every SEARCH matching exactly once;
    a file any of whose edits does not match is left as it was and named."""
    from fastapi import HTTPException

    from workspace.store import replaced

    changed: dict[str, str] = {}
    refused: list[str] = []
    for path, pairs in edits.items():
        text = originals[path]
        try:
            for old, new in pairs:
                text, _count = replaced(text, old, new)
        except HTTPException as exc:
            refused.append(f"{path}: {exc.detail}")
            continue
        changed[path] = text
    return changed, refused


_PATH_COMMENT = re.compile(
    r"^\s*(?:#|//|/\*|<!--)\s*([A-Za-z0-9_][\w./-]*\.\w+)\s*(?:\*/|-->)?\s*$"
)


def infer_file(reply: str, originals: dict[str, str], named: list[str]) -> dict[str, str]:
    """One unnamed code block in Lisan's reply, as the one file it must be.

    Lisan sometimes answers with ```python instead of ```shapes.py. The block is
    taken as a file only when it names it in a first-line comment, or when the
    request names exactly one existing file to change (tests aside); and only
    when it is the whole file (it keeps most of the original's lines), never a
    snippet that would drop the rest of the file.
    """
    blocks = re.findall(r"```[ \t]*([^\n`]*)\n(.*?)```", reply, re.DOTALL)
    if len(blocks) != 1:
        return {}
    body = blocks[0][1].strip("\n")
    first, _, rest = body.partition("\n")
    hinted = _PATH_COMMENT.match(first)
    if hinted and _local(hinted.group(1)) in originals:
        target: str | None = _local(hinted.group(1))
        body = rest.strip("\n")
    else:
        targets = [name for name in named if name in originals]
        if len(targets) > 1:
            targets = [name for name in targets if not _is_test(name)]
        target = targets[0] if len(targets) == 1 else None
    if target is None or not _whole(originals[target], body):
        return {}
    return {target: body + "\n"}


def _is_test(path: str) -> bool:
    name = path.split("/")[-1]
    return name.startswith("test_") or bool(re.search(r"(?:_test\.py|\.(?:test|spec)\.\w+)$", name))


def _whole(original: str, new: str) -> bool:
    """The new text keeps most of the original's lines: a whole file, not a snippet."""
    lines = {line.strip() for line in original.splitlines() if line.strip()}
    if len(lines) < 3:
        return True
    kept = {line.strip() for line in new.splitlines()} & lines
    return len(kept) / len(lines) >= 0.6


# ── editing an existing project ──────────────────────────────────────────

TEXT_EXTENSIONS = {
    "html", "htm", "css", "js", "mjs", "cjs", "jsx", "ts", "tsx", "py", "json", "md", "txt",
    "toml", "yaml", "yml", "svg", "xml", "csv", "ini", "cfg",
}  # fmt: skip
_SKIP_DIRS = {"node_modules", "dist", "build", ".git", "__pycache__", ".venv", "venv", ".next"}
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,159}$")
_ENTRY = {"index.html", "app.js", "main.js", "script.js", "style.css", "main.py", "app.py"}


def editable(path: str) -> bool:
    """A text file MIZAN may read or change (no hidden, vendored or build output)."""
    if not _SAFE_PATH.match(path) or ".." in path.split("/"):
        return False
    parts = path.split("/")
    if any(part in _SKIP_DIRS or part.startswith(".") for part in parts):
        return False
    return path.rsplit(".", 1)[-1].lower() in TEXT_EXTENSIONS if "." in parts[-1] else False


def relevant_files(files: list[dict], request: str, budget: int = 60_000) -> list[str]:
    """The files Lisan sees: all of a small project, else the most relevant ones."""
    from core.adaptive import bm25_scores, tokenize

    texts = [f for f in files if editable(str(f.get("path", "")))]
    if sum(int(f.get("size", 0)) for f in texts) <= budget and len(texts) <= 8:
        return [str(f["path"]) for f in texts]
    documents = [tokenize(re.sub(r"[/._-]+", " ", str(f["path"]))) for f in texts]
    scores = bm25_scores(tokenize(request), documents)
    ranked = sorted(
        range(len(texts)),
        key=lambda i: scores[i] + (1.0 if str(texts[i]["path"]).split("/")[-1] in _ENTRY else 0),
        reverse=True,
    )
    chosen: list[str] = []
    used = 0
    for index in ranked:
        size = int(texts[index].get("size", 0))
        if len(chosen) >= 6 or used + size > budget:
            continue
        chosen.append(str(texts[index]["path"]))
        used += size
    return chosen


def local_references(html: str) -> set[str]:
    """Files a page loads from its own project (not http, data or absolute URLs)."""
    scan = scan_html(html)
    return {
        ref
        for ref in scan.styles | scan.scripts
        if ref and not re.match(r"^(?:[a-z]+:|//|/)", ref, re.IGNORECASE)
    }
