"""Satr (ستر, covering): a secret in what a tool returns is covered before anything keeps it.

"Whoever covers a Muslim, Allah will cover him in this world and the next" (Muslim 2699).
A tool's output goes to the model, the chat history, the live events and the Sakk
receipt; a key, token or password in it would travel to all of them. :func:`cover`
replaces each secret-shaped value with ``[redacted:<kind>]`` and leaves the rest of the
text as it was.

Two detectors, ported from ForgeKit's ``src/secrets.js``:

1. Format grammars: documented credential shapes (PEM keys, GitHub/GitLab tokens,
   ``sk-`` keys, Slack, Google, JWT, AWS key ids), a password inside a URL
   (``scheme://user:PASSWORD@host``), a value assigned to a key named like a secret
   (``DB_PASSWORD=…``, ``api_key: "…"``) and an ``Authorization`` header.
2. Entropy: a token of 20+ characters with lower case, upper case and digits in three or
   more separate runs whose Shannon entropy reaches 3.9 bits per character, the shape of
   a random credential no format lists.

Precision first, so what MIZAN itself prints is never mangled: hex digests (SHA-256
receipts, git SHAs) and UUIDs lack the mixed case and are not secrets; lockfile and SRI
``sha512-…`` digests are public; code that assigns an expression (``token =
jwt.sign(…)``, ``secret_key = settings.SECRET_KEY``) is left alone; a ``data:`` image is
never read; and the entropy test is not applied inside a link (a document id in a URL
is part of the address the person asked about). Every pattern is bounded, so the scan
is linear in the length of the text.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

MARKER = re.compile(r"\[redacted(?::[a-z_]+)?\]")

# Key names whose assigned value is a credential (DB_PASSWORD, apiKey, x-auth-token).
_KEYISH = r"(?:api[_-]?key|secret|passwd|password|token)"
# Broader words that carry a credential only in the env/query form (AUTH=…, ?auth=…).
_AUTHISH = r"(?:auth(?:orization)?|credentials?)"
_NOT_COVERED = r"(?!\[redacted)"

# Display masking of live events by key name (``agents.events.bounded``): any key that
# mentions one of these words is shown as [redacted], whatever its value.
SECRET_KEY = re.compile(r"(api[_-]?key|token|secret|password|passwd|authorization|cookie)", re.I)

# A structured value is a credential when its key ENDS in a credential word; a cursor
# (``next_page_token``) is not one and is needed to read the next page.
_CREDENTIAL_KEY = re.compile(
    r"(?:^|[_\-.])(?:password|passwd|secret|api[_-]?key|private[_-]?key|token|"
    r"authorization|cookie|bearer)$",
    re.I,
)
_CAMEL_CREDENTIAL_KEY = re.compile(
    r"[a-z0-9](?:Password|Passwd|Secret|ApiKey|Apikey|PrivateKey|Token|Authorization|Cookie)$"
)
_CURSOR_KEY = re.compile(r"(?:page|next|continuation|sync|cursor|resume)[_\-]?token$", re.I)

# (kind, pattern) — format grammars, masked whole.
_FORMATS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_token", re.compile(r"\bghp_[A-Za-z0-9]{16,255}|\bgithub_pat_[A-Za-z0-9_]{20,255}")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,255}")),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,255}", re.I)),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,255}", re.I)),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_-]{20,255}")),
    ("google_token", re.compile(r"\bya29\.[A-Za-z0-9._-]{1,2048}")),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,4096}\.[A-Za-z0-9_-]{10,4096}(?:\.[A-Za-z0-9_-]{0,4096})?"
        ),
    ),
    # AWS key ids only mean "credential" in their exact case.
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("api_key", re.compile(r"\bapikey_[0-9a-f]{40}_[0-9a-f]{64}\b")),
)
_PEM = re.compile(r"-----BEGIN [\s\S]*?(?:-----END [^\n-]{0,64}-----|$)", re.I)
_URL_CRED = re.compile(r"(\b[a-z][a-z0-9+.-]{0,31}://[^\s/:@]{0,256}:)([^\s/@]{1,256})(?=@)", re.I)
_AUTH_HEADER = re.compile(
    r"(\bauthorization[\"']?\s*:\s*[\"']?(?:basic|bearer|digest|token)\s+)"
    + _NOT_COVERED
    + r"([^\s\"']{4,512})",
    re.I,
)
# A bare bearer credential (a log line): a run with a digit in it, never a prose word.
_BEARER = re.compile(
    r"(\bbearer\s+)" + _NOT_COVERED + r"(?=[A-Za-z0-9._~+/=-]{0,64}\d)([A-Za-z0-9._~+/=-]{16,512})",
    re.I,
)
# The env/shell/query form ``…PASSWORD=value``: the key ENDS in a secret word, ``=`` is bare,
# and the whole shell word is the value (a kwarg ``f(password=pw)`` is left alone).
_ENV_ASSIGNED = re.compile(
    rf"((?:{_KEYISH}|{_AUTHISH})[\"']?=(?:(?:basic|bearer|digest|token) +)?)"
    + _NOT_COVERED
    + r"(?![\s$\"'{])([^\s\"'`;&|<>()]{1,512})(?=[\s\"'`;&|]|$)",
    re.I,
)
# Any separator: a quoted literal, or an 8+ character credential-class run that is not
# the start of an expression (a call, an index or an attribute: ``settings.SECRET_KEY``).
_ASSIGNED = re.compile(
    rf"({_KEYISH}[\w-]{{0,64}}[\"']?\s*[:=]\s*(?:(?:basic|bearer|token)\s+)?)"
    + _NOT_COVERED
    + r"(\"[^\"\n]{4,512}\"|'[^'\n]{4,512}'"
    r"|[A-Za-z0-9+/=_!@#%^&*~-][A-Za-z0-9+/=_!@#$%^&*~-]{7,511}(?![\w(\[]|\.[A-Za-z_]))",
    re.I,
)

ENTROPY_MIN_LEN = 20
ENTROPY_MIN_BITS = 3.9
ENTROPY_MIN_DIGIT_RUNS = 3
# Content digests are random-looking by design but public (npm/yarn lockfiles, SRI,
# go.sum); the XMP packet id is fixed by Adobe's specification.
_EXEMPT = r"\b(?:sha(?:1|256|384|512)-[A-Za-z0-9+/]{16,512}={0,2}|h1:[A-Za-z0-9+/]{43}=)"
_PUBLIC_CONSTANT = r"(?<![A-Za-z0-9+=_-])W5M0MpCehiHzreSzNTczkc9d(?![A-Za-z0-9+=_-])"
_ENTROPY_SCAN = re.compile(rf"({_EXEMPT}|{_PUBLIC_CONSTANT})|[A-Za-z0-9+=_-]{{20,4096}}")
_LINK = re.compile(r"\b[a-z][a-z0-9+.-]{0,31}://[^\s\"'<>]{1,4096}", re.I)
_DATA_URI = re.compile(r"^data:[\w/+.-]{1,100};base64,", re.I)


def _entropy(token: str) -> float:
    counts = Counter(token)
    total = len(token)
    return -sum(n / total * math.log2(n / total) for n in counts.values())


def high_entropy(token: str) -> bool:
    """A bare token shaped like a random credential by measure alone."""
    if len(token) < ENTROPY_MIN_LEN:
        return False
    if not (re.search(r"[a-z]", token) and re.search(r"[A-Z]", token) and re.search(r"\d", token)):
        return False
    if len(re.findall(r"\d+", token)) < ENTROPY_MIN_DIGIT_RUNS:
        return False
    return _entropy(token) >= ENTROPY_MIN_BITS


def _mark(kind: str, labelled: bool) -> str:
    return f"[redacted:{kind}]" if labelled else "[redacted]"


def _cover_entropy(text: str, labelled: bool) -> str:
    def scan(segment: str) -> str:
        return _ENTROPY_SCAN.sub(
            lambda m: (
                m.group(0)
                if m.group(1) or not high_entropy(m.group(0))
                else _mark("high_entropy", labelled)
            ),
            segment,
        )

    # A link is the address the person asked about: its path is never scored.
    out, last = [], 0
    for link in _LINK.finditer(text):
        out.append(scan(text[last : link.start()]))
        out.append(link.group(0))
        last = link.end()
    out.append(scan(text[last:]))
    return "".join(out)


def cover_text(text: str, *, labelled: bool = True) -> str:
    """The text with every secret-shaped value replaced (``labelled``: by its kind)."""
    if not text or _DATA_URI.match(text):
        return text
    text = _PEM.sub(_mark("private_key", labelled), text)
    # The URL password first: ``https://x-access-token:PW@host`` masks PW, not ``PW@host``.
    text = _URL_CRED.sub(lambda m: m.group(1) + _mark("url_password", labelled), text)
    for kind, pattern in _FORMATS:
        text = pattern.sub(_mark(kind, labelled), text)
    text = _AUTH_HEADER.sub(lambda m: m.group(1) + _mark("authorization", labelled), text)
    text = _BEARER.sub(lambda m: m.group(1) + _mark("authorization", labelled), text)
    text = _ENV_ASSIGNED.sub(lambda m: m.group(1) + _mark("assigned", labelled), text)

    def assigned(m: re.Match[str]) -> str:
        value = m.group(2)
        # ``secret_dir = /etc/app`` is a path, unless it is random once its slashes go.
        if value.startswith("/") and not high_entropy(value.replace("/", "")):
            return m.group(0)
        return m.group(1) + _mark("assigned", labelled)

    text = _ASSIGNED.sub(assigned, text)
    return _cover_entropy(text, labelled)


def credential_key(name: Any) -> bool:
    """Whether a structured value under this key is a credential (``client_secret``,
    ``accessToken``), not a cursor (``next_page_token``) or a count (``max_tokens``)."""
    key = str(name)
    named = _CREDENTIAL_KEY.search(key) or _CAMEL_CREDENTIAL_KEY.search(key)
    return bool(named) and not _CURSOR_KEY.search(key)


def cover(value: Any, depth: int = 0) -> Any:
    """A copy of a tool's output (str, dict, list, tuple, nested) with secrets covered.
    Other values (numbers, booleans, None, bytes) are returned as they are."""
    if depth > 40:
        return value
    if isinstance(value, str):
        return cover_text(value)
    if isinstance(value, dict):
        covered: dict = {}
        for key, item in value.items():
            if (
                isinstance(item, str)
                and len(item) >= 6
                and credential_key(key)
                and not MARKER.fullmatch(item)
            ):
                covered[key] = _mark("key", True)
            else:
                covered[key] = cover(item, depth + 1)
        return covered
    if isinstance(value, list):
        return [cover(item, depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(cover(item, depth + 1) for item in value)
    return value


def holds(text: Any) -> bool:
    """Whether this text (or structure) holds anything :func:`cover` would cover."""
    return bool(cover(text) != text)


def markers(text: str) -> int:
    """How many covered places this text shows."""
    return len(MARKER.findall(text or ""))
