"""Private persistent project files; never resolve user paths against the host root."""

from __future__ import annotations

import base64
import builtins
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import HTTPException


def _limit(name: str, default: int, maximum: int) -> int:
    """Operator-tunable quota; the isolated runner must accept the same sizes."""
    try:
        value = int(os.getenv(name, "") or default)
    except ValueError:
        value = default
    return max(1, min(value, maximum))


MAX_FILE_BYTES = _limit("MIZAN_WORKSPACE_MAX_FILE_BYTES", 1024 * 1024, 8 * 1024 * 1024)
MAX_PROJECT_BYTES = _limit("MIZAN_WORKSPACE_MAX_PROJECT_BYTES", 10 * 1024 * 1024, 100 * 1024 * 1024)
MAX_FILES = _limit("MIZAN_WORKSPACE_MAX_FILES", 500, 5000)
MAX_WORKSPACES = 10


def max_workspaces() -> int:
    """Projects a user may keep (``MIZAN_WORKSPACE_MAX_PROJECTS``, 1-200, default 10),
    read on each create so an admin's change applies without a restart."""
    return _limit("MIZAN_WORKSPACE_MAX_PROJECTS", MAX_WORKSPACES, 200)


# Checkpoints: manifests of {path: sha256} over shared content-addressed objects,
# so an unchanged file costs nothing in a new checkpoint.
MAX_CHECKPOINTS = _limit("MIZAN_WORKSPACE_MAX_CHECKPOINTS", 30, 200)
MAX_CHECKPOINT_BYTES = _limit(
    "MIZAN_WORKSPACE_MAX_CHECKPOINT_BYTES", 50 * 1024 * 1024, 1024 * 1024 * 1024
)
CHECKPOINT_KINDS = ("manual", "agent", "turn", "restore")
# Git keeps its own history in the project; the file tools, quota and checkpoints
# leave it alone, and only runs (where git itself works) see it.
GIT_DIR = ".git"
# Agent search bounds (glob/grep) and line reads.
MAX_GLOB_RESULTS = 500
MAX_GREP_MATCHES = 300
MAX_GREP_PATTERN = 500
MAX_LINE_CHARS = 2000
DEFAULT_READ_LINES = 2000
_NESTED_QUANTIFIER = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*{]")
_LOCK = threading.RLock()
_ID = re.compile(r"^[0-9a-f]{32}$")


def glob_regex(pattern: str) -> re.Pattern[str]:
    """``**`` spans directories, ``*`` and ``?`` stay inside one path segment."""
    if not isinstance(pattern, str) or not pattern or len(pattern) > 300:
        raise HTTPException(422, "A glob pattern of 1..300 characters is required")
    pattern = pattern.lstrip("/")
    out, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        elif char == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                out.append(re.escape(char))
                index += 1
            else:
                body = pattern[index + 1 : end].replace("\\", "\\\\")
                out.append("[" + ("^" + body[1:] if body.startswith("!") else body) + "]")
                index = end + 1
        else:
            out.append(re.escape(char))
            index += 1
    return re.compile("".join(out) + r"\Z")


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parts(path: str) -> builtins.list[str]:
    if not isinstance(path, str) or not path or len(path) > 512:
        raise HTTPException(422, "A relative project path is required")
    result = path.split("/")
    if any(p in {"", ".", ".."} or "\\" in p or "\x00" in p for p in result):
        raise HTTPException(422, "Absolute paths, traversal and ambiguous paths are forbidden")
    return result


def entry_paths(path: str) -> set[str]:
    components = parts(path)
    return {"/".join(components[:index]) for index in range(1, len(components) + 1)}


def user_path(path: str) -> builtins.list[str]:
    """A path the file tools may change: anything but git's own folder."""
    components = parts(path)
    if components[0] == GIT_DIR:
        raise HTTPException(422, "The .git folder belongs to git; use the git tool to change it")
    return components


