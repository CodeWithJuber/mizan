"""Claude-Code-style project tools: numbered reads, exact edits, glob, grep, web."""

import pytest
from fastapi import HTTPException

from security.auth import TokenPayload, bind_principal, reset_principal
from skills.builtin.coding_workspace import (
    CodingWorkspaceSkill,
    allows_user_web_tool,
    allows_user_workspace_tool,
)
from skills.builtin.web_browse import WebBrowseSkill
from skills.registry import SkillRegistry
from workspace.context import bind_workspace, reset_workspace
from workspace.store import WorkspaceStore, glob_regex

USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    store = WorkspaceStore(USER.user_id)
    workspace = store.create("App")["id"]
    store.write(workspace, "src/app.py", "def add(a, b):\n    return a + b\n\nprint(add(2, 2))\n")
    store.write(workspace, "src/util/helpers.py", "VALUE = 1\nVALUE = 2\n")
    store.write(workspace, "README.md", "# Demo\nTODO: docs\n")
    store.write_bytes(workspace, "logo.bin", b"\x00\x01TODO\x00")
    return store, workspace


def test_read_offset_limit_numbering(project):
    store, workspace = project
    excerpt = store.read_lines(workspace, "src/app.py", offset=2, limit=2)
    assert excerpt["content"] == "     2\t    return a + b\n     3\t"
    assert excerpt["total_lines"] == 4 and excerpt["truncated"] is True
    assert excerpt["sha256"] == store.read(workspace, "src/app.py")["sha256"]


def test_edit_requires_unique_exact_match(project):
    store, workspace = project
    result = store.edit(workspace, "src/app.py", "return a + b", "return a + b  # sum")
    assert "+    return a + b  # sum" in result["diff"]
    assert store.read(workspace, "src/app.py")["content"].count("# sum") == 1
    with pytest.raises(HTTPException) as ambiguous:
        store.edit(workspace, "src/util/helpers.py", "VALUE", "LIMIT")
    assert ambiguous.value.status_code == 409 and "2 places" in ambiguous.value.detail
    with pytest.raises(HTTPException) as missing:
        store.edit(workspace, "src/app.py", "not in the file", "x")
    assert missing.value.status_code == 404


def test_edit_replace_all_and_sha_conflict(project):
    store, workspace = project
    result = store.edit(workspace, "src/util/helpers.py", "VALUE", "LIMIT", replace_all=True)
    assert result["replacements"] == 2
    assert store.read(workspace, "src/util/helpers.py")["content"] == "LIMIT = 1\nLIMIT = 2\n"
    with pytest.raises(HTTPException) as stale:
        store.edit(workspace, "README.md", "TODO", "DONE", expected_sha256="0" * 64)
    assert stale.value.status_code == 409


def test_glob_double_star(project):
    store, workspace = project
    found = {f["path"] for f in store.glob(workspace, "**/*.py")["files"]}
    assert found == {"src/app.py", "src/util/helpers.py"}
    assert {f["path"] for f in store.glob(workspace, "src/*.py")["files"]} == {"src/app.py"}
    assert glob_regex("[!a]*.md").match("b.md") and not glob_regex("[!a]*.md").match("a.md")


def test_grep_caps_and_binary_skip(project):
    store, workspace = project
    hits = store.grep(workspace, "TODO")
    assert [(m["path"], m["line"]) for m in hits["matches"]] == [("README.md", 2)]
    assert (
        store.grep(workspace, "value", path_glob="src/**", ignore_case=True)["files_with_matches"]
        == 1
    )
    assert len(store.grep(workspace, ".", max_matches=3)["matches"]) == 3
    for bad in ("(a+)+$", "(", "x" * 600):
        with pytest.raises(HTTPException):
            store.grep(workspace, bad)


async def test_skill_tools_use_the_selected_project(project):
    store, workspace = project
    skill = CodingWorkspaceSkill()
    principal, selected = bind_principal(USER), bind_workspace(workspace)
    try:
        numbered = await skill.read(path="src/app.py", offset=1, limit=1)
        assert numbered["content"].startswith("     1\tdef add")
        edited = await skill.edit(path="README.md", old_string="# Demo", new_string="# Mizan")
        assert edited["replacements"] == 1
        assert (await skill.grep(pattern="Mizan"))["matches"][0]["path"] == "README.md"
        assert len((await skill.glob(pattern="**/*.md"))["files"]) == 1
        assert {"workspace_edit", "workspace_glob", "workspace_grep"} <= {
            schema["name"] for schema in skill.get_tool_schemas()
        }
    finally:
        reset_workspace(selected)
        reset_principal(principal)


def test_new_tools_trusted_only_as_bound_methods():
    registry = SkillRegistry()
    registry.register(CodingWorkspaceSkill())
    registry.register(WebBrowseSkill())
    for name in ("workspace_edit", "workspace_glob", "workspace_grep"):
        assert allows_user_workspace_tool(name, registry, native_tools={})
    assert allows_user_web_tool("web_browse", registry, native_tools={})
    assert allows_user_web_tool("web_search", registry, native_tools={})
    assert not allows_user_web_tool("web_browse", registry, native_tools={"web_browse": print})
    assert not allows_user_web_tool("http_get", registry)


async def test_web_browse_refuses_internal_addresses():
    skill = WebBrowseSkill()
    for url in (
        "http://127.0.0.1:8000/api/status",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/",
        "file:///etc/passwd",
    ):
        result = await skill.browse(url)
        assert "error" in result and "content" not in result


def test_bulk_text_files_for_preview_skips_heavy_and_binary(project):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import coding_workspace as api

    store, workspace = project
    store.write(workspace, "node_modules/react/index.js", "module.exports = {}")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: USER
    data = TestClient(app).get(f"/api/workspaces/{workspace}/files").json()
    assert set(data["files"]) == {"src/app.py", "src/util/helpers.py", "README.md"}
    other = TokenPayload("bob", "Bob", ["user"], 9999999999, 0, "bob-token")
    app.dependency_overrides[api.require_auth] = lambda: other
    assert TestClient(app).get(f"/api/workspaces/{workspace}/files").status_code == 404


def test_scratch_project_is_created_once_and_reused(tmp_path, monkeypatch):
    from skills.builtin.coding_workspace import SCRATCH_PROJECT, scratch_project
    from workspace.store import WorkspaceStore

    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    store = WorkspaceStore("scratch-owner")
    first = scratch_project(store)
    assert scratch_project(store) == first
    assert [item["name"] for item in store.list()] == [SCRATCH_PROJECT]
    assert scratch_project(WorkspaceStore("someone-else")) != first
