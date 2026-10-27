"""Hugging Face Hub, read by MIZAN itself.

MIZAN's code sandbox has no network by design, so a program it runs cannot
download a dataset. MIZAN reads the Hub on the server instead, read-only, and
puts what is needed into the user's project for the program to use:

- ``repos``: a user's or organisation's datasets, models or spaces
- ``files``: a repository's files and their sizes
- ``preview``: a dataset's first rows (the Hub's dataset viewer)
- ``fetch``: one file; a text file larger than the project limit is cut to its
  first whole rows (a sample), and the reply says so

Only huggingface.co and its file servers (``*.hf.co``) are contacted, and
every redirect is checked. The token (``HF_TOKEN`` in System settings, sealed)
is used only for administrators, so a user can never read the owner's private
repositories through MIZAN; nothing here writes to the Hub.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import httpx

BASE = "https://huggingface.co"
VIEWER = "https://datasets-server.huggingface.co"
KINDS = ("datasets", "models", "spaces")
_REPO = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[A-Za-z0-9][\w.-]{0,95}$")
_OWNER = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}$")
_REVISION = re.compile(r"^[\w.-]{1,80}$")
TEXT_SUFFIXES = (".jsonl", ".json", ".csv", ".tsv", ".txt", ".md", ".py", ".yaml", ".yml")
# A Hub address in the user's words: huggingface.co/datasets/owner/name, /owner/name, /owner.
LINK = re.compile(
    r"https?://(?:www\.)?(?:huggingface\.co|hf\.co)/(?:(datasets|spaces)/)?"
    r"([A-Za-z0-9][\w.-]{0,95})(?:/([A-Za-z0-9][\w.-]{0,95}))?"
    r"(?:/(?:blob|resolve|tree)/([\w.-]{1,80})/([^\s?#]+))?",
    re.IGNORECASE,
)


class HubError(RuntimeError):
    pass


def host_allowed(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return host in {"huggingface.co", "hf.co"} or host.endswith((".huggingface.co", ".hf.co"))


def token() -> str | None:
    """The owner's token, for administrators only (never a user's request)."""
    from security.auth import request_has_role

    value = os.getenv("HF_TOKEN", "").strip()
    return value if value and request_has_role("admin") else None


def _client(timeout: float = 30.0) -> httpx.AsyncClient:
    headers = {"User-Agent": "MIZAN-hub/1.0"}
    if secret := token():
        headers["Authorization"] = f"Bearer {secret}"

    async def guard(request: httpx.Request) -> None:
        if request.url.scheme != "https" or not host_allowed(request.url.host):
            raise HubError(f"MIZAN reads only from Hugging Face, not {request.url.host}")

    # httpx drops Authorization on a redirect to another host (the Hub's file servers).
    return httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=headers, event_hooks={"request": [guard]}
    )


def _kind(kind: str) -> str:
    value = (kind or "datasets").lower().rstrip("s") + "s"
    if value not in KINDS:
        raise HubError("kind must be datasets, models or spaces")
    return value


def _repo(repo: str) -> str:
    repo = (repo or "").strip().strip("/")
    if not _REPO.fullmatch(repo):
        raise HubError("A repository is owner/name, for example Zubairshaikh/mizan-eval-v1")
    return repo


def _path(path: str) -> str:
    path = (path or "").strip().lstrip("/")
    if not path or ".." in path.split("/") or len(path) > 300:
        raise HubError("A file path inside the repository is required")
    return path


def file_url(repo: str, path: str, kind: str = "datasets", revision: str = "main") -> str:
    kind, repo, path = _kind(kind), _repo(repo), _path(path)
    if not _REVISION.fullmatch(revision):
        raise HubError("Invalid revision")
    prefix = "" if kind == "models" else f"/{kind}"
    return f"{BASE}{prefix}/{repo}/resolve/{quote(revision)}/{quote(path)}"


async def _json(client: httpx.AsyncClient, url: str, params: dict | None = None) -> Any:
    response = await client.get(url, params=params)
    if response.status_code == 401 or response.status_code == 403:
        raise HubError("Hugging Face refused: the repository is private or gated")
    if response.status_code == 404:
        raise HubError("Not found on Hugging Face")
    if response.status_code >= 400:
        raise HubError(f"Hugging Face answered {response.status_code}")
    return response.json()


async def whoami() -> str | None:
    if not token():
        return None
    async with _client() as client:
        data = await _json(client, f"{BASE}/api/whoami-v2")
    return str(data.get("name") or "") or None


async def repos(owner: str = "", kind: str = "datasets", limit: int = 50) -> dict:
    kind = _kind(kind)
    owner = (owner or "").strip() or (await whoami() or "")
    if not _OWNER.fullmatch(owner):
        raise HubError("Whose repositories? Give a Hugging Face user or organisation name")
    async with _client() as client:
        items = await _json(
            client, f"{BASE}/api/{kind}", {"author": owner, "limit": max(1, min(limit, 100))}
        )
    return {
        "owner": owner,
        "kind": kind,
        "repos": [
            {
                "id": item.get("id"),
                "private": bool(item.get("private")),
                "downloads": item.get("downloads"),
                "likes": item.get("likes"),
                "updated": item.get("lastModified"),
            }
            for item in items
            if isinstance(item, dict)
        ],
    }


async def files(repo: str, kind: str = "datasets", revision: str = "main", path: str = "") -> dict:
    kind, repo = _kind(kind), _repo(repo)
    folder = "/" + quote(path.strip("/")) if path.strip("/") else ""
    async with _client() as client:
        items = await _json(
            client,
            f"{BASE}/api/{kind}/{repo}/tree/{quote(revision)}{folder}",
            {"recursive": "true"},
        )
    entries = [item for item in items if isinstance(item, dict) and item.get("type") == "file"]
    return {
        "repo": repo,
        "kind": kind,
        "files": [{"path": item.get("path"), "size": item.get("size")} for item in entries[:500]],
        "total": len(entries),
        "bytes": sum(int(item.get("size") or 0) for item in entries),
    }


async def preview(repo: str, rows: int = 5, split: str = "", config: str = "") -> dict:
    repo = _repo(repo)
    async with _client() as client:
        if not split or not config:
            splits = await _json(client, f"{VIEWER}/splits", {"dataset": repo})
            chosen = next(iter(splits.get("splits") or []), None)
            if chosen is None:
                raise HubError("The dataset viewer has no splits for this dataset")
            config, split = config or chosen["config"], split or chosen["split"]
        data = await _json(
            client, f"{VIEWER}/first-rows", {"dataset": repo, "config": config, "split": split}
        )
    found = [row.get("row") for row in data.get("rows", []) if isinstance(row, dict)]
    return {"repo": repo, "config": config, "split": split, "rows": found[: max(1, min(rows, 20))]}


async def fetch(
    repo: str,
    path: str,
    kind: str = "datasets",
    revision: str = "main",
    max_bytes: int = 1024 * 1024,
) -> dict:
    """One file's bytes; a text file over ``max_bytes`` becomes its first whole rows."""
    url = file_url(repo, path, kind, revision)
    text = path.lower().endswith(TEXT_SUFFIXES)
    body = bytearray()
    total: int | None = None
    truncated = False
    async with _client(timeout=120) as client, client.stream("GET", url) as response:
        if response.status_code in (401, 403):
            raise HubError("Hugging Face refused: the repository is private or gated")
        if response.status_code == 404:
            raise HubError(f"{path} was not found in {repo}")
        if response.status_code >= 400:
            raise HubError(f"Hugging Face answered {response.status_code}")
        length = response.headers.get("content-length")
        total = int(length) if length and length.isdigit() else None
        if total is not None and total > max_bytes and not text:
            raise HubError(
                f"{path} is {total:,} bytes, over the project limit of {max_bytes:,}; "
                "only text files can be sampled"
            )
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > max_bytes:
                truncated = True
                break
    data = bytes(body)
    if truncated:
        if not text:
            raise HubError(f"{path} is larger than the project limit of {max_bytes:,} bytes")
        data = data[:max_bytes]
        data = data[: data.rfind(b"\n") + 1] or data  # whole rows only
    return {
        "repo": repo,
        "path": path,
        "url": url,
        "bytes": data,
        "size": total,
        "sampled": truncated,
        "rows": data.count(b"\n") if text else None,
    }


def parse_link(text: str) -> dict | None:
    """A Hub address in the text, as kind, repo or owner, and file."""
    match = LINK.search(text or "")
    if not match:
        return None
    section, first, second, revision, path = match.groups()
    reserved = {"docs", "blog", "pricing", "settings", "models", "papers", "learn", "join", "login"}
    if section is None and first.lower() in reserved:
        return None
    kind = (section or "models").lower()
    if second is None:
        return {"owner": first, "kind": None}
    return {
        "repo": f"{first}/{second}",
        "kind": kind,
        "revision": revision or "main",
        "path": path,
    }
