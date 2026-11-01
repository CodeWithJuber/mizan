"""Install Agent Skills into a user's private skill directory.

Sources: a GitHub URL (repository or ``/tree/<ref>/<path>``), an uploaded
``.tar.gz``/``.zip`` archive, or a skill written in the UI. Archives are
checked member by member: regular files only (no links or devices), no
absolute or ``..`` paths, and bounded sizes and counts.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import tarfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from agent_skills.loader import NAME, SkillParseError, parse_skill_md, user_root

MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
MAX_SKILL_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_SKILL_FILES = 200
MAX_SKILLS_PER_INSTALL = 25
_GITHUB = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?"
    r"(?:/(?:tree|blob)/([A-Za-z0-9_.\-/]+?))?/?$"
)


class InstallError(ValueError):
    pass


@dataclass
class _Member:
    path: str
    data: bytes


def parse_github_url(url: str) -> tuple[str, str, list[str], str]:
    """(owner, repo, candidate refs, sub-path) from a GitHub repository URL."""
    match = _GITHUB.match(url.strip())
    if not match:
        raise InstallError("Use a https://github.com/<owner>/<repo>[/tree/<ref>/<path>] URL")
    owner, repo, rest = match.group(1), match.group(2), match.group(3) or ""
    if not rest:
        return owner, repo, ["HEAD", "main", "master"], ""
    ref, _, subpath = rest.partition("/")
    return owner, repo, [ref], subpath.removesuffix("/SKILL.md").strip("/")


async def fetch_github_archive(url: str) -> tuple[bytes, str]:
    owner, repo, refs, subpath = parse_github_url(url)
    last_status = 0
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        for ref in refs:
            archive = f"https://codeload.github.com/{owner}/{repo}/tar.gz/{ref}"
            async with client.stream("GET", archive) as response:
                last_status = response.status_code
                if response.status_code != 200:
                    continue
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_DOWNLOAD_BYTES:
                        raise InstallError("Repository archive is larger than 30 MB")
                return bytes(body), subpath
    raise InstallError(f"Could not download the repository (HTTP {last_status})")


def _safe_relative(name: str) -> str | None:
    parts = name.replace("\\", "/").split("/")
    if name.startswith("/") or any(p in {"..", ""} for p in parts[:-1]) or ".." in parts:
        return None
    return "/".join(p for p in parts if p not in {"", "."})


def _members(archive: bytes) -> list[_Member]:
    members: list[_Member] = []
    total = 0
    if archive[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode and mode != 0o100000:
                    continue  # symlinks and special files
                path = _safe_relative(info.filename)
                if path is None or info.file_size > MAX_FILE_BYTES:
                    continue
                total += info.file_size
                if total > MAX_DOWNLOAD_BYTES:
                    raise InstallError("Archive content is too large")
                members.append(_Member(path, bundle.read(info)))
        return members
    try:
        tar_bundle = tarfile.open(fileobj=io.BytesIO(archive), mode="r:*")
    except tarfile.TarError as exc:
        raise InstallError(f"Not a readable .tar.gz or .zip archive: {exc}") from None
    with tar_bundle:
        for member in tar_bundle:
            if not member.isreg():
                continue  # links, devices and directories are never extracted
            path = _safe_relative(member.name)
            if path is None or member.size > MAX_FILE_BYTES:
                continue
            total += member.size
            if total > MAX_DOWNLOAD_BYTES:
                raise InstallError("Archive content is too large")
            extracted = tar_bundle.extractfile(member)
            if extracted is not None:
                members.append(_Member(path, extracted.read()))
    return members


def _strip_common_root(members: list[_Member]) -> list[_Member]:
    """GitHub archives wrap everything in ``<repo>-<sha>/``."""
    roots = {m.path.split("/", 1)[0] for m in members if "/" in m.path}
    if len(roots) == 1 and all("/" in m.path for m in members):
        prefix = roots.pop() + "/"
        return [_Member(m.path[len(prefix) :], m.data) for m in members]
    return members


def _skill_dirs(members: list[_Member], subpath: str) -> dict[str, list[_Member]]:
    base = subpath.strip("/")
    scoped = [
        _Member(m.path[len(base) + 1 :] if base else m.path, m.data)
        for m in members
        if not base or m.path.startswith(base + "/")
    ]
    roots = sorted(
        {m.path[: -len("SKILL.md")].rstrip("/") for m in scoped if m.path.endswith("SKILL.md")}
    )
    # A SKILL.md at the sub-path itself is one skill; otherwise each folder
    # (at any depth) holding a SKILL.md is a skill.
    if "" in roots:
        roots = [""]
    skills: dict[str, list[_Member]] = {}
    for root in roots[:MAX_SKILLS_PER_INSTALL]:
        prefix = root + "/" if root else ""
        if any(other != root and root.startswith(other + "/") for other in roots):
            continue  # nested inside another skill
        skills[root or base.rsplit("/", 1)[-1]] = [
            _Member(m.path[len(prefix) :], m.data) for m in scoped if m.path.startswith(prefix)
        ]
    return skills


def _write_skill(user_id: str, directory_name: str, files: list[_Member], overwrite: bool) -> dict:
    skill_md = next((m for m in files if m.path == "SKILL.md"), None)
    if skill_md is None:
        raise InstallError("Missing SKILL.md")
    try:
        data, _body, diagnostics = parse_skill_md(
            skill_md.data.decode("utf-8", "replace"), directory_name
        )
    except SkillParseError as exc:
        raise InstallError(f"{directory_name}: {exc}") from None
    name = str(data["name"]).strip().lower()
    if not NAME.match(name) or len(name) > 64:
        name = re.sub(r"[^a-z0-9]+", "-", directory_name.lower()).strip("-")[:64]
    if not name or not NAME.match(name):
        raise InstallError(f"{directory_name}: cannot derive a valid skill name")
    if len(files) > MAX_SKILL_FILES or sum(len(m.data) for m in files) > MAX_SKILL_BYTES:
        raise InstallError(f"{name}: skills are limited to {MAX_SKILL_FILES} files and 5 MB")
    root = user_root(user_id)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / name
    if target.exists() and not overwrite:
        raise InstallError(f"A skill named {name} is already installed")
    staging = root / f".install-{uuid.uuid4().hex}"
    staging.mkdir(mode=0o700)
    try:
        for member in files:
            destination = staging.joinpath(*member.path.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(member.data)
        if target.exists():
            shutil.rmtree(target)
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"name": name, "files": len(files), "diagnostics": diagnostics}


def install_archive(
    user_id: str, archive: bytes, subpath: str = "", *, overwrite: bool = False
) -> list[dict]:
    members = _strip_common_root(_members(archive))
    skills = _skill_dirs(members, subpath)
    if not skills:
        raise InstallError("No SKILL.md found at that location")
    return [_write_skill(user_id, name, files, overwrite) for name, files in skills.items()]


def write_skill(
    user_id: str, name: str, description: str, body: str, *, overwrite: bool = False
) -> dict:
    """Create or update a user skill written in the UI."""
    if not NAME.match(name) or len(name) > 64:
        raise InstallError("Use 1-64 lowercase letters, digits and single hyphens for the name")
    if not description.strip() or len(description) > 1024:
        raise InstallError("A description of 1-1024 characters is required")
    text = f"---\nname: {name}\ndescription: {_yaml_string(description)}\n---\n\n{body.strip()}\n"
    return _write_skill(user_id, name, [_Member("SKILL.md", text.encode())], overwrite)


def _yaml_string(value: str) -> str:
    import json

    return json.dumps(" ".join(value.split()))


def delete_skill(user_id: str, name: str) -> bool:
    if not NAME.match(name):
        return False
    target = user_root(user_id) / name
    if not target.is_dir() or target.is_symlink():
        return False
    shutil.rmtree(target)
    return True


def skill_path(user_id: str, name: str) -> Path:
    path: Path = user_root(user_id) / name
    return path
