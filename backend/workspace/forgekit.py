"""ForgeKit in the sandbox: the one command MIZAN runs there, and what its JSON says.

The workspace runtime image carries ForgeKit (``@codewithjuber/forgekit``, pinned to
``FORGEKIT_VERSION`` in docker/Dockerfile.workspace-runtime). MIZAN runs ``forge verify``,
``forge impact`` or ``forge docs sync`` with ``--json`` inside the project's sandbox (its
live session, or a one-shot run that copies nothing back) and reads the answer here. The
functions are pure: they build the shell command and read its output, nothing else.

What the command guarantees:

- ForgeKit, node, python, git and timeout are called by their paths in the image, so a
  project's own ``node_modules/.bin`` never answers for them; an image without ForgeKit
  says ``missing`` (a runner older than this change).
- ForgeKit's own state (``.forge/``: its atlas cache, provenance stamp, verifier events) is
  put back exactly as it was afterwards, so a check changes none of the project's files; a
  project that keeps a ``.forge`` of its own (ForgeKit's config) keeps it byte for byte.
- ``forge verify`` binds its verdict to a git state. A project without git is verified
  against a throwaway snapshot commit kept under ``.cache/`` (never synced): its tests run
  and the verdict is bound, but ForgeKit's test-integrity check has no earlier state to
  compare with. ``docs sync`` needs the project's own history and says so without it.
- ForgeKit runs under ``timeout`` shorter than the run's own limit, so ``.forge`` is put
  back even when the tests hang.
- The answer is a marker line with a fresh random mark, then ForgeKit's JSON trimmed inside
  the container (long strings and lists cut), so a large report still fits the run's
  output and no test output can pose as MIZAN's marker.

The verdict is what the project's own tests report in its sandbox: evidence, not a proof
against a test suite written to lie (tests are the project's code and run with its
rights there).
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Any

from .session_agent import HEAVY

FORGEKIT_VERSION = "1.26.0"
FORGE = "/usr/local/bin/forge"
NODE = "/usr/local/bin/node"
PYTHON = "/usr/local/bin/python3"
# Coreutils and git from the image too: the session PATH puts the project's own
# node_modules/.bin first, and these two write what MIZAN reads.
TIMEOUT = "/usr/bin/timeout"
GIT = "/usr/bin/git"
MISSING = "ForgeKit is not installed in this sandbox image; the runner needs upgrading"
NO_GIT = (
    "This project has no git history to compare the changes with: run workspace_git "
    "action=init and action=commit once, then check again after the next change"
)
VERDICTS = frozenset({"PASS", "FAIL", "INCOMPLETE", "NOT_CONFIGURED", "SUSPECT"})
# The manifests ForgeKit plans a test suite from (verify.js PACKAGE_MANIFESTS): without one
# it answers NOT_CONFIGURED, so MIZAN does not ask for a run that cannot find tests.
MANIFESTS = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "setup.py",
        "pytest.ini",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Gemfile",
        "composer.json",
    }
)
GIT_MODES = ("any", "snapshot", "require")
_MARK = re.compile(r"[0-9a-f]{16,64}")
_SYMBOL = re.compile(r"[A-Za-z_$][\w$]*(?:[.#:][A-Za-z_$][\w$]*)*")
_COUNTS = ("total", "pass", "fail", "skipped")
# Trims ForgeKit's JSON inside the container: ``added`` (every added line of the diff) is
# dropped, strings keep their first 1000 and last 3000 characters, lists their first 300.
_TRIM = (
    "import json, sys\n"
    "def t(v):\n"
    "    if isinstance(v, str):\n"
    "        return v if len(v) <= 4000 else v[:1000] + ' … ' + v[-3000:]\n"
    "    if isinstance(v, list):\n"
    "        return [t(x) for x in v[:300]]\n"
    "    if isinstance(v, dict):\n"
    "        return {k: t(x) for k, x in v.items() if k != 'added'}\n"
    "    return v\n"
    "try:\n"
    "    data = json.load(open(sys.argv[1], encoding='utf-8'))\n"
    "except (OSError, ValueError):\n"
    "    data = {}\n"
    "print(json.dumps(t(data), ensure_ascii=False))\n"
)


class ForgeKitError(Exception):
    """A typed refusal: ``code`` names it, ``message`` is safe to show."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def result(self) -> dict:
        return {"error": self.message, "code": self.code}


def needs_tests(paths: list[str] | set[str]) -> bool:
    """A project ForgeKit could find a test suite in (one of its manifests)."""
    return any(str(path).rsplit("/", 1)[-1] in MANIFESTS for path in paths)


