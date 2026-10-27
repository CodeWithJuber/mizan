"""Encrypt connector secrets (headers, env values, OAuth tokens) at rest.

Fernet with a key in ``$MIZAN_DATA_DIR/connectors.key`` (mode 0600), created
on first use. Ciphertext lives in the per-user connector files.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

_LOCK = threading.Lock()


def _key_path() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data")) / "connectors.key"


def _fernet() -> Fernet:
    path = _key_path()
    with _LOCK:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            key = Fernet.generate_key()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(key)
        return Fernet(path.read_bytes().strip())


def seal(value: Any) -> str:
    """Encrypt a JSON-serialisable value; empty values stay empty."""
    if value in (None, "", {}, []):
        return ""
    token: str = _fernet().encrypt(json.dumps(value).encode()).decode()
    return token


def unseal(token: str, default: Any = None) -> Any:
    if not token:
        return default
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        return default
