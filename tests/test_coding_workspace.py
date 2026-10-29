"""Exercise privacy, descriptor-safe file access, edit conflicts and real isolated jobs."""

import base64
import hashlib
import io
import json
import os
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import coding_workspace as api
from api.artifacts import add_artifact_version, get_artifact
from security.auth import TokenPayload, bind_principal, reset_principal
from skills.builtin.coding_workspace import CodingWorkspaceSkill, allows_user_workspace_tool
from skills.registry import SkillRegistry
from workspace import runner as runner_module
from workspace import store as store_module
from workspace.context import bind_workspace, reset_workspace, running_in
from workspace.runner import app as runner_app
from workspace.runner import execute
from workspace.store import WorkspaceStore

USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")
OTHER = TokenPayload("bob", "Bob", ["user"], 9999999999, 0, "bob-token")
ADMIN = TokenPayload("admin", "Admin", ["admin"], 9999999999, 0, "admin-token")


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.delenv("MIZAN_WORKSPACE_RUNNER_URL", raising=False)
    monkeypatch.delenv("MIZAN_WORKSPACE_RUNNER_TOKEN", raising=False)
    return WorkspaceStore(USER.user_id)


def client(user=USER):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_project_editor_roundtrip_and_edit_conflict(storage):
    c = client()
    project = c.post("/api/workspaces", json={"name": "My app"}).json()["id"]
    path = f"/api/workspaces/{project}"
    assert (
        c.put(
            path + "/file", json={"path": "src/main.py", "content": "print('hello')\n"}
        ).status_code
        == 200
    )
    read = c.get(path + "/file", params={"path": "src/main.py"}).json()
    assert read["content"] == "print('hello')\n"
    assert (
        c.put(
            path + "/file",
            json={"path": "src/main.py", "content": "updated", "expected_sha256": "wrong"},
        ).status_code
        == 409
    )
    assert (
        c.put(
            path + "/file",
            json={"path": "src/main.py", "content": "updated", "expected_sha256": read["sha256"]},
        ).status_code
        == 200
    )
    assert (
        c.post(path + "/rename", json={"path": "src/main.py", "new_path": "src/app.py"}).status_code
        == 200
    )
    assert c.get(path + "/tree").json()["files"][1]["path"] == "src/app.py"
    assert c.delete(path + "/file", params={"path": "src/app.py"}).status_code == 200
    assert c.delete(path + "/file", params={"path": "src"}).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../secret",
        "src/../../secret",
        "src//foo",
        "src\\foo",
        "x/./y",
        "C:\\Windows\\system.ini",
        "x/\x00y",
    ],
)
def test_path_traversal_rejected(storage, path):
    workspace = storage.create("App")["id"]
    with pytest.raises(HTTPException) as exc:
        storage.write(workspace, path, "attack")
    assert exc.value.status_code == 422


def test_symlink_and_fifo_cannot_escape_or_block(storage, tmp_path):
    workspace = storage.create("App")["id"]
    files = storage.project(workspace) / "files"
    outside = tmp_path / "private"
    outside.write_text("private content")
    (files / "link").symlink_to(outside)
    for operation in (
        lambda: storage.read(workspace, "link"),
        lambda: storage.write(workspace, "link", "overwrite"),
        lambda: storage.delete(workspace, "link"),
    ):
        with pytest.raises(HTTPException):
            operation()
    assert outside.read_text() == "private content"
    (files / "link").unlink()
    (files / "directory").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(HTTPException):
        storage.read(workspace, "directory/private")
    (files / "directory").unlink()
    os.mkfifo(files / "pipe")
    with pytest.raises(HTTPException) as exc:
        storage.read(workspace, "pipe")
    assert exc.value.status_code == 413


def test_cross_user_requests_return_missing(storage):
    workspace = storage.create("Secret project")["id"]
    storage.write(workspace, "secret.txt", "private")
    other = client(OTHER)
    assert other.get("/api/workspaces").json()["workspaces"] == []
    for suffix in ("tree", "checkpoints", "file?path=secret.txt"):
        assert other.get(f"/api/workspaces/{workspace}/{suffix}").status_code == 404
    assert (
        other.put(
            f"/api/workspaces/{workspace}/file", json={"path": "secret.txt", "content": "overwrite"}
        ).status_code
        == 404
    )
    assert storage.read(workspace, "secret.txt")["content"] == "private"