def command(args: list[str], mark: str, *, git: str = "any", limit: int = 110) -> str:
    """The shell script that runs ``forge <args> --json`` in the project directory.

    ``git``: ``snapshot`` makes a throwaway baseline commit when the project has no git,
    ``require`` refuses (``nogit``) without one, ``any`` runs either way. ``limit`` is
    ForgeKit's own time limit in seconds, below the run's, so the cleanup always runs.
    """
    if git not in GIT_MODES:
        raise ValueError(f"git must be one of {GIT_MODES}")
    if not _MARK.fullmatch(mark):
        raise ValueError("mark must be 16-64 lowercase hex characters")
    if not args or any(not isinstance(arg, str) or not arg for arg in args):
        raise ValueError("ForgeKit needs a command")
    marker = shlex.quote(f"@@mizan-forge-{mark}")
    state = shlex.quote(f".cache/mizan-forge/{mark}")
    forge = " ".join(shlex.quote(arg) for arg in args)
    ignored = " ".join(shlex.quote(f"{name}/") for name in sorted(HEAVY | {".forge"}))
    lines = [
        f"M={marker}",
        f'if [ ! -x {FORGE} ] || [ ! -x {NODE} ]; then echo "$M missing"; exit 0; fi',
    ]
    if git == "require":
        lines.append('if [ ! -e .git ]; then echo "$M nogit"; exit 0; fi')
    lines += [
        f"S={state}",
        'mkdir -p "$S" || exit 1',
        # ForgeKit writes its state into .forge: keep a copy to put back afterwards.
        'if [ -e .forge ] || [ -L .forge ]; then cp -a .forge "$S/kept" || exit 1; fi',
        "B=project",
    ]
    if git == "snapshot":
        lines += [
            "if [ ! -e .git ]; then",
            "  B=snapshot",
            '  GIT_DIR="$PWD/$S/git"; GIT_WORK_TREE="$PWD"; export GIT_DIR GIT_WORK_TREE',
            f'  {{ {GIT} init -q && mkdir -p "$GIT_DIR/info" &&'
            f" printf '%s\\n' {ignored} > \"$GIT_DIR/info/exclude\" && {GIT} add -A &&"
            f" {GIT} -c user.name=MIZAN -c user.email=verify@mizan.invalid commit -q --no-verify"
            " --allow-empty -m 'MIZAN snapshot'; } >/dev/null 2>&1 || B=none",
            "fi",
        ]
    lines += [
        f"FORGE_HOOKS=0 FORGE_LLM=0 {TIMEOUT} -k 5 {max(10, int(limit))} {NODE} {FORGE} {forge}"
        ' --json > "$S/out.json" 2> "$S/err.txt"; C=$?',
        "rm -rf .forge",
        'if [ -e "$S/kept" ] || [ -L "$S/kept" ]; then mv "$S/kept" .forge; fi',
        'echo "$M exit $C baseline $B"',
        f'{PYTHON} -I -c {shlex.quote(_TRIM)} "$S/out.json" || echo "{{}}"',
        'echo "$M stderr"',
        'tail -c 2000 "$S/err.txt"',
        'rm -rf "$S"',
        # Only folders this command made and left empty; a project's own .cache stays.
        "rmdir .cache/mizan-forge .cache 2>/dev/null",
        "exit 0",
    ]
    return "\n".join(lines)


def read(stdout: str, mark: str) -> tuple[dict, int, str]:
    """(ForgeKit's JSON, its exit code, the baseline) from the command's output."""
    prefix = f"@@mizan-forge-{mark}"
    lines = (stdout or "").splitlines()
    head = next((i for i, line in enumerate(lines) if line.startswith(prefix + " ")), None)
    if head is None:
        raise ForgeKitError("no_answer", "ForgeKit did not answer in the sandbox")
    words = lines[head][len(prefix) + 1 :].split()
    if words[:1] == ["missing"]:
        raise ForgeKitError("forgekit_missing", MISSING)
    if words[:1] == ["nogit"]:
        raise ForgeKitError("no_git", NO_GIT)
    if len(words) != 4 or words[0] != "exit" or words[2] != "baseline" or not words[1].isdigit():
        raise ForgeKitError("no_answer", "ForgeKit did not answer in the sandbox")
    code, baseline = int(words[1]), words[3]
    end = next((i for i in range(head + 1, len(lines)) if lines[i] == f"{prefix} stderr"), None)
    body = "\n".join(lines[head + 1 : end]).strip()
    if code in (124, 137):
        raise ForgeKitError("timeout", "ForgeKit did not finish within the sandbox's time limit")
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    if not isinstance(data, dict) or not data:
        errors = "\n".join(lines[end + 1 :]).strip() if end is not None else ""
        reason = f": {errors[-300:]}" if errors else ""
        raise ForgeKitError("bad_answer", f"ForgeKit's answer could not be read{reason}")
    return data, code, baseline


def _count(value: Any) -> int:
    number = _int(value)
    return number if number is not None and number >= 0 else 0


def _counts(reported: Any) -> dict[str, int] | None:
    if not isinstance(reported, dict):
        return None
    return {key: _count(reported.get(key)) for key in _COUNTS}


