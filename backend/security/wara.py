"""Wara' (ورع): a package an install would fetch is vetted before the install runs.

"Leave what gives you doubt for what does not give you doubt" (Tirmidhi 2518). A model
that invents a package name is the slopsquatting attack surface: the name sounds right,
someone registers it, and the install runs their code. Before a command MIZAN runs
installs a registry package, Wara' asks that package's own registry whether it exists
and how long it has, OSV whether it is listed as malicious, and compares its name with
a small bundled list of popular ones. Ported from ForgeKit's ``src/depgate.js``.

Evidence-proportional, like every gate in MIZAN: a verdict carries the evidence that
earned it, and missing evidence never blocks.

- ``refuse``: first-hand evidence of harm only. The registry does not have the name
  (PyPI and npm are the only places pip and npm look by default, so the name is
  invented), or OSV lists it as malicious (a ``MAL-`` advisory, the OpenSSF
  malicious-packages feed).
- ``ask``: doubt. Youth (a 30-day half-life since the first publish), a thin history
  (few versions) and a name one slip from a popular package combine by noisy-OR,
  score = 1 − ∏(1 − wₖ·sₖ); at 0.5 or more a person decides (in every permission mode;
  held when no one is watching; refused when no one can be asked).
- ``allow``: everything else. A score of 0.25 or more, or a registry that could not be
  reached, leaves a note on the result; the install runs as before.

What leaves the server: a package name goes to its own public registry. Only when the
registry has it is the name also sent to OSV, so a typo, an invention or a private name
is told to no one else. A command that points the install at another index
(``--index-url``, ``--registry``) is not vetted: a miss there proves nothing.

``MIZAN_WARA`` = on (default) | off. Verdicts are cached in-process per (ecosystem,
name) for six hours; a registry that could not be reached is asked again next time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger("mizan.wara")

ECOSYSTEMS: dict[str, dict[str, str]] = {
    "pypi": {"label": "PyPI", "osv": "PyPI"},
    "npm": {"label": "the npm registry", "osv": "npm"},
}
# Weights of the noisy-OR (ForgeKit's depgate, with the squat signal for a name one slip
# from a popular one). A signal of 1 alone: youth asks, squat and thin only note.
WEIGHTS = {"youth": 0.9, "thin": 0.2, "squat": 0.4}
YOUTH_HALF_LIFE_DAYS = 30.0
THRESHOLDS = {"ask": 0.5, "note": 0.25}
TIMEOUT_SECONDS = 2.5
MAX_PACKAGES = 8  # probed per command; the rest are noted, not guessed
CACHE_SECONDS = 6 * 3600
CACHE_MAX = 2000
# A packument this large has thousands of release files: an old package. Its age is not
# read (missing evidence, never a signal), so a huge download is never waited for.
MAX_BODY_BYTES = 4 * 1024 * 1024
USER_AGENT = "mizan-wara/1"
DAY = 86400.0

# The most downloaded names of each registry (PyPI: pypistats/top-pypi-packages; npm: the
# npm "most depended upon" list), for the typosquat comparison. A name that IS one of
# these is never a squat of another.
POPULAR: dict[str, frozenset[str]] = {
    "pypi": frozenset(
        """
        boto3 botocore urllib3 requests setuptools certifi charset-normalizer idna
        typing-extensions python-dateutil s3transfer packaging aiobotocore six numpy
        pyyaml s3fs fsspec pip cryptography grpcio-status google-api-core pydantic cffi
        attrs pycparser pandas importlib-metadata jmespath protobuf rsa pyasn1 wheel
        click platformdirs zipp markupsafe jinja2 tomli pytz filelock virtualenv
        pydantic-core pluggy pytest colorama awscli googleapis-common-protos sqlalchemy
        wrapt pyjwt jsonschema tzdata psutil pyarrow aiohttp httpx yarl multidict
        frozenlist aiosignal greenlet pyparsing pygments requests-oauthlib oauthlib
        werkzeug flask django fastapi uvicorn starlette gunicorn redis celery scipy
        matplotlib scikit-learn pillow tqdm beautifulsoup4 lxml openpyxl docutils
        tensorflow torch torchvision transformers tokenizers huggingface-hub openai
        anthropic langchain tiktoken regex rich typer black isort flake8 mypy ruff
        pylint coverage pytest-cov tox poetry pre-commit sphinx paramiko pymysql
        psycopg2 psycopg2-binary pymongo elasticsearch selenium playwright websockets
        simplejson ujson orjson httplib2 grpcio google-auth cachetools decorator
        networkx sympy nltk spacy keras xgboost lightgbm opencv-python seaborn plotly
        dash streamlit gradio arrow pendulum faker hypothesis mock responses
        """.split()
    ),
    "npm": frozenset(
        """
        lodash react react-dom chalk commander express axios debug tslib moment
        request prop-types uuid fs-extra async bluebird vue typescript webpack
        babel-core yargs glob minimist dotenv semver classnames rxjs jquery underscore
        body-parser colors mkdirp inquirer core-js eslint prettier jest mocha chai
        next nuxt svelte angular preact redux react-redux zod yup ajv joi
        socket.io ws node-fetch cross-env rimraf nodemon ts-node esbuild vite rollup
        postcss autoprefixer tailwindcss sass less styled-components graphql
        apollo-server mongoose sequelize mysql pg redis ioredis jsonwebtoken bcrypt
        bcryptjs passport cors helmet morgan multer cookie-parser nanoid date-fns
        dayjs luxon immer zustand mobx three d3 chart.js puppeteer playwright
        cheerio jsdom marked highlight.js sharp winston pino bunyan dotenv-expand
        typeorm prisma knex koa fastify hapi nestjs electron yarn pnpm npm
        """.split()
    ),
}


def enabled() -> bool:
    return os.getenv("MIZAN_WARA", "on").strip().lower() not in {"off", "0", "false", "no"}


# ── Which registry packages a command line would fetch ─────────────────────

_PYPI_VALUE_FLAGS = frozenset(
    "-r --requirement -c --constraint -e --editable -i --index-url --extra-index-url -f "
    "--find-links -t --target --prefix --root --python -p --platform --python-version "
    "--implementation --abi --only-binary --no-binary --progress-bar --src "
    "--upgrade-strategy --cache-dir --trusted-host --proxy --cert --client-cert -C "
    "--config-settings --global-option --log --retries --timeout --exists-action --report "
    "--group -G --extra -E --optional --source --markers --branch --tag --rev --index "
    "--default-index --directory --project --config-file".split()
)
_PYPI_CUSTOM = frozenset(
    "-i --index-url --extra-index-url -f --find-links --index --default-index".split()
)
_NPM_VALUE_FLAGS = frozenset(
    "--registry --prefix -C --dir --filter -F -w --workspace --tag --otp --cache --userconfig "
    "--globalconfig --loglevel --cwd --modules-folder --omit --include --install-strategy "
    "--before --script-shell --node-options".split()
)
_NPM_CUSTOM = frozenset({"--registry"})
_FLAGS = {
    "pypi": (_PYPI_VALUE_FLAGS, _PYPI_CUSTOM),
    "npm": (_NPM_VALUE_FLAGS, _NPM_CUSTOM),
}
# (tool, subcommand path, ecosystem); a path step lists its alternatives.
_COMMANDS: tuple[tuple[str, tuple[tuple[str, ...], ...], str], ...] = (
    ("pip", (("install",),), "pypi"),
    ("uv", (("pip",), ("install",)), "pypi"),
    ("uv", (("add",),), "pypi"),
    ("npm", (("install", "i", "add", "in", "ins", "isntall"),), "npm"),
    ("pnpm", (("add", "install", "i"),), "npm"),
    ("yarn", (("global",), ("add",)), "npm"),
    ("yarn", (("add",),), "npm"),
)
_WRAPPERS = frozenset({"sudo", "doas", "env", "command", "exec", "time", "nohup", "nice"})
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ash"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Environment settings that point an installer at another index or registry.
_INDEX_ENV: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"^(?:PIP_(?:EXTRA_)?INDEX_URL|PIP_FIND_LINKS|UV_(?:EXTRA_|DEFAULT_)?INDEX(?:_URL)?)=",
            re.I,
        ),
        "pypi",
    ),
    (
        re.compile(
            r"^(?:npm_config_(?:@[^:=]+:)?registry|YARN_(?:NPM_)?REGISTRY(?:_SERVER)?)=", re.I
        ),
        "npm",
    ),
)


def _index_settings(words: list[str]) -> set[str]:
    """The ecosystems these ``VAR=value`` words point at another index."""
    return {eco for word in words for pattern, eco in _INDEX_ENV if pattern.match(word)}


_UNRESOLVED = re.compile(r"[$`*?]")
_PUNCT = set("();<>|&")
_NPM_NAME = re.compile(r"^(?:@[a-z0-9~-][a-z0-9._~-]*/)?[a-z0-9~-][a-z0-9._~-]*$")
_NPM_NOT_REGISTRY = re.compile(
    r"^(?:\.|/|~|file:|link:|workspace:|portal:|patch:|catalog:|git\+|git:|github:|gitlab:"
    r"|bitbucket:|gist:|https?:)|\.(?:tgz|tar\.gz|tar)$",
    re.I,
)
_PYPI_SPEC = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?:\[[^\]]*\])?\s*(.*)$")


def _tool_name(word: str) -> str:
    name = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    name = re.sub(r"\.(exe|cmd|bat)$", "", name)
    return "pip" if re.fullmatch(r"pip(?:3(?:\.\d+)?)?", name) else name


def npm_spec(raw: str) -> str | None:
    """The npm registry package one install word names, or None (a path, a URL, a git
    source, a tarball, GitHub shorthand)."""
    text = raw
    alias = text.find("@npm:")
    if alias > 0:
        text = text[alias + 5 :]
    if _NPM_NOT_REGISTRY.search(text) or "://" in text:
        return None
    at = text.rfind("@")
    name = text[:at] if at > 0 else text
    return name if _NPM_NAME.fullmatch(name) else None


def pypi_spec(raw: str) -> str | None:
    """The PyPI project one requirement names (PEP 503 normalised), or None."""
    text = raw.split(";")[0].strip()
    if re.search(r"^(?:\.|/|~)|://|^git\+|\.(?:whl|zip|tar\.gz|tar\.bz2)$", text, re.I):
        return None
    if "/" in text or "\\" in text:
        return None
    match = _PYPI_SPEC.match(text)
    if not match or match.group(2).startswith("@"):  # ``name @ https://…``
        return None
    return re.sub(r"[-_.]+", "-", match.group(1).lower())


_SPECS = {"pypi": pypi_spec, "npm": npm_spec}


def _segments(command: str) -> list[list[str]]:
    """Simple commands of a shell line, as words; redirection targets dropped."""
    text = command.replace("\\\n", " ").replace("\r", "").replace("\n", " ; ")
    # ``2>&1``: the file descriptor is part of the redirection, never an argument.
    text = re.sub(r"(?<![\w.-])\d+(?=[<>])", "", text)
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    redirect = False
    for token in lexer:
        if token and set(token) <= _PUNCT:
            if "<" in token or ">" in token:
                redirect = True
            else:
                segments.append([])
            continue
        if redirect:
            redirect = False
            continue
        segments[-1].append(token)
    return [words for words in segments if words]


def _match(tool: str, args: list[str]) -> tuple[str, list[str]] | None:
    for name, path, ecosystem in _COMMANDS:
        if tool != name:
            continue
        values = _FLAGS[ecosystem][0]
        index, matched = 0, True
        for step in path:
            while index < len(args) and args[index].startswith("-"):
                if "=" not in args[index] and args[index] in values:
                    index += 1
                index += 1
            if index >= len(args) or args[index] not in step:
                matched = False
                break
            index += 1
        if matched:
            return ecosystem, args[index:]
    return None


Found = tuple[list[tuple[str, str]], list[tuple[str, str]]]


def _from_words(words: list[str], depth: int, elsewhere_eco: set[str]) -> Found:
    """(names the public registry serves, names another index serves) of one command."""
    start = 0
    while start < len(words) and (
        _ASSIGNMENT.match(words[start])
        or _tool_name(words[start]) in _WRAPPERS
        or (
            start > 0 and _tool_name(words[start - 1]) in _WRAPPERS and words[start].startswith("-")
        )
    ):
        start += 1
    if start >= len(words):
        return [], []
    other = elsewhere_eco | _index_settings(words[:start])
    tool, args = _tool_name(words[start]), words[start + 1 :]
    if tool in _SHELLS and "-c" in args and depth < 2:
        script = args[args.index("-c") + 1 : args.index("-c") + 2]
        return _targets(script[0], depth + 1, other) if script else ([], [])
    if re.fullmatch(r"py(?:thon(?:\d(?:\.\d+)?)?)?", tool) and "-m" in args:
        at = args.index("-m")
        if args[at + 1 : at + 2] == ["pip"]:
            tool, args = "pip", args[at + 2 :]
    hit = _match(tool, args)
    if hit is None:
        return [], []
    ecosystem, rest = hit
    values, custom = _FLAGS[ecosystem]
    found: list[tuple[str, str]] = []
    off_registry = ecosystem in other
    literal, index = False, 0
    while index < len(rest):
        word = rest[index]
        index += 1
        if literal or not word.startswith("-"):
            if not _UNRESOLVED.search(word):
                name = _SPECS[ecosystem](word)
                if name:
                    found.append((ecosystem, name))
            continue
        if word == "--":
            literal = True
            continue
        flag = word.split("=", 1)[0]
        if flag in custom:
            off_registry = True  # another index: a miss on the public one proves nothing
        if "=" not in word and flag in values:
            index += 1  # the flag's value (a requirements file, a path) is no package
    return ([], found) if off_registry else (found, [])


def _targets(command: str, depth: int = 0, elsewhere_eco: set[str] | None = None) -> Found:
    try:
        segments = _segments(command)
    except ValueError:  # unbalanced quotes: nothing can be read, so nothing is vetted
        return [], []
    checked: list[tuple[str, str]] = []
    elsewhere: list[tuple[str, str]] = []
    exported = set(elsewhere_eco or ())
    for words in segments:
        # ``export PIP_INDEX_URL=…`` (or a bare ``VAR=…``) holds for the commands after it.
        settings = words[1:] if words[0] == "export" else words
        if all(_ASSIGNMENT.match(word) for word in settings):
            exported |= _index_settings(settings)
            continue
        public, other = _from_words(words, depth, exported)
        checked += [target for target in public if target not in checked]
        elsewhere += [target for target in other if target not in elsewhere]
    return checked, elsewhere


def install_targets(command: str) -> list[tuple[str, str]]:
    """Every (ecosystem, name) a shell command line would fetch from PyPI or npm:
    pip / pip3 / python -m pip / uv pip install / uv add, npm / pnpm / yarn add, install
    and i. Local paths, URLs, git sources, ``-r`` files and names built from a variable
    name nothing that can be checked; names another index serves are in
    :func:`tool_install`'s ``elsewhere``."""
    if not isinstance(command, str) or not command.strip():
        return []
    return _targets(command)[0]