def test_anonymous_workspace_requests_are_denied(storage, monkeypatch):
    app = FastAPI()
    app.include_router(api.router)

    async def deny():
        raise HTTPException(401, "Authentication required")

    app.dependency_overrides[api.require_auth] = deny
    c = TestClient(app)
    assert c.get("/api/workspaces").status_code == 401
    assert c.post("/api/workspaces", json={"name": "attack"}).status_code == 401


def test_checkpoints_diffs_retention_and_restart(storage, monkeypatch):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "main.py", "before\n")
    checkpoint = storage.checkpoint(workspace, "before coding")
    assert checkpoint["reused"] is False and checkpoint["file_count"] == 1
    # Nothing changed: the same checkpoint comes back instead of a copy.
    again = storage.checkpoint(workspace, "same again")
    assert again["reused"] is True and again["id"] == checkpoint["id"]
    storage.write(workspace, "main.py", "after\n")
    storage.write(workspace, "new.py", "new\n")
    changes = storage.diff(workspace, checkpoint["id"])["files"]
    assert {item["status"] for item in changes} == {"modified", "added"}
    assert "-before" in changes[0]["diff"] and "+after" in changes[0]["diff"]
    monkeypatch.setattr(store_module, "MAX_CHECKPOINTS", 5)
    for index in range(7):
        storage.write(workspace, "main.py", f"version {index}\n")
        storage.checkpoint(workspace, f"v{index}")
    kept = storage.checkpoints(workspace)
    assert len(kept) == 5 and kept[0]["message"] == "v6"
    # Objects of pruned checkpoints are gone; shared ones stay once.
    objects = storage.project(workspace) / "checkpoints" / "objects"
    stored = {path.name for path in objects.glob("*/*")}
    wanted = {
        hashlib.sha256(f"version {index}\n".encode()).hexdigest() for index in range(2, 7)
    } | {hashlib.sha256(b"new\n").hexdigest()}
    assert stored == wanted
    assert WorkspaceStore(USER.user_id).read(workspace, "main.py")["content"] == "version 6\n"


def test_restore_brings_back_files_keeps_git_and_can_be_undone(storage):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "src/a.py", "a = 1\n")
    storage.write(workspace, "b.py", "b = 1\n")
    saved = storage.checkpoint(workspace, "good")
    storage.write(workspace, "src/a.py", "a = 2\n")
    storage.delete(workspace, "b.py")
    storage.write(workspace, "c.py", "c\n")
    git = storage.project(workspace) / "files" / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    result = storage.restore(workspace, saved["id"])
    assert result["restored"] == ["b.py", "src/a.py"] and result["removed"] == ["c.py"]
    assert storage.read(workspace, "src/a.py")["content"] == "a = 1\n"
    assert storage.read(workspace, "b.py")["content"] == "b = 1\n"
    assert not (storage.project(workspace) / "files" / "c.py").exists()
    assert (git / "HEAD").read_text() == "ref: refs/heads/main\n"
    # The state before the restore was saved first, so the restore can be undone.
    undo = storage.restore(workspace, result["before"]["id"])
    assert undo["removed"] == ["b.py"] and undo["restored"] == ["c.py", "src/a.py"]
    assert storage.read(workspace, "src/a.py")["content"] == "a = 2\n"


def test_restore_selected_files_and_read_a_file_from_a_checkpoint(storage):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "a.py", "old a\n")
    storage.write(workspace, "b.py", "old b\n")
    saved = storage.checkpoint(workspace, "start")
    storage.write(workspace, "a.py", "new a\n")
    storage.write(workspace, "b.py", "new b\n")
    storage.write(workspace, "added.py", "added\n")
    assert storage.file_at(workspace, saved["id"], "a.py") == {
        "path": "a.py",
        "content": "old a\n",
        "sha256": hashlib.sha256(b"old a\n").hexdigest(),
    }
    with pytest.raises(HTTPException) as missing:
        storage.file_at(workspace, saved["id"], "added.py")
    assert missing.value.status_code == 404
    result = storage.restore(workspace, saved["id"], ["a.py", "added.py"])
    assert result["restored"] == ["a.py"] and result["removed"] == ["added.py"]
    assert storage.read(workspace, "a.py")["content"] == "old a\n"
    assert storage.read(workspace, "b.py")["content"] == "new b\n"
    with pytest.raises(HTTPException) as unknown:
        storage.restore(workspace, "0" * 32)
    assert unknown.value.status_code == 404


