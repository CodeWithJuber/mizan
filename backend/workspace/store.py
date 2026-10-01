"""Private persistent project files; never resolve user paths against the host root."""

from __future__ import annotations

import base64
import builtins
import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi import HTTPException

MAX_FILE_BYTES = 1024 * 1024
MAX_PROJECT_BYTES = 10 * 1024 * 1024
MAX_FILES = 500
MAX_WORKSPACES = 10
MAX_CHECKPOINTS = 5
_LOCK = threading.RLock()
_ID = re.compile(r"^[0-9a-f]{32}$")


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

    def list(self) -> builtins.list[dict]:
        with _LOCK:
            result = []
            for path in self.root.iterdir():
                if _ID.fullmatch(path.name) and path.is_dir() and not path.is_symlink():
                    result.append(self._metadata(path))
            return sorted(result, key=lambda item: item["updated_at"], reverse=True)

    def create(self, name: str) -> dict:
        if not name or len(name) > 100:
            raise HTTPException(422, "Project name must be 1..100 characters")
        with _LOCK:
            if len(self.list()) >= MAX_WORKSPACES:
                raise HTTPException(413, "Workspace quota reached")
            workspace_id = uuid.uuid4().hex
            path = self.root / workspace_id
            path.mkdir(mode=0o700)
            (path / "files").mkdir(mode=0o700)
            (path / "checkpoints").mkdir(mode=0o700)
            result = {"id": workspace_id, "name": name, "created_at": now(), "updated_at": now()}
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
                    raise HTTPException(413, "Only regular project files up to 1 MiB are supported")
                data = handle.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(413, "Project file exceeds 1 MiB")
                return data

    def read(self, workspace_id: str, path: str) -> dict:
        data = self.read_bytes(workspace_id, path)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "Binary file; publish it as an image artifact") from None
        return {"path": path, "content": content, "sha256": hashlib.sha256(data).hexdigest()}

    def tree(self, workspace_id: str) -> dict:
        result: builtins.list[dict] = []

        def visit(fd: int, prefix: str) -> None:
            for name in sorted(os.listdir(fd)):
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
        with _LOCK:
            count = len(
                {entry["path"] for entry in self.tree(workspace_id)["files"]}
                | entry_paths(new_path)
            )
            if count > MAX_FILES:
                raise HTTPException(413, "Workspace entry quota reached")
        with (
            _LOCK,
            self.parent(workspace_id, path) as (source, old),
            self.parent(workspace_id, new_path, create=True) as (target, new),
        ):
            info = os.stat(old, dir_fd=source, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise HTTPException(422, "Rename supports regular files only")
            try:
                os.stat(new, dir_fd=target, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise HTTPException(409, "Target path already exists")
            os.rename(old, new, src_dir_fd=source, dst_dir_fd=target)
            self._touch(self.project(workspace_id))
            return {"path": new_path}

    def delete(self, workspace_id: str, path: str) -> dict:
        with _LOCK, self.parent(workspace_id, path) as (fd, name):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise HTTPException(422, "Deletion supports regular files only")
            os.unlink(name, dir_fd=fd)
            self._touch(self.project(workspace_id))
        return {"deleted": True, "path": path}

    def snapshot(self, workspace_id: str) -> dict[str, str]:
        with _LOCK:
            result = {
                item["path"]: base64.b64encode(self.read_bytes(workspace_id, item["path"])).decode(
                    "ascii"
                )
                for item in self.tree(workspace_id)["files"]
                if item["kind"] == "file"
            }
            if sum(len(base64.b64decode(data)) for data in result.values()) > MAX_PROJECT_BYTES:
                raise HTTPException(413, "Workspace storage quota reached")
            return result

    def snapshot_state(self, workspace_id: str) -> tuple[dict[str, str], builtins.list[str]]:
        with _LOCK:
            return self.snapshot(workspace_id), [
                item["path"]
                for item in self.tree(workspace_id)["files"]
                if item["kind"] == "directory"
            ]

    def checkpoint(self, workspace_id: str, message: str) -> dict:
        with _LOCK:
            data = {
                "id": uuid.uuid4().hex,
                "message": message[:200],
                "created_at": now(),
                "files": self.snapshot(workspace_id),
            }
            directory = self.project(workspace_id) / "checkpoints"
            self._atomic_json(directory / f"{data['id']}.json", data)
            previous = sorted(
                directory.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True
            )
            for old in previous[MAX_CHECKPOINTS:]:
                old.unlink()
            return {key: value for key, value in data.items() if key != "files"}

    def checkpoints(self, workspace_id: str) -> builtins.list[dict]:
        with _LOCK:
            result = []
            for path in (self.project(workspace_id) / "checkpoints").glob("*.json"):
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd) as handle:
                    value = json.load(handle)
                result.append({key: value[key] for key in ("id", "message", "created_at")})
            return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def diff(self, workspace_id: str, checkpoint_id: str) -> dict:
        if not _ID.fullmatch(checkpoint_id):
            raise HTTPException(404, "Checkpoint not found")
        with _LOCK:
            try:
                fd = os.open(
                    self.project(workspace_id) / "checkpoints" / f"{checkpoint_id}.json",
                    os.O_RDONLY | os.O_NOFOLLOW,
                )
            except FileNotFoundError:
                raise HTTPException(404, "Checkpoint not found") from None
            with os.fdopen(fd) as handle:
                before = json.load(handle)["files"]
            after = self.snapshot(workspace_id)
            files = []
            remaining = 100_000
            for path in sorted(before.keys() | after.keys()):
                if before.get(path) == after.get(path):
                    continue
                old = base64.b64decode(before.get(path, "")).decode("utf-8", errors="replace")
                new = base64.b64decode(after.get(path, "")).decode("utf-8", errors="replace")
                if len(old) > 64000 or len(new) > 64000:
                    files.append(
                        {
                            "path": path,
                            "status": "modified",
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
                files.append(
                    {
                        "path": path,
                        "status": "added"
                        if path not in before
                        else "deleted"
                        if path not in after
                        else "modified",
                        "diff": patch[: max(0, remaining)],
                    }
                )
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
                    for entry in self.tree(workspace_id)["files"]
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
