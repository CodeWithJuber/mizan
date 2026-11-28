"""Encrypt connector secrets (headers, env values, OAuth tokens) at rest.

The same data key seals the other secrets MIZAN keeps (runtime settings, Sakk
signing keys, the Web Push key).

Fernet keys come from ``MIZAN_CONNECTORS_KEY`` when it is set: a comma-separated
list, the first key encrypts and every key decrypts (``MultiFernet``), so a key is
rotated by putting the new one first and keeping the old one until every value
has been sealed again. ``$MIZAN_DATA_DIR/connectors.key`` (mode 0600), when it
exists, also still decrypts. Without the variable that file is the key, created
on first use. Keys are read once and cached until the variable or the file
changes.

A value that no configured key opens is never silently replaced: ``unseal``
logs it loudly, and with ``strict=True`` raises :class:`SecretsUnreadable`, so a
connector says "secrets cannot be decrypted" instead of acting as if it had no
headers or tokens.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

logger = logging.getLogger("mizan.connectors.secrets")

_LOCK = threading.Lock()
_cache: tuple[tuple, MultiFernet] | None = None
_reported: set[str] = set()
ENV_KEY = "MIZAN_CONNECTORS_KEY"


class SecretsUnreadable(RuntimeError):
    """A sealed value no configured key decrypts (the key changed or was lost)."""

    code = "secrets_unreadable"

    def __init__(self) -> None:
        super().__init__(
            "Saved secrets cannot be decrypted: connectors.key (or MIZAN_CONNECTORS_KEY) "
            "changed? Restore the old key, or enter the secrets again"
        )


def _key_path() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data")) / "connectors.key"


def _file_keys(path: Path) -> list[bytes]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = Fernet.generate_key()
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass  # another process created it first
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(key)
    lines = path.read_bytes().split()
    return [line.strip() for line in lines if line.strip()]


def _fernet() -> MultiFernet:
    global _cache
    configured = os.getenv(ENV_KEY, "").strip()
    path = _key_path()
    with _LOCK:
        if configured:
            try:
                info = path.stat()
                stamp: tuple = ("env", configured, info.st_mtime_ns, info.st_size)
            except OSError:
                stamp = ("env", configured, None, None)
        else:
            try:
                info = path.stat()
                stamp = ("file", str(path), info.st_mtime_ns, info.st_size)
            except OSError:
                stamp = ("file", str(path), None, None)
        if _cache is not None and _cache[0] == stamp:
            return _cache[1]
        if configured:
            keys = [key.strip().encode() for key in configured.split(",") if key.strip()]
            # The key file, when there is one, still opens what it sealed (decrypt
            # only: the first configured key seals), so moving to the variable never
            # locks out values sealed before. Delete the file to retire that key.
            with contextlib.suppress(OSError):
                if path.exists():
                    keys += [key for key in path.read_bytes().split() if key and key not in keys]
        else:
            keys = _file_keys(path)
            info = path.stat()
            stamp = ("file", str(path), info.st_mtime_ns, info.st_size)
        if not keys:
            raise RuntimeError(f"{ENV_KEY} is set but holds no key")
        fernet = MultiFernet([Fernet(key) for key in keys])
        _cache = (stamp, fernet)
        return fernet


def reset_cache() -> None:
    """Forget the cached key (tests, and after an operator rotates the key file)."""
    global _cache
    with _LOCK:
        _cache = None
        _reported.clear()


def seal(value: Any) -> str:
    """Encrypt a JSON-serialisable value; empty values stay empty."""
    if value in (None, "", {}, []):
        return ""
    token: str = _fernet().encrypt(json.dumps(value).encode()).decode()
    return token


def unseal(token: str, default: Any = None, *, strict: bool = False) -> Any:
    """Decrypt a sealed value. A value no key opens is logged as an error (once per
    value) and, with ``strict``, raises :class:`SecretsUnreadable`."""
    if not token:
        return default
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        digest = hashlib.sha256(token.encode()).hexdigest()[:12]
        if digest not in _reported:
            _reported.add(digest)
            logger.error(
                "A sealed secret (%s) cannot be decrypted with the configured key: "
                "connectors.key or %s changed or was lost",
                digest,
                ENV_KEY,
            )
        if strict:
            raise SecretsUnreadable() from None
        return default


def reseal(token: str) -> str:
    """The same value sealed with the current first key (after a rotation)."""
    if not token:
        return token
    rotated: str = _fernet().rotate(token.encode()).decode()
    return rotated