def test_old_full_copy_checkpoints_are_converted_once(storage):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "main.py", "now\n")
    directory = storage.project(workspace) / "checkpoints"
    legacy = {
        "id": "a" * 32,
        "message": "from before",
        "created_at": "2026-10-01T10:00:00+00:00",
        "files": {"main.py": base64.b64encode(b"then\n").decode()},
    }
    (directory / f"{'a' * 32}.json").write_text(json.dumps(legacy))
    listed = storage.checkpoints(workspace)
    assert [item["id"] for item in listed] == ["a" * 32]
    assert listed[0]["created_at"] == "2026-10-01T10:00:00+00:00"
    converted = json.loads((directory / f"{'a' * 32}.json").read_text())
    assert converted["version"] == 2 and "then" not in json.dumps(converted)
    assert storage.file_at(workspace, "a" * 32, "main.py")["content"] == "then\n"
    assert "-then" in storage.diff(workspace, "a" * 32)["files"][0]["diff"]
    assert storage.checkpoints(workspace) == listed


def test_git_folder_stays_out_of_file_tools_and_quota(storage):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "main.py", "print(1)\n")
    git = storage.project(workspace) / "files" / ".git"
    (git / "objects").mkdir(parents=True)
    (git / "config").write_text("[core]\n")
    assert [item["path"] for item in storage.tree(workspace)["files"]] == ["main.py"]
    assert [item["path"] for item in storage.glob(workspace, "**")["files"]] == ["main.py"]
    assert storage.grep(workspace, "core")["matches"] == []
    for operation in (
        lambda: storage.write(workspace, ".git/config", "evil"),
        lambda: storage.delete(workspace, ".git/config"),
        lambda: storage.directory(workspace, ".git/hooks"),
        lambda: storage.rename(workspace, "main.py", ".git/main.py"),
    ):
        with pytest.raises(HTTPException) as refused:
            operation()
        assert refused.value.status_code == 422
    files, directories = storage.snapshot_state(workspace)
    assert ".git/config" in files and ".git/objects" in directories
    saved = storage.checkpoint(workspace, "x")
    manifest = json.loads(
        (storage.project(workspace) / "checkpoints" / f"{saved['id']}.json").read_text()
    )
    assert list(manifest["files"]) == ["main.py"] and saved["file_count"] == 1


def test_project_rename_delete_export_and_restore_routes(storage):
    c = client()
    project = c.post("/api/workspaces", json={"name": "First"}).json()["id"]
    base = f"/api/workspaces/{project}"
    c.put(base + "/file", json={"path": "app.js", "content": "one\n"})
    saved = c.post(base + "/checkpoint", json={"message": "one"}).json()
    c.put(base + "/file", json={"path": "app.js", "content": "two\n"})
    renamed = c.patch(base, json={"name": "  Better name "})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Better name"
    assert c.get("/api/workspaces").json()["workspaces"][0]["name"] == "Better name"
    at = c.get(f"{base}/checkpoints/{saved['id']}/file", params={"path": "app.js"})
    assert at.json()["content"] == "one\n"
    (storage.project(project) / "files" / ".git").mkdir()
    (storage.project(project) / "files" / ".git" / "HEAD").write_text("x")
    exported = c.get(base + "/export.zip")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"] == 'attachment; filename="Better-name.zip"'
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert archive.namelist() == ["app.js"] and archive.read("app.js") == b"two\n"
    with running_in(USER.user_id, project):
        assert c.post(f"{base}/checkpoints/{saved['id']}/restore", json={}).status_code == 409
        assert c.delete(base).status_code == 409
    restored = c.post(f"{base}/checkpoints/{saved['id']}/restore", json={"paths": ["app.js"]})
    assert restored.status_code == 200 and restored.json()["restored"] == ["app.js"]
    assert c.get(base + "/file", params={"path": "app.js"}).json()["content"] == "one\n"
    other = client(OTHER)
    assert other.patch(base, json={"name": "mine"}).status_code == 404
    assert other.delete(base).status_code == 404
    assert other.get(base + "/export.zip").status_code == 404
    assert other.post(f"{base}/checkpoints/{saved['id']}/restore", json={}).status_code == 404
    assert c.delete(base).json() == {"deleted": True, "id": project}
    assert c.get("/api/workspaces").json()["workspaces"] == []
    assert c.get(base + "/tree").status_code == 404


