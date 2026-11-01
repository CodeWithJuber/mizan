"""Hudud (حدود): the limits a program MIZAN runs on the user's project must keep.

A program Lisan writes for a request ("count the errors in app.log and write
errors.csv") runs in the project's sandbox, and what it changes is applied back
to the project. Hudud puts a guard in front of the program, before its first
line, using Python's audit hooks (PEP 578), which a program cannot remove:

- inside the project, only the files the request names as outputs can be
  opened for writing; reading is free
- nothing inside the project is deleted, renamed or truncated
- no other program is started (``subprocess``, ``os.system``, ``os.exec*``)
  and no native library is loaded (``ctypes``), so the guard cannot be stepped
  around from Python

Writing outside the project (``/tmp``) stays allowed. The sandbox itself is the
outer wall; Hudud keeps the request's own limits inside it, so text in a file
(or a mistaken program) cannot make MIZAN change what the user did not ask for.
After the run MIZAN still checks the files the sandbox reports as changed.
"""

from __future__ import annotations

import json
import re

_FUTURE = re.compile(r"^from\s+__future__\s+import[^\n]*\n?", re.MULTILINE)

_GUARD = """\
import os as _hudud_os, sys as _hudud_sys
_HUDUD_ROOT = _hudud_os.path.realpath(_hudud_os.getcwd())
_HUDUD_WRITABLE = frozenset(
    _hudud_os.path.realpath(_hudud_os.path.join(_HUDUD_ROOT, _p)) for _p in {writable}
)
_HUDUD_WRITE_FLAGS = (
    _hudud_os.O_WRONLY | _hudud_os.O_RDWR | _hudud_os.O_CREAT | _hudud_os.O_TRUNC | _hudud_os.O_APPEND
)


def _hudud_inside(path):
    try:
        if isinstance(path, int):
            return False
        full = _hudud_os.path.realpath(_hudud_os.fsdecode(path))
    except (TypeError, ValueError):
        return True
    return full == _HUDUD_ROOT or full.startswith(_HUDUD_ROOT + _hudud_os.sep)


def _hudud_guard(event, args):
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, 0))[:3]
        writing = any(c in str(mode or "") for c in "wax+") or bool((flags or 0) & _HUDUD_WRITE_FLAGS)
        if writing and _hudud_inside(path):
            full = _hudud_os.path.realpath(_hudud_os.fsdecode(path))
            if full not in _HUDUD_WRITABLE and "__pycache__" not in full:
                raise PermissionError(
                    "MIZAN (Hudud): this request does not ask to write "
                    + _hudud_os.path.relpath(full, _HUDUD_ROOT)
                )
    elif event in {{"os.remove", "os.rmdir", "shutil.rmtree", "os.truncate", "os.rename"}}:
        targets = [a for a in args[:2] if isinstance(a, (str, bytes, _hudud_os.PathLike))]
        if any(_hudud_inside(a) for a in targets):
            raise PermissionError("MIZAN (Hudud): this request does not delete or move files")
    elif event in {{"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
                   "os.fork", "os.forkpty", "pty.spawn", "ctypes.dlopen", "ctypes.dlsym",
                   "ctypes.cdata", "ctypes.call_function"}}:
        raise PermissionError("MIZAN (Hudud): this request runs no other programs")


_hudud_sys.addaudithook(_hudud_guard)
del _hudud_guard
"""


def guard(program: str, writable: list[str]) -> str:
    """The program with Hudud's guard in front ("from __future__" lines stay first)."""
    futures = "".join(_FUTURE.findall(program))
    body = _FUTURE.sub("", program)
    names = sorted({path.strip().lstrip("./") for path in writable if path.strip()})
    prelude = _GUARD.format(writable=json.dumps(names))
    return f"{futures}{prelude}\n# ── the program ──\n{body}"


def refused(stderr: str) -> bool:
    """The run stopped because the program crossed one of the request's limits."""
    return "MIZAN (Hudud)" in (stderr or "")