def replaced(
    before: str, old_string: str, new_string: str, replace_all: bool = False
) -> tuple[str, int]:
    """The text after an exact replacement and how many places changed; ambiguity
    is refused rather than guessed."""
    if not isinstance(old_string, str) or not old_string:
        raise HTTPException(422, "old_string must be non-empty exact text from the file")
    if not isinstance(new_string, str) or new_string == old_string:
        raise HTTPException(422, "new_string must differ from old_string")
    matches = before.count(old_string)
    if matches == 0:
        raise HTTPException(404, "old_string was not found; read the file and copy the exact text")
    if matches > 1 and not replace_all:
        raise HTTPException(
            409,
            f"old_string matches {matches} places; add surrounding context or set replace_all",
        )
    if replace_all:
        return before.replace(old_string, new_string), matches
    return before.replace(old_string, new_string, 1), 1


def unified(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree_digest(files: dict[str, str]) -> str:
    """One digest for a whole {path: sha256} tree, independent of order."""
    return _sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def _when(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)


class WorkspaceStore:
    def __init__(self, user_id: str):
        if not user_id:
            raise HTTPException(401, "Authentication required")
        root = Path(
            os.getenv("MIZAN_WORKSPACE_ROOT")
            or Path(os.getenv("MIZAN_DATA_DIR", "data")) / "workspaces"
        )
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root / hashlib.sha256(user_id.encode()).hexdigest()
        self.root.mkdir(exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise HTTPException(503, "Invalid workspace storage")

    def project(self, workspace_id: str) -> Path:
        if not _ID.fullmatch(workspace_id):
            raise HTTPException(404, "Workspace not found")
        path = self.root / workspace_id
        if path.is_symlink() or not path.is_dir():
            raise HTTPException(404, "Workspace not found")
        return path

    def remove(self, workspace_id: str) -> None:
        """Delete a whole project (the AGI test's throwaway projects)."""
        with _LOCK:
            shutil.rmtree(self.project(workspace_id))

    def rename_project(self, workspace_id: str, name: str) -> dict:
        name = (name or "").strip()
        if not name or len(name) > 100:
            raise HTTPException(422, "Project name must be 1..100 characters")
        with _LOCK:
            project = self.project(workspace_id)
            metadata = self._metadata(project)
            metadata["name"] = name
            metadata["updated_at"] = now()
            self._atomic_json(project / "metadata.json", metadata)
            return metadata

    def set_goal(self, workspace_id: str, goal: str) -> dict:
        """The project's stated goal (Niyyah); "" clears it, and the project chat's
        first request is the goal again."""
        goal = " ".join((goal or "").split())
        if len(goal) > 1000:
            raise HTTPException(422, "A project goal is at most 1000 characters")
        with _LOCK:
            project = self.project(workspace_id)
            metadata = self._metadata(project)
            metadata["goal"] = goal
            self._atomic_json(project / "metadata.json", metadata)
            return metadata

    def goal(self, workspace_id: str) -> str:
        with _LOCK:
            return str(self._metadata(self.project(workspace_id)).get("goal") or "")

    def export_zip(self, workspace_id: str) -> tuple[str, bytes]:
        """The project's files (not git's folder) as a zip, with the project's name."""
        with _LOCK:
            name = self._metadata(self.project(workspace_id))["name"]
            files = self.files(workspace_id)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, data in sorted(files.items()):
                archive.writestr(path, data)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "project"
        return f"{safe[:60]}.zip", buffer.getvalue()

    def list(self) -> builtins.list[dict]:
        with _LOCK:
            result = []
            for path in self.root.iterdir():
                if _ID.fullmatch(path.name) and path.is_dir() and not path.is_symlink():
                    result.append(self._metadata(path))
            return sorted(result, key=lambda item: item["updated_at"], reverse=True)

    def create(self, name: str, *, reserved: bool = False) -> dict:
        """A new project. ``reserved`` is the one Scratch project MIZAN runs plain-chat
        code in: it never counts against the user's project quota."""
        if not name or len(name) > 100:
            raise HTTPException(422, "Project name must be 1..100 characters")
        with _LOCK:
            projects = [item for item in self.list() if not item.get("reserved")]
            quota = max_workspaces()
            if not reserved and len(projects) >= quota:
                raise HTTPException(
                    413,
                    f"Workspace quota reached: {quota} projects. Delete one under "
                    "Code → Projects to create another.",
                )
            workspace_id = uuid.uuid4().hex
            path = self.root / workspace_id
            path.mkdir(mode=0o700)
            (path / "files").mkdir(mode=0o700)
            (path / "checkpoints").mkdir(mode=0o700)
            result: dict[str, Any] = {
                "id": workspace_id, "name": name, "created_at": now(), "updated_at": now(),
            }  # fmt: skip
            if reserved:
                result["reserved"] = True
            self._atomic_json(path / "metadata.json", result)
            return result

    @staticmethod
    def _atomic_json(path: Path, data: dict) -> None:
        temporary = path.parent / f".{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _metadata(project: Path) -> dict:
        fd = os.open(project / "metadata.json", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as handle:
            return cast(dict, json.load(handle))

    def _touch(self, project: Path) -> None:
        metadata = self._metadata(project)
        metadata["updated_at"] = now()
        self._atomic_json(project / "metadata.json", metadata)

    @contextmanager
    def parent(self, workspace_id: str, path: str, *, create: bool = False):
        """Use descriptor-relative traversal: concurrent symlink swaps cannot redirect I/O."""
        components = parts(path)
        fd = os.open(
            self.project(workspace_id) / "files", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            for component in components[:-1]:
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                next_fd = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                os.close(fd)
                fd = next_fd
            yield fd, components[-1]
        except (FileNotFoundError, NotADirectoryError):
            raise HTTPException(404, "Project file not found") from None
        except OSError:
            raise HTTPException(422, "Unsafe or unavailable project path") from None
        finally:
            os.close(fd)

    def read_bytes(self, workspace_id: str, path: str) -> bytes:
        with _LOCK, self.parent(workspace_id, path) as (fd, name):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                    raise HTTPException(
                        413,
                        f"Only regular project files up to {MAX_FILE_BYTES} bytes are supported",
                    )
                data = handle.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(413, f"Project file exceeds {MAX_FILE_BYTES} bytes")
                return data

    def read(self, workspace_id: str, path: str) -> dict:
        data = self.read_bytes(workspace_id, path)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "Binary file; publish it as an image artifact") from None
        return {"path": path, "content": content, "sha256": hashlib.sha256(data).hexdigest()}

    def read_lines(
        self, workspace_id: str, path: str, offset: int = 1, limit: int = DEFAULT_READ_LINES
    ) -> dict:
        """Numbered lines ``offset..offset+limit-1`` (1-based), long lines clipped."""
        document = self.read(workspace_id, path)
        lines = document["content"].splitlines()
        start = max(1, int(offset or 1))
        count = max(1, min(int(limit or DEFAULT_READ_LINES), DEFAULT_READ_LINES))
        selected = lines[start - 1 : start - 1 + count]
        numbered = "\n".join(
            f"{start + index:6d}\t{line[:MAX_LINE_CHARS]}" for index, line in enumerate(selected)
        )
        return {
            "path": path,
            "sha256": document["sha256"],
            "total_lines": len(lines),
            "start_line": start,
            "end_line": start + len(selected) - 1,
            "content": numbered,
            "truncated": start - 1 + count < len(lines),
        }

    def edit(
        self,
        workspace_id: str,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        expected_sha256: str | None = None,
    ) -> dict:
        """Replace exact text; ambiguity is refused rather than guessed."""
        with _LOCK:
            document = self.read(workspace_id, path)
            if expected_sha256 and document["sha256"] != expected_sha256:
                raise HTTPException(409, "File changed since it was read")
            before = document["content"]
            after, count = replaced(before, old_string, new_string, replace_all)
            written = self.write(workspace_id, path, after, document["sha256"])
        patch = unified(path, before, after)
        return {
            **written,
            "replacements": count,
            "diff": patch[:32_000],
            "diff_truncated": len(patch) > 32_000,
        }

    def preview_change(self, workspace_id: str, tool: str, params: dict) -> dict | None:
        """The diff an edit or write would make, without making it (for an approval
        prompt). None when the change would be refused anyway."""
        path = str(params.get("path") or "")
        try:
            user_path(path)
            try:
                before, new_file = self.read(workspace_id, path)["content"], False
            except HTTPException as exc:
                if exc.status_code != 404:
                    return None
                before, new_file = "", True
            if tool == "workspace_edit":
                after, _count = replaced(
                    before,
                    str(params.get("old_string") or ""),
                    str(params.get("new_string") or ""),
                    bool(params.get("replace_all")),
                )
            elif tool == "workspace_write":
                after = str(params.get("content") or "")
            else:
                return None
        except HTTPException:
            return None
        patch = unified(path, before, after)
        limit = 20_000
        return {
            "path": path,
            "diff": patch[:limit],
            "truncated": len(patch) > limit,
            "new_file": new_file,
        }

    def glob(self, workspace_id: str, pattern: str) -> dict:
        matcher = glob_regex(pattern)
        files = [
            entry
            for entry in self.tree(workspace_id)["files"]
            if entry["kind"] == "file" and matcher.match(entry["path"])
        ]
        return {
            "pattern": pattern,
            "files": [{"path": f["path"], "size": f["size"]} for f in files[:MAX_GLOB_RESULTS]],
            "total": len(files),
            "truncated": len(files) > MAX_GLOB_RESULTS,
        }

    def grep(
        self,
        workspace_id: str,
        pattern: str,
        path_glob: str | None = None,
        ignore_case: bool = False,
        max_matches: int = 100,
    ) -> dict:
        """Regex search over text files, bounded in pattern, lines and matches."""
        if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_GREP_PATTERN:
            raise HTTPException(422, f"A regex of 1..{MAX_GREP_PATTERN} characters is required")
        if _NESTED_QUANTIFIER.search(pattern):
            raise HTTPException(422, "Nested quantifiers like (a+)+ are not accepted")
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            raise HTTPException(422, f"Invalid regular expression: {exc}") from None
        matcher = glob_regex(path_glob) if path_glob else None
        limit = max(1, min(int(max_matches or 100), MAX_GREP_MATCHES))
        matches: builtins.list[dict] = []
        files_with_matches = 0
        for entry in self.tree(workspace_id)["files"]:
            if entry["kind"] != "file" or (matcher and not matcher.match(entry["path"])):
                continue
            try:
                data = self.read_bytes(workspace_id, entry["path"])
            except HTTPException:
                continue
            if b"\x00" in data[:8192]:
                continue  # binary
            found = False
            for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if regex.search(line[:MAX_LINE_CHARS]):
                    found = True
                    if len(matches) < limit:
                        matches.append({"path": entry["path"], "line": number, "text": line[:300]})
            files_with_matches += found
            if len(matches) >= limit:
                break
        return {
            "pattern": pattern,
            "matches": matches,
            "files_with_matches": files_with_matches,
            "truncated": len(matches) >= limit,
        }

    def tree(self, workspace_id: str, *, include_git: bool = False) -> dict:
        """Every entry, in path order. ``.git`` is left out unless a run asks for it."""
        result: builtins.list[dict] = []

        def visit(fd: int, prefix: str) -> None:
            for name in sorted(os.listdir(fd)):
                if not prefix and name == GIT_DIR and not include_git:
                    continue
                if len(result) >= MAX_FILES:
                    raise HTTPException(413, "Workspace contains too many entries")
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                path = f"{prefix}/{name}" if prefix else name
                if stat.S_ISLNK(info.st_mode) or not (
                    stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
                ):
                    raise HTTPException(422, "Symlinks and special files are forbidden in projects")
                result.append(
                    {
                        "path": path,
                        "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
                        "size": info.st_size,
                    }
                )
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        visit(child, path)
                    finally:
                        os.close(child)

        with _LOCK:
            root_fd = os.open(
                self.project(workspace_id) / "files", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                visit(root_fd, "")
            finally:
                os.close(root_fd)
        return {"files": result, "truncated": False}

    def write_bytes(
        self, workspace_id: str, path: str, data: bytes, expected_sha256: str | None = None
    ) -> dict:
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, "Project file exceeds 1 MiB")
        user_path(path)
        with _LOCK:
            entries = self.tree(workspace_id)["files"]
            existing = next((item for item in entries if item["path"] == path), None)
            if existing and existing["kind"] != "file":
                raise HTTPException(409, "A directory already exists at that path")
            if expected_sha256 is not None:
                actual = (
                    hashlib.sha256(self.read_bytes(workspace_id, path)).hexdigest()
                    if existing
                    else ""
                )
                if actual != expected_sha256:
                    raise HTTPException(409, "File changed since it was read")
            total = (
                sum(item["size"] for item in entries if item["kind"] == "file")
                - (existing["size"] if existing else 0)
                + len(data)
            )
            count = len({entry["path"] for entry in entries} | entry_paths(path))
            if total > MAX_PROJECT_BYTES or count > MAX_FILES:
                raise HTTPException(413, "Workspace storage quota reached")
            with self.parent(workspace_id, path, create=True) as (fd, name):
                temporary = f".{uuid.uuid4().hex}.tmp"
                try:
                    descriptor = os.open(
                        temporary,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=fd,
                    )
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=fd)
                    except FileNotFoundError:
                        pass
            self._touch(self.project(workspace_id))
        return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    def write(
        self, workspace_id: str, path: str, content: str, expected_sha256: str | None = None
    ) -> dict:
        return self.write_bytes(workspace_id, path, content.encode("utf-8"), expected_sha256)

    def directory(self, workspace_id: str, path: str) -> dict:
        user_path(path)
        with _LOCK:
            count = len(
                {entry["path"] for entry in self.tree(workspace_id)["files"]} | entry_paths(path)
            )
            if count > MAX_FILES:
                raise HTTPException(413, "Workspace entry quota reached")
            with self.parent(workspace_id, path, create=True) as (fd, name):
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    raise HTTPException(409, "Path already exists") from None
            self._touch(self.project(workspace_id))
            return {"path": path}

    def rename(self, workspace_id: str, path: str, new_path: str) -> dict:
        user_path(path)
        user_path(new_path)
        with _LOCK:
            entries = self.tree(workspace_id)["files"]
            existing = {entry["path"]: entry for entry in entries}
            if path not in existing:
                raise HTTPException(404, "Project file not found")
            if existing[path]["kind"] != "file":
                raise HTTPException(422, "Rename supports regular files only")
            if new_path in existing:
                raise HTTPException(409, "Target path already exists")
            count = len((existing.keys() - {path}) | entry_paths(new_path))
            if count > MAX_FILES:
                raise HTTPException(413, "Workspace entry quota reached")
            with (
                self.parent(workspace_id, path) as (source, old),
                self.parent(workspace_id, new_path, create=True) as (target, new),
            ):
                os.rename(old, new, src_dir_fd=source, dst_dir_fd=target)
            self._touch(self.project(workspace_id))
            return {"path": new_path}

    def delete(self, workspace_id: str, path: str) -> dict:
        user_path(path)
        with _LOCK, self.parent(workspace_id, path) as (fd, name):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise HTTPException(422, "Deletion supports regular files only")
            os.unlink(name, dir_fd=fd)
            self._touch(self.project(workspace_id))
        return {"deleted": True, "path": path}

    def files(self, workspace_id: str, *, include_git: bool = False) -> dict[str, bytes]:
        """Every file's bytes, within the project quota."""
        with _LOCK:
            result = {
                item["path"]: self.read_bytes(workspace_id, item["path"])
                for item in self.tree(workspace_id, include_git=include_git)["files"]
                if item["kind"] == "file"
            }
            if sum(map(len, result.values())) > MAX_PROJECT_BYTES:
                raise HTTPException(413, "Workspace storage quota reached")
            return result

    def snapshot(self, workspace_id: str, *, include_git: bool = False) -> dict[str, str]:
        return {
            path: base64.b64encode(data).decode("ascii")
            for path, data in self.files(workspace_id, include_git=include_git).items()
        }

    def snapshot_state(
        self, workspace_id: str, *, include_git: bool = True
    ) -> tuple[dict[str, str], builtins.list[str]]:
        """What a run or a sandbox session works on: files and directories, git included."""
        with _LOCK:
            return self.snapshot(workspace_id, include_git=include_git), [
                item["path"]
                for item in self.tree(workspace_id, include_git=include_git)["files"]
                if item["kind"] == "directory"
            ]

    # --- checkpoints -------------------------------------------------------

    def _checkpoint_dir(self, workspace_id: str) -> Path:
        return self.project(workspace_id) / "checkpoints"

    @staticmethod
    def _object_path(directory: Path, digest: str) -> Path:
        return directory / "objects" / digest[:2] / digest

    def _put_object(self, directory: Path, data: bytes) -> str:
        """Store bytes once under their SHA-256; an object never changes after it is written."""
        digest = _sha(data)
        target = self._object_path(directory, digest)
        if target.is_file():
            return digest
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.parent / f".{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return digest

    def _get_object(self, directory: Path, digest: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            raise HTTPException(500, "Checkpoint refers to an invalid object")
        try:
            fd = os.open(self._object_path(directory, digest), os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            raise HTTPException(410, "A file of this checkpoint is no longer stored") from None
        with os.fdopen(fd, "rb") as handle:
            data = handle.read()
        if _sha(data) != digest:
            raise HTTPException(500, "A stored checkpoint file does not match its digest")
        return data

    def _load_manifest(self, directory: Path, path: Path) -> dict:
        """Read one manifest; an old full-copy checkpoint is converted in place, keeping its
        id and date, so converting again after a crash changes nothing."""
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as handle:
            manifest = cast(dict, json.load(handle))
        if manifest.get("version") == 2:
            return manifest
        files = {
            name: self._put_object(directory, base64.b64decode(encoded))
            for name, encoded in dict(manifest.get("files") or {}).items()
        }
        upgraded = {
            "version": 2,
            "id": manifest["id"],
            "message": str(manifest.get("message") or "Project checkpoint")[:200],
            "kind": "manual",
            "created_at": manifest.get("created_at") or now(),
            "tree": _tree_digest(files),
            "files": files,
            "bytes": sum(len(base64.b64decode(v)) for v in (manifest.get("files") or {}).values()),
        }
        self._atomic_json(path, upgraded)
        return upgraded

    def _manifests(self, workspace_id: str) -> builtins.list[dict]:
        """All checkpoints of a project, newest first."""
        directory = self._checkpoint_dir(workspace_id)
        manifests = [
            self._load_manifest(directory, path)
            for path in directory.glob("*.json")
            if _ID.fullmatch(path.stem)
        ]
        return sorted(manifests, key=lambda item: _when(item["created_at"]), reverse=True)

    def _manifest(self, workspace_id: str, checkpoint_id: str) -> dict:
        if not _ID.fullmatch(checkpoint_id or ""):
            raise HTTPException(404, "Checkpoint not found")
        directory = self._checkpoint_dir(workspace_id)
        path = directory / f"{checkpoint_id}.json"
        if path.is_symlink() or not path.is_file():
            raise HTTPException(404, "Checkpoint not found")
        return self._load_manifest(directory, path)

    @staticmethod
    def _summary(manifest: dict) -> dict:
        summary = {
            "id": manifest["id"],
            "message": manifest["message"],
            "created_at": manifest["created_at"],
            "kind": manifest.get("kind", "manual"),
            "file_count": len(manifest.get("files") or {}),
            "bytes": manifest.get("bytes", 0),
        }
        if manifest.get("origin"):
            summary["origin"] = manifest["origin"]
        return summary

    def _prune(self, workspace_id: str) -> None:
        """Keep the newest checkpoints within the count and object budget, then drop
        every object no kept checkpoint refers to."""
        directory = self._checkpoint_dir(workspace_id)
        kept: set[str] = set()
        used = 0
        for index, manifest in enumerate(self._manifests(workspace_id)):
            fresh = set(manifest["files"].values()) - kept
            size = sum(
                self._object_path(directory, digest).stat().st_size
                for digest in fresh
                if self._object_path(directory, digest).is_file()
            )
            if index and (index >= MAX_CHECKPOINTS or used + size > MAX_CHECKPOINT_BYTES):
                (directory / f"{manifest['id']}.json").unlink(missing_ok=True)
                continue
            kept |= fresh
            used += size
        objects = directory / "objects"
        if objects.is_dir():
            for path in objects.glob("*/*"):
                if path.is_file() and path.name not in kept:
                    path.unlink(missing_ok=True)

    def checkpoint(
        self,
        workspace_id: str,
        message: str,
        *,
        kind: str = "manual",
        origin: dict | None = None,
    ) -> dict:
        """Record the project's files. When nothing changed since the newest checkpoint,
        that one is returned (``reused``) instead of a copy."""
        if kind not in CHECKPOINT_KINDS:
            raise HTTPException(422, "Unknown checkpoint kind")
        with _LOCK:
            directory = self._checkpoint_dir(workspace_id)
            current = self.files(workspace_id)
            digests = {path: _sha(data) for path, data in current.items()}
            tree = _tree_digest(digests)
            existing = self._manifests(workspace_id)
            if existing and existing[0].get("tree") == tree:
                return {**self._summary(existing[0]), "reused": True}
            for data in current.values():
                self._put_object(directory, data)
            manifest: dict[str, Any] = {
                "version": 2,
                "id": uuid.uuid4().hex,
                "message": (message or "Project checkpoint")[:200],
                "kind": kind,
                "created_at": datetime.now(UTC).isoformat(timespec="microseconds"),
                "tree": tree,
                "files": digests,
                "bytes": sum(map(len, current.values())),
            }
            if origin:
                manifest["origin"] = {
                    key: str(value)[:100] for key, value in origin.items() if value
                }
            self._atomic_json(directory / f"{manifest['id']}.json", manifest)
            self._prune(workspace_id)
            return {**self._summary(manifest), "reused": False}

    def checkpoints(self, workspace_id: str) -> builtins.list[dict]:
        with _LOCK:
            return [self._summary(item) for item in self._manifests(workspace_id)]

    def file_at(self, workspace_id: str, checkpoint_id: str, path: str) -> dict:
        """One file as it was in a checkpoint."""
        parts(path)
        with _LOCK:
            manifest = self._manifest(workspace_id, checkpoint_id)
            digest = manifest["files"].get(path)
            if digest is None:
                raise HTTPException(404, "That file is not in the checkpoint")
            data = self._get_object(self._checkpoint_dir(workspace_id), digest)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "Binary file") from None
        return {"path": path, "content": content, "sha256": digest}

    def restore(
        self,
        workspace_id: str,
        checkpoint_id: str,
        paths: builtins.list[str] | None = None,
    ) -> dict:
        """Bring files back to a checkpoint. The current state is checkpointed first, so a
        restore can itself be undone. ``paths`` restores only those files (a path the
        checkpoint lacks is deleted); git's folder is never touched."""
        with _LOCK:
            manifest = self._manifest(workspace_id, checkpoint_id)
            directory = self._checkpoint_dir(workspace_id)
            if paths is not None:
                for path in paths:
                    user_path(path)
            before = self.checkpoint(
                workspace_id, f"Before restoring “{manifest['message'][:80]}”", kind="restore"
            )
            current = self.files(workspace_id)
            wanted = (
                manifest["files"]
                if paths is None
                else {path: manifest["files"][path] for path in paths if path in manifest["files"]}
            )
            target = {path: self._get_object(directory, digest) for path, digest in wanted.items()}
            scope = set(current) | set(target) if paths is None else set(paths)
            restored = sorted(p for p in target if current.get(p) != target[p])
            removed = sorted(p for p in scope if p in current and p not in target)
            if paths is not None:
                for path in restored:
                    self.write_bytes(workspace_id, path, target[path])
                for path in removed:
                    self.delete(workspace_id, path)
            elif restored or removed:
                self._replace_files(workspace_id, target)
            return {
                "checkpoint": self._summary(manifest),
                "restored": restored,
                "removed": removed,
                "before": before,
            }

    def _replace_files(self, workspace_id: str, files: dict[str, bytes]) -> None:
        """Swap the whole file tree for ``files`` at once, keeping git's folder."""
        if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_PROJECT_BYTES:
            raise HTTPException(413, "The checkpoint is larger than the project quota")
        project = self.project(workspace_id)
        staging = project / f".restore-{uuid.uuid4().hex}"
        backup = project / f".previous-{uuid.uuid4().hex}"
        staging.mkdir(mode=0o700)
        git = project / "files" / GIT_DIR
        moved_git = False
        try:
            for path, data in files.items():
                destination = staging.joinpath(*parts(path))
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(
                    destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
            if git.is_dir() and not git.is_symlink():
                os.rename(git, staging / GIT_DIR)
                moved_git = True
            os.rename(project / "files", backup)
            try:
                os.rename(staging, project / "files")
            except BaseException:
                os.rename(backup, project / "files")
                raise
            moved_git = False
            self._touch(project)
        finally:
            if moved_git and (staging / GIT_DIR).is_dir():
                os.rename(staging / GIT_DIR, git)
            for cleanup_directory in (staging, backup):
                if cleanup_directory.exists():
                    shutil.rmtree(cleanup_directory)

    def diff(self, workspace_id: str, checkpoint_id: str) -> dict:
        with _LOCK:
            manifest = self._manifest(workspace_id, checkpoint_id)
            directory = self._checkpoint_dir(workspace_id)
            current = self.files(workspace_id)
            after = {path: _sha(data) for path, data in current.items()}
            before = manifest["files"]
            files = []
            remaining = 100_000
            for path in sorted(before.keys() | after.keys()):
                if before.get(path) == after.get(path):
                    continue
                status = (
                    "added"
                    if path not in before
                    else "deleted"
                    if path not in after
                    else "modified"
                )
                old_bytes = self._get_object(directory, before[path]) if path in before else b""
                new_bytes = current.get(path, b"")
                old = old_bytes.decode("utf-8", errors="replace")
                new = new_bytes.decode("utf-8", errors="replace")
                if len(old) > 64000 or len(new) > 64000:
                    files.append(
                        {
                            "path": path,
                            "status": status,
                            "diff": "Large or binary file changed; open the file to inspect it.",
                        }
                    )
                    continue
                patch = "".join(
                    difflib.unified_diff(
                        old.splitlines(keepends=True),
                        new.splitlines(keepends=True),
                        fromfile=f"a/{path}",
                        tofile=f"b/{path}",
                    )
                )
                files.append({"path": path, "status": status, "diff": patch[: max(0, remaining)]})
                remaining -= len(patch)
            return {"files": files, "truncated": remaining < 0}

    def apply_run(
        self,
        workspace_id: str,
        baseline: dict[str, str],
        result: dict[str, str],
        directories: builtins.list[str] | None = None,
        expected_directories: builtins.list[str] | None = None,
    ) -> builtins.list[str]:
        """Validate every exported file before modifying storage; never overwrite intervening edits."""
        decoded = {}
        for path, encoded in result.items():
            parts(path)
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                raise HTTPException(502, "Runner returned invalid project files") from None
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(413, "Generated file exceeds 1 MiB")
            decoded[path] = data
        entries: set[str] = set()
        for path in decoded:
            entries.update(entry_paths(path))
            if any(prefix in decoded for prefix in entry_paths(path) - {path}):
                raise HTTPException(502, "Runner returned conflicting file paths")
        exported_directories: set[str] = set()
        if directories is not None:
            if not isinstance(directories, list) or len(directories) > MAX_FILES:
                raise HTTPException(502, "Runner returned invalid project directories")
            for directory in directories:
                exported_directories.update(entry_paths(directory))
                if any(prefix in decoded for prefix in entry_paths(directory)):
                    raise HTTPException(502, "Runner returned conflicting directory paths")
            entries.update(exported_directories)
        if len(entries) > MAX_FILES or sum(map(len, decoded.values())) > MAX_PROJECT_BYTES:
            raise HTTPException(413, "Generated project exceeds storage quota")
        with _LOCK:
            current_files, current_directories = self.snapshot_state(workspace_id)
            if current_files != baseline or (
                expected_directories is not None
                and set(current_directories) != set(expected_directories)
            ):
                raise HTTPException(
                    409, "Project changed during execution; generated files were not applied"
                )
            preserved_directories = (
                exported_directories
                if directories is not None
                else {
                    entry["path"]
                    for entry in self.tree(workspace_id, include_git=True)["files"]
                    if entry["kind"] == "directory"
                    and entry["path"] not in decoded
                    and not any(
                        prefix in decoded for prefix in entry_paths(entry["path"]) - {entry["path"]}
                    )
                }
            )
            if len(entries | preserved_directories) > MAX_FILES:
                raise HTTPException(413, "Generated project exceeds the entry quota")
            changed = sorted(
                path
                for path in baseline.keys() | result.keys()
                if baseline.get(path) != result.get(path)
            )
            project = self.project(workspace_id)
            staging = project / f".run-{uuid.uuid4().hex}"
            backup = project / f".previous-{uuid.uuid4().hex}"
            staging.mkdir(mode=0o700)
            try:
                # Preserve empty directories too, unless generated files replace their paths.
                for path in preserved_directories:
                    staging.joinpath(*parts(path)).mkdir(parents=True, exist_ok=True, mode=0o700)
                for path, data in decoded.items():
                    destination = staging.joinpath(*parts(path))
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    descriptor = os.open(
                        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(data)
                os.rename(project / "files", backup)
                try:
                    os.rename(staging, project / "files")
                except BaseException:
                    os.rename(backup, project / "files")
                    raise
                self._touch(project)
            finally:
                for cleanup_directory in (staging, backup):
                    if cleanup_directory.exists():
                        shutil.rmtree(cleanup_directory)
            return changed