def test_quota_message_names_where_to_delete(storage, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_MAX_PROJECTS", "1")
    storage.create("One")
    with pytest.raises(HTTPException) as full:
        storage.create("Two")
    assert full.value.status_code == 413 and "Code → Projects" in str(full.value.detail)


def test_failed_export_cannot_partially_overwrite_and_concurrent_edits_win(storage):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "main.py", "baseline")
    baseline = storage.snapshot(workspace)
    with pytest.raises(HTTPException):
        storage.apply_run(
            workspace,
            baseline,
            {"main.py": base64.b64encode(b"overwrite").decode(), "../escape": "YQ=="},
        )
    assert storage.read(workspace, "main.py")["content"] == "baseline"
    storage.write(workspace, "main.py", "editor change")
    with pytest.raises(HTTPException) as exc:
        storage.apply_run(
            workspace, baseline, {"main.py": base64.b64encode(b"run change").decode()}
        )
    assert exc.value.status_code == 409
    assert storage.read(workspace, "main.py")["content"] == "editor change"


def test_execution_export_applies_deletes_and_new_files(storage):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "old.txt", "old")
    baseline = storage.snapshot(workspace)
    changed = storage.apply_run(
        workspace, baseline, {"src/new.py": base64.b64encode(b"new").decode()}
    )
    assert changed == ["old.txt", "src/new.py"]
    assert storage.read(workspace, "src/new.py")["content"] == "new"
    with pytest.raises(HTTPException):
        storage.read(workspace, "old.txt")


def test_execution_fails_closed_and_hardware_is_admin_only(storage):
    workspace = storage.create("App")["id"]
    c = client()
    caps = c.get("/api/workspaces").json()["capabilities"]
    assert caps["execution_available"] is False and caps["host_shell"] is False
    assert c.post(f"/api/workspaces/{workspace}/run", json={"command": "id"}).status_code == 503
    assert c.get("/api/workspaces/hardware").status_code == 403
    hardware = client(ADMIN).get("/api/workspaces/hardware").json()
    assert hardware["scope"] == "backend-container" and hardware["disk_total_bytes"] > 0
    assert hardware["host_shell"] is False


def test_saved_preview_artifact_owner_scope(storage):
    workspace = storage.create("App")["id"]
    storage.write(workspace, "index.html", "<h1>Hello</h1>")
    response = client().post(
        f"/api/workspaces/{workspace}/artifact", json={"path": "index.html", "session_id": "chat-1"}
    )
    assert response.status_code == 201
    artifact = response.json()["artifact"]
    assert artifact["kind"] == "html" and artifact["content"] == "<h1>Hello</h1>"
    assert get_artifact(user_id=OTHER.user_id, artifact_id=artifact["id"]) is None


def test_image_decoder_and_image_versions(storage):
    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    workspace = storage.create("Images")["id"]
    storage.write_bytes(workspace, "chart.png", output.getvalue())
    artifact = api.publish_artifact(
        storage, workspace, user_id=USER.user_id, path="chart.png", session_id="s"
    )["artifact"]
    assert artifact["kind"] == "image" and artifact["content"].startswith("data:image/png;base64,")
    with pytest.raises(HTTPException) as exc:
        add_artifact_version(
            user_id=USER.user_id,
            artifact_id=artifact["id"],
            content="data:image/svg+xml;base64,PHN2Zy8+",
        )
    assert exc.value.status_code == 422
    storage.write_bytes(workspace, "fake.png", b"not an image")
    with pytest.raises(HTTPException):
        api.publish_artifact(
            storage, workspace, user_id=USER.user_id, path="fake.png", session_id="s"
        )