@dataclass
class Install:
    """What one tool call would install: names the public registries serve (vetted) and
    names another index or registry serves (noted: a miss there proves nothing)."""

    checked: list[tuple[str, str]] = field(default_factory=list)
    elsewhere: list[tuple[str, str]] = field(default_factory=list)


# The command line each tool runs, composed exactly as the tool composes it.
_COMMAND_LINES: dict[str, Any] = {
    "bash": lambda p: str(p.get("command") or ""),
    # A program in another language is not a command line.
    "workspace_run": lambda p: (
        str(p.get("command") or "") if str(p.get("language") or "shell") == "shell" else ""
    ),
    "workspace_sandbox": lambda p: (
        str(p.get("command") or "") if p.get("action") == "serve" else ""
    ),
    "run_tests": lambda p: f"cd {p.get('path') or ''} && {p.get('framework') or 'pytest'}",
    "lint_code": lambda p: f"pylint {p.get('path') or ''}",
    "git_operation": lambda p: (
        f"cd {p.get('repo_path') or '.'} && git {p.get('operation') or ''} {p.get('args') or ''}"
    ),
}


def tool_install(tool_name: str, params: dict) -> Install:
    """What a tool call would install: ``install_package``'s package, or the packages
    the command line of a tool that runs one would fetch."""
    params = params if isinstance(params, dict) else {}
    if tool_name == "install_package":
        ecosystem = "npm" if str(params.get("manager") or "pip") == "npm" else "pypi"
        name = _SPECS[ecosystem](str(params.get("package") or ""))
        return Install([(ecosystem, name)] if name else [])
    compose = _COMMAND_LINES.get(tool_name)
    command = compose(params) if compose else ""
    if not isinstance(command, str) or not command.strip():
        return Install()
    checked, elsewhere = _targets(command)
    return Install(checked, elsewhere)