def _text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def verification(data: dict) -> dict:
    """What ``forge verify --json`` found: the verdict, each suite it ran, their counts."""
    tests = _dict(data.get("tests"))
    verdict = str(tests.get("status") or "")
    if verdict not in VERDICTS:
        raise ForgeKitError("bad_answer", "ForgeKit's verdict could not be read")
    commands: list[dict[str, Any]] = []
    reported: list[dict[str, int]] = []
    for suite in tests.get("executed") or []:
        if not isinstance(suite, dict):
            continue
        counted = _counts(suite.get("reportedCounts"))
        if counted:
            reported.append(counted)
        commands.append(
            {
                "command": _text(suite.get("label"), 200),
                "cwd": _text(suite.get("cwd") or ".", 200),
                "status": _text(suite.get("status"), 40),
                "exit_code": _int(suite.get("exitCode")),
                "duration_ms": _int(suite.get("durationMs")),
                "counts": counted,
            }
        )
    counts = {key: sum(item[key] for item in reported) for key in _COUNTS} if reported else None
    missing = _dict(tests.get("notConfigured"))
    detail = tests.get("output") or missing.get("detail") or missing.get("reason") or ""
    provenance = _dict(data.get("provenance"))
    state, event = _dict(provenance.get("codeState")), _dict(provenance.get("event"))
    return {
        "verdict": verdict,
        "passed": verdict == "PASS",
        "has_tests": verdict != "NOT_CONFIGURED",
        "commands": commands,
        "counts": counts,
        "not_run": [_text(item, 200) for item in tests.get("notExecuted") or []][:20],
        "detail": _text(detail, 3000),
        "test_integrity": _text(_dict(data.get("testIntegrity")).get("status"), 40),
        "mutated": bool(tests.get("mutated")),
        "forge": {
            "version": _text(event.get("verifierVersion"), 40),
            "head": _str(state.get("head")),
            "dirty_hash": _str(state.get("dirtyHash")),
            "scheme": _text(state.get("scheme"), 40),
        },
    }


def _paths(values: Any, limit: int) -> list[str]:
    return [_text(item, 512) for item in (values or []) if isinstance(item, str)][:limit]


def impact(data: dict, limit: int = 200) -> dict:
    """The files ``forge impact <target> --json`` predicts an edit will touch."""
    if not isinstance(data.get("impactedFiles"), list):
        raise ForgeKitError("bad_answer", "ForgeKit's impact report could not be read")
    files = _paths(data["impactedFiles"], limit)
    return {
        "target": _text(data.get("target"), 200),
        "found": data.get("found") is True,
        "defined_in": _paths(data.get("definedIn"), 50),
        "direct": _paths(data.get("directFiles"), limit),
        "files": files,
        "hops": {
            str(hop): _count(count)
            for hop, count in dict(data.get("hops") or {}).items()
            if str(hop).isdigit()
        },
        "truncated": len(data["impactedFiles"]) > len(files),
        "graph": {
            "nodes": _count(data.get("totalGraphNodes")),
            "edges": _count(data.get("totalGraphEdges")),
            "capped": data.get("capped") is True,
        },
    }


def docs(data: dict, limit: int = 50) -> dict:
    """The docs ``forge docs sync --json`` finds stale after the changes since git's HEAD."""
    if data.get("error"):
        if str(data["error"]).startswith("unknown base ref"):
            raise ForgeKitError("no_git", NO_GIT)  # git init without a first commit
        raise ForgeKitError("bad_answer", _text(data["error"], 300))
    if not isinstance(data.get("stale"), list):
        raise ForgeKitError("bad_answer", "ForgeKit's docs report could not be read")
    stale = []
    for entry in data["stale"][:limit]:
        if not isinstance(entry, dict):
            continue
        hits = [
            {
                "identifier": _text(hit.get("identifier"), 200),
                "line": _count(hit.get("line")),
                "text": _text(hit.get("text"), 200),
            }
            for hit in entry.get("hits") or []
            if isinstance(hit, dict)
        ][:20]
        stale.append(
            {"file": _text(entry.get("file"), 512), "hits": hits}
            | ({"note": _text(entry["note"], 200)} if entry.get("note") else {})
        )
    return {
        "base": _text(data.get("base"), 80),
        "changed_files": _paths(data.get("changedFiles"), 200),
        "identifiers": _paths(data.get("identifiers"), 100),
        "stale": stale,
        "updated": [
            _text(entry.get("file"), 512)
            for entry in data.get("updated") or []
            if isinstance(entry, dict)
        ][:limit],
        "unaffected": len(data.get("unaffected") or []),
    }


def impact_args(symbol: str | None, path: str | None) -> list[str]:
    """``impact <target>`` for exactly one of a symbol or a project path, checked."""
    from .store import parts

    symbol, path = (symbol or "").strip(), (path or "").strip()
    if bool(symbol) == bool(path):
        raise ForgeKitError("invalid", "Give exactly one of symbol or path")
    if symbol:
        if len(symbol) > 200 or not _SYMBOL.fullmatch(symbol):
            raise ForgeKitError("invalid", "symbol must be a name such as total or Cart.add")
        return ["impact", symbol]
    if path.startswith("-"):
        raise ForgeKitError("invalid", "path must be a project path")
    try:
        parts(path)
    except Exception:  # noqa: BLE001 - the store's own path rule, reported as typed
        raise ForgeKitError("invalid", "path must be a relative project path") from None
    return ["impact", path]