async def test_agent_tools_require_principal_and_respect_selected_project(storage):
    skill = CodingWorkspaceSkill()
    assert (await skill.execute({"action": "create", "user_id": USER.user_id}))["status"] == 401
    principal = bind_principal(USER)
    workspace = storage.create("App")["id"]
    selected = bind_workspace(workspace)
    try:
        await skill.write(path="main.py", content="agent edit")
        assert storage.read(workspace, "main.py")["content"] == "agent edit"
        other_project = storage.create("Other")["id"]
        with pytest.raises(HTTPException) as exc:
            await skill.read(workspace_id=other_project, path="main.py")
        assert exc.value.status_code == 403
        result = await skill.artifact(path="main.py", session_id="chat-1")
        assert result["artifact"]["kind"] == "code"
        assert "workspace_run" in skill.get_tools()
        assert {schema["name"] for schema in skill.get_tool_schemas()} == set(skill.get_tools())
    finally:
        reset_workspace(selected)
        reset_principal(principal)


async def test_a_started_server_opens_its_preview_in_the_chat(storage, monkeypatch):
    from agents import events
    from skills.builtin import coding_workspace as skill_module

    async def start_service(user_id, workspace_id, port, command, mode):
        return {"port": port, "preview_url": f"/api/workspaces/preview/cap/{port}/"}

    monkeypatch.setattr(skill_module.session_client, "start_service", start_service)
    seen = []

    async def sink(kind, payload):
        seen.append((kind, payload))

    principal = bind_principal(USER)
    workspace = storage.create("App")["id"]
    selected = bind_workspace(workspace)
    try:
        with events.bind_event_sink(sink):
            await CodingWorkspaceSkill().sandbox(action="serve", port=5173, command="npm run dev")
    finally:
        reset_workspace(selected)
        reset_principal(principal)
    assert seen == [
        (
            "preview",
            {
                "workspace_id": workspace,
                "port": 5173,
                "preview_url": "/api/workspaces/preview/cap/5173/",
            },
        )
    ]


async def test_user_tool_dispatch_accepts_only_shipped_bound_handlers(storage):
    skill = CodingWorkspaceSkill()
    registry = SkillRegistry()
    registry.register(skill)
    workspace = storage.create("Selected project")["id"]
    selected = bind_workspace(workspace)
    principal = bind_principal(USER)
    try:
        assert allows_user_workspace_tool("workspace_write", registry, native_tools={})
        result = await registry.get_all_tools()["workspace_write"](
            path="agent.py", content="print(42)"
        )
        assert result["path"] == "agent.py"
        assert storage.read(workspace, "agent.py")["content"] == "print(42)"
        assert not allows_user_workspace_tool("bash", registry)
        assert not allows_user_workspace_tool("workspace_unregistered", registry)
        assert not allows_user_workspace_tool(
            "workspace_write", registry, native_tools={"workspace_write": lambda: None}
        )
        # A different plugin with the same tool name cannot gain the user exception.
        impostor = Mock()
        impostor.get_tools.return_value = {"workspace_write": lambda: {"unsafe": True}}
        registry._loaded["impostor"] = impostor
        assert not allows_user_workspace_tool("workspace_write", registry)
        registry._loaded.pop("impostor")
    finally:
        reset_principal(principal)
    viewer = TokenPayload(USER.user_id, "Viewer", ["viewer"], 9999999999, 0, "viewer")
    principal = bind_principal(viewer)
    try:
        # Recognition does not bypass the shipped handler's editor permission.
        assert allows_user_workspace_tool("workspace_write", registry)
        with pytest.raises(HTTPException) as exc:
            await registry.get_all_tools()["workspace_write"](path="agent.py", content="overwrite")
        assert exc.value.status_code == 403
    finally:
        reset_principal(principal)
        reset_workspace(selected)


def test_private_runner_rejects_anonymous_and_wrong_token(monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", "a" * 40)
    c = TestClient(runner_app)
    assert c.get("/health").status_code == 401
    assert c.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/run", json={}).status_code == 401


def test_hung_daemon_cleanup_does_not_prevent_cli_termination(monkeypatch):
    process = Mock()
    process.stdin = io.BytesIO()
    process.stdout = io.BytesIO()
    process.stderr = io.BytesIO()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("docker", 21), 0]
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(runner_module, "cleanup", Mock(side_effect=OSError("daemon unavailable")))
    with pytest.raises(HTTPException) as exc:
        execute({"language": "python", "command": "print(42)", "timeout_s": 1, "files": {}})
    assert exc.value.status_code == 503
    process.kill.assert_called_once()
    assert process.wait.call_args_list[-1].kwargs == {"timeout": 5}