def tool_targets(tool_name: str, params: dict) -> list[tuple[str, str]]:
    """The public-registry packages of :func:`tool_install`."""
    return tool_install(tool_name, params).checked


# ── Typosquats ─────────────────────────────────────────────────────────────


def _distance(a: str, b: str, limit: int) -> int:
    """Optimal string alignment distance (a transposition is one slip), capped."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2: list[int] = []
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                current[j] = min(current[j], previous2[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
        previous2, previous = previous, current
    return previous[-1]


def close_to_popular(ecosystem: str, name: str) -> str | None:
    """The popular package this name is one slip from (two for long names), or None.
    Names shorter than four letters are close to too many others to say anything."""
    popular = POPULAR.get(ecosystem, frozenset())
    if name in popular or len(name) < 4:
        return None
    best: tuple[int, str] | None = None
    for known in popular:
        if len(known) < 5:
            continue
        limit = 1 if len(known) < 9 else 2
        slips = _distance(name, known, limit)
        if slips <= limit and (best is None or (slips, known) < best):
            best = (slips, known)
    return best[1] if best else None


# ── Evidence and judgment ──────────────────────────────────────────────────


@dataclass
class Evidence:
    """What could be verified about one package; ``None`` is "not checked", never clean."""

    exists: bool | None = None
    canonical: str | None = None
    first_published: float | None = None
    versions: int | None = None
    malicious: list[str] | None = None
    # Sources that did not answer although the registry did (OSV; the history the
    # registry's answer should hold): partial evidence is noted and never remembered.
    partial: list[str] = field(default_factory=list)


@dataclass
class Judgment:
    level: str  # refuse | ask | note | ok | unknown
    score: float = 0.0
    signals: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def judge(ecosystem: str, name: str, evidence: Evidence, now: float | None = None) -> Judgment:
    """One package's verdict from its evidence. Pure."""
    now = time.time() if now is None else now
    where = ECOSYSTEMS.get(ecosystem, {}).get("label", ecosystem)
    if evidence.exists is False:
        return Judgment("refuse", 1.0, {}, [f"is not on {where}: the name looks invented"])
    if evidence.malicious:
        return Judgment(
            "refuse", 1.0, {}, [f"is listed as malicious by OSV ({evidence.malicious[0]})"]
        )
    signals: dict[str, float] = {}
    reasons: list[str] = []
    if evidence.first_published is not None:
        days = max(0.0, (now - evidence.first_published) / DAY)
        signals["youth"] = min(1.0, 2 ** (-days / YOUTH_HALF_LIFE_DAYS))
        if days < 60:
            reasons.append(
                "first published about a day ago"
                if days < 2
                else f"first published {round(days)} days ago"
            )
    if evidence.versions:
        signals["thin"] = min(1.0, 1 / evidence.versions)
        if evidence.versions <= 2 and signals.get("youth", 0) >= 0.25:
            reasons.append(
                f"only {evidence.versions} version{'s' if evidence.versions > 1 else ''} published"
            )
    near = close_to_popular(ecosystem, name)
    if near:
        signals["squat"] = 1.0
        reasons.append(f"its name is one slip from the popular {near!r}")
    if evidence.exists is None and not signals:
        return Judgment("unknown", 0.0, {}, [f"could not be checked ({where} did not answer)"])
    clean = 1.0
    for kind, value in signals.items():
        clean *= 1 - WEIGHTS.get(kind, 0.0) * value
    score = max(0.0, min(1.0, 1 - clean))
    if evidence.exists is None:
        reasons.append(f"could not be checked ({where} did not answer)")
    if "history" in evidence.partial:
        reasons.append(
            "its age and versions could not be read (the registry's answer was too large or not JSON)"
        )
    if "OSV" in evidence.partial:
        reasons.append("could not be fully checked (OSV did not answer)")
    level = "ask" if score >= THRESHOLDS["ask"] else "note" if score >= THRESHOLDS["note"] else "ok"
    if evidence.partial and level == "ok":
        level = "note"  # missing evidence: allowed, and said
    if evidence.exists is None and level == "ask":
        level = "note"  # never ask on what could not be checked
    return Judgment(level, round(score, 3), {k: round(v, 3) for k, v in signals.items()}, reasons)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )


async def _get_json(client: httpx.AsyncClient, url: str) -> tuple[int, Any]:
    """Status and parsed body (None when too large or not JSON)."""
    async with client.stream("GET", url) as response:
        if response.status_code != 200:
            return response.status_code, None
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                return 200, None
    try:
        return 200, json.loads(bytes(body))
    except ValueError:
        return 200, None


def _when(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


async def probe(ecosystem: str, name: str, client: httpx.AsyncClient) -> Evidence:
    """Gather one package's evidence. Never raises: a source that fails leaves its
    fields unknown."""
    evidence = Evidence()
    if ecosystem == "pypi":
        url = f"https://pypi.org/pypi/{quote(name, safe='')}/json"
    else:
        url = f"https://registry.npmjs.org/{quote(name, safe='@')}"
    try:
        status, doc = await asyncio.wait_for(_get_json(client, url), TIMEOUT_SECONDS * 2)
    except (httpx.HTTPError, TimeoutError, OSError):
        return evidence
    if status in (404, 410):
        evidence.exists = False
        return evidence
    if status != 200:
        return evidence
    evidence.exists = True
    if isinstance(doc, dict):
        if ecosystem == "pypi":
            evidence.canonical = str((doc.get("info") or {}).get("name") or name)
            releases = doc.get("releases") or {}
            times = [
                stamp
                for files in releases.values()
                for item in (files or [])
                if (stamp := _when(item.get("upload_time_iso_8601") or item.get("upload_time")))
            ]
            evidence.versions = sum(1 for files in releases.values() if files) or None
            evidence.first_published = min(times) if times else None
        else:
            evidence.canonical = name
            evidence.first_published = _when((doc.get("time") or {}).get("created"))
            evidence.versions = len(doc.get("versions") or {}) or None
    else:
        evidence.partial.append("history")  # too large to read, or not JSON
    # Only a name its registry has is told to OSV (never a typo or a private name).
    try:
        response = await asyncio.wait_for(
            client.post(
                "https://api.osv.dev/v1/query",
                json={
                    "package": {
                        "name": evidence.canonical or name,
                        "ecosystem": ECOSYSTEMS[ecosystem]["osv"],
                    }
                },
            ),
            TIMEOUT_SECONDS * 2,
        )
        if response.status_code == 200:
            vulns = response.json().get("vulns") or []
            evidence.malicious = [
                str(item.get("id"))
                for item in vulns
                if str(item.get("id", "")).upper().startswith("MAL-")
            ]
        else:
            evidence.partial.append("OSV")
    except (httpx.HTTPError, TimeoutError, OSError, ValueError):
        evidence.partial.append("OSV")
    return evidence


@dataclass
class Verdict:
    decision: str  # refuse | ask | allow
    reason: str = ""
    notes: list[str] = field(default_factory=list)
    packages: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_cache: dict[tuple[str, str], tuple[float, Judgment]] = {}


def clear_cache() -> None:
    _cache.clear()


def _label(ecosystem: str, name: str) -> str:
    return f"{name} ({ECOSYSTEMS[ecosystem]['label']})"


async def vet(
    targets: list[tuple[str, str]],
    *,
    elsewhere: list[tuple[str, str]] | tuple = (),
    now: float | None = None,
) -> Verdict:
    """The verdict for the packages one command would install: the worst package
    decides. ``elsewhere`` are names another index serves: never asked of a public
    registry (a miss there proves nothing, and a private name stays private), only
    noted. Never raises."""
    wanted = [(eco, name) for eco, name in dict.fromkeys(targets) if eco in ECOSYSTEMS]
    notes: list[str] = [
        f"{_label(eco, name)} is installed from another index, so it was not checked "
        "against the public registry"
        for eco, name in dict.fromkeys(elsewhere)
        if eco in ECOSYSTEMS
    ]
    if not wanted:
        return Verdict("allow", "", notes)
    stamp = time.monotonic()
    judged: dict[tuple[str, str], Judgment] = {}
    to_probe: list[tuple[str, str]] = []
    for target in wanted:
        cached = _cache.get(target)
        if cached and cached[0] > stamp:
            judged[target] = cached[1]
        else:
            to_probe.append(target)
    if len(to_probe) > MAX_PACKAGES:
        notes.append(f"{len(to_probe) - MAX_PACKAGES} more package(s) were not checked")
        to_probe = to_probe[:MAX_PACKAGES]
    if to_probe:
        try:
            async with _client() as client:
                found = await asyncio.gather(
                    *(probe(eco, name, client) for eco, name in to_probe), return_exceptions=True
                )
        except Exception:  # noqa: BLE001 - a broken client is missing evidence, not a block
            logger.warning("Wara': the registries could not be asked", exc_info=True)
            found = [Evidence() for _ in to_probe]
        for target, evidence in zip(to_probe, found, strict=True):
            if not isinstance(evidence, Evidence):
                evidence = Evidence()
            judgment = judge(target[0], target[1], evidence, now)
            judged[target] = judgment
            # What could not be checked, wholly or in part, is asked again next time.
            if evidence.exists is not None and not evidence.partial:
                if len(_cache) >= CACHE_MAX:
                    _cache.pop(next(iter(_cache)))
                _cache[target] = (stamp + CACHE_SECONDS, judgment)
    rank = {"refuse": 0, "ask": 1, "note": 2, "unknown": 2, "ok": 3}
    ordered = sorted(judged.items(), key=lambda item: rank[item[1].level])
    packages = [
        {"ecosystem": eco, "name": name, **asdict(judgment)} for (eco, name), judgment in ordered
    ]

    def lines(level: str) -> str:
        return " | ".join(
            f"{_label(eco, name)} {'; '.join(j.reasons)}"
            for (eco, name), j in ordered
            if j.level == level
        )

    worst = ordered[0][1].level
    if worst == "refuse":
        return Verdict(
            "refuse",
            f"Wara': {lines('refuse')}. A package that does not exist (or is known to be "
            "malicious) is how a squatted name gets installed: find the real package in "
            "the registry or the library's own documentation first.",
            notes,
            packages,
        )
    if worst == "ask":
        return Verdict(
            "ask",
            f"Wara': {lines('ask')}. A new, thin package with a name close to a popular "
            "one is the usual shape of a squatted name: confirm this is the package you mean.",
            notes,
            packages,
        )
    for (eco, name), judgment in ordered:
        if judgment.level in {"note", "unknown"}:
            notes.append(f"{_label(eco, name)} {'; '.join(judgment.reasons)}")
    return Verdict("allow", "", notes, packages)


def summary(verdict: Verdict) -> dict:
    """What a tool result carries about its vetting (no network detail)."""
    return {
        "decision": verdict.decision,
        **({"reason": verdict.reason} if verdict.reason else {}),
        **({"notes": verdict.notes} if verdict.notes else {}),
        "packages": [
            {key: item[key] for key in ("ecosystem", "name", "level", "score", "reasons")}
            for item in verdict.packages
        ],
    }