def test_viewer_cannot_create_edit_or_execute(storage):
    viewer = TokenPayload("alice", "Read only", ["viewer"], 9999999999, 0, "viewer")
    workspace = storage.create("App")["id"]
    storage.write(workspace, "main.py", "original")
    c = client(viewer)
    assert c.get(f"/api/workspaces/{workspace}/tree").status_code == 200
    assert c.post("/api/workspaces", json={"name": "write"}).status_code == 403
    assert (
        c.put(
            f"/api/workspaces/{workspace}/file", json={"path": "main.py", "content": "attack"}
        ).status_code
        == 403
    )
    assert c.post(f"/api/workspaces/{workspace}/run", json={"command": "id"}).status_code == 403


def test_rename_at_entry_quota_and_concurrent_renames(storage, monkeypatch):
    from workspace import store as store_module

    monkeypatch.setattr(store_module, "MAX_FILES", 3)
    workspace = storage.create("Full project")["id"]
    for name in ("a", "b", "c"):
        storage.write(workspace, name, name)
    storage.rename(workspace, "a", "d")
    assert {item["path"] for item in storage.tree(workspace)["files"]} == {"b", "c", "d"}
    storage.delete(workspace, "c")

    def rename(source, target):
        try:
            storage.rename(workspace, source, target)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(rename, "d", "first/d")
        two = pool.submit(rename, "b", "second/b")
        assert sorted((one.result(), two.result())) == [200, 413]
    assert len(storage.tree(workspace)["files"]) == 3


def runtime_available():
    try:
        return (
            subprocess.run(
                ["docker", "image", "inspect", "mizan-workspace-runtime:v1"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(
    not runtime_available(),
    reason="Build isolated runtime image to execute Docker integration checks",
)
class TestRealRuntime:
    @pytest.mark.parametrize(
        "language,command,expected",
        [
            ("python", "print(6 * 7)", "42"),
            ("javascript", "console.log(6 * 7)", "42"),
            ("shell", "git --version && printf 'shell works'", "shell works"),
        ],
    )
    def test_real_languages(self, language, command, expected):
        result = execute({"language": language, "command": command, "timeout_s": 10, "files": {}})
        assert result["exit_code"] == 0 and expected in result["stdout"]
        assert result["export_error"] is False

    def test_typescript_is_parsed_by_the_runtimes_esbuild(self):
        from tadbir.engine import _esbuild

        good = base64.b64encode(b"export const n: number = 1;\n").decode()
        bad = base64.b64encode(b"export const n: number = ;\n").decode()
        passed = execute(
            {"language": "shell", "command": _esbuild(["good.ts"]), "timeout_s": 30,
             "files": {"good.ts": good}}
        )  # fmt: skip
        assert passed["exit_code"] == 0, passed["stderr"]
        failed = execute(
            {"language": "shell", "command": _esbuild(["good.ts", "bad.ts"]), "timeout_s": 30,
             "files": {"good.ts": good, "bad.ts": bad}}
        )  # fmt: skip
        assert failed["exit_code"] == 1 and "bad.ts" in failed["stderr"]

    def test_generated_file_and_no_keys_network_host_mounts(self):
        code = "import os,socket,pathlib\nassert not os.getenv('MIZAN_WORKSPACE_RUNNER_TOKEN')\nassert not pathlib.Path('/var/run/docker.sock').exists()\nassert not pathlib.Path('/data/mizan.db').exists()\ntry:\n socket.create_connection(('1.1.1.1',443),timeout=1)\n raise AssertionError('network unexpectedly available')\nexcept OSError: pass\npathlib.Path('result.txt').write_text('saved')\nprint('isolated')"
        result = execute({"language": "python", "command": code, "timeout_s": 10, "files": {}})
        assert result["exit_code"] == 0 and result["stdout"] == "isolated\n"
        assert base64.b64decode(result["files"]["result.txt"]) == b"saved"

    def test_plot_is_generated_isolated_and_saved_as_validated_artifact(self, storage):
        from PIL import Image

        code = """import os
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from PIL import Image
assert matplotlib.get_backend().lower() == 'agg'
assert os.environ['OPENBLAS_NUM_THREADS'] == '1'
x = np.linspace(0, 2 * np.pi, 40)
fig, ax = plt.subplots(figsize=(4, 3), dpi=80)
ax.plot(x, np.sin(x))
fig.savefig('curve.png')
plt.close(fig)
with Image.open('curve.png') as image:
    assert image.size == (320, 240)
print('plot created')
"""
        result = execute({"language": "python", "command": code, "timeout_s": 30, "files": {}})
        assert result["exit_code"] == 0, result["stderr"]
        assert result["stdout"] == "plot created\n"
        assert result["export_error"] is False
        assert set(result["files"]) == {"curve.png"}
        data = base64.b64decode(result["files"]["curve.png"])
        with Image.open(io.BytesIO(data)) as image:
            assert image.format == "PNG" and image.size == (320, 240)
            image.verify()
        workspace = storage.create("Isolated chart")["id"]
        storage.apply_run(workspace, {}, result["files"], result["directories"])
        response = client().post(
            f"/api/workspaces/{workspace}/artifact",
            json={"path": "curve.png", "session_id": "chart-chat"},
        )
        assert response.status_code == 201
        artifact = response.json()["artifact"]
        assert artifact["kind"] == "image" and artifact["session_id"] == "chart-chat"
        assert base64.b64decode(artifact["content"].split(",", 1)[1]) == data
        assert get_artifact(user_id=OTHER.user_id, artifact_id=artifact["id"]) is None

    def test_timeout_output_cap_and_cleanup(self):
        result = execute(
            {
                "language": "python",
                "command": "import time; print('x'*300000,flush=True); time.sleep(30)",
                "timeout_s": 1,
                "files": {},
            }
        )
        assert result["timed_out"] is True and result["exit_code"] == 124
        assert len(result["stdout"].encode()) <= 100000 and result["truncated"] is True
        running = subprocess.run(
            ["docker", "ps", "-q", "--filter", "name=mizan-workspace-"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        assert running.stdout == ""

    def test_unsafe_generated_symlink_not_exported(self):
        result = execute(
            {"language": "shell", "command": "ln -s /etc/passwd leak", "timeout_s": 10, "files": {}}
        )
        assert result["export_error"] is True and result["files"] == {}

    def test_git_history_persists_across_isolated_jobs(self, storage):
        workspace = storage.create("Repository")["id"]
        storage.write(workspace, "main.py", "print(42)\n")
        baseline = storage.snapshot(workspace)
        initialized = execute(
            {"language": "shell", "command": "git init", "timeout_s": 10, "files": baseline}
        )
        assert initialized["exit_code"] == 0
        storage.apply_run(workspace, baseline, initialized["files"], initialized["directories"])
        baseline = storage.snapshot(workspace)
        committed = execute(
            {
                "language": "shell",
                "command": "git add -A && git -c user.name=Test -c user.email=test@localhost commit -m initial && git log -1 --oneline",
                "timeout_s": 10,
                "files": baseline,
                "directories": [
                    item["path"]
                    for item in storage.tree(workspace)["files"]
                    if item["kind"] == "directory"
                ],
            }
        )
        assert committed["exit_code"] == 0 and "initial" in committed["stdout"]
        storage.apply_run(workspace, baseline, committed["files"], committed["directories"])
        baseline = storage.snapshot(workspace)
        checked = execute(
            {
                "language": "shell",
                "command": "git status --porcelain && git log -1 --oneline",
                "timeout_s": 10,
                "files": baseline,
                "directories": [
                    item["path"]
                    for item in storage.tree(workspace)["files"]
                    if item["kind"] == "directory"
                ],
            }
        )
        assert checked["exit_code"] == 0 and "initial" in checked["stdout"]


async def test_chat_image_artifact_uses_bound_session_and_preserves_binary(storage):
    from PIL import Image

    from workspace.context import bind_chat_session, reset_chat_session

    workspace = storage.create("Graph")["id"]
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(image, format="PNG")
    data = image.getvalue()
    (storage.project(workspace) / "files" / "plot.png").write_bytes(data)
    token = bind_principal(USER)
    session = bind_chat_session("current-chat")
    try:
        skill = CodingWorkspaceSkill()
        result = await skill.artifact(workspace, "plot.png")
        assert result["artifact"]["session_id"] == "current-chat"
        assert result["artifact"]["kind"] == "image"
        assert storage.read_bytes(workspace, "plot.png") == data
        with pytest.raises(HTTPException) as exc:
            await skill.artifact(workspace, "plot.png", session_id="different-chat")
        assert exc.value.status_code == 403
    finally:
        reset_chat_session(session)
        reset_principal(token)
