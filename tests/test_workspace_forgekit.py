"""ForgeKit in the sandbox: workspace_verify, workspace_impact, workspace_docs_check.

The JSON fixtures in ``tests/fixtures/forgekit`` are ForgeKit 1.26.0's real answers
(``forge verify|impact|docs sync --json``), recorded on tiny npm and Python projects and
with their scratch paths replaced by /workspace. The sandbox is faked here; one test runs
the very command MIZAN sends against the real ForgeKit when it is installed locally.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from security.approvals import ApprovalContext, tool_category
from security.auth import TokenPayload, bind_principal, reset_principal
from skills.builtin import coding_workspace as skill_module
from skills.builtin.coding_workspace import CodingWorkspaceSkill, allows_user_workspace_tool
from skills.registry import SkillRegistry
from workspace import forgekit
from workspace.context import bind_workspace, reset_workspace
from workspace.store import WorkspaceStore

FIXTURES = Path(__file__).parent / "fixtures" / "forgekit"
ROOT = Path(__file__).parent.parent
USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")
TOOLS = ("workspace_verify", "workspace_impact", "workspace_docs_check")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def answer(mark: str, data: dict | None, *, code: int = 0, baseline: str = "project") -> str:
    """What the command prints in the sandbox for ForgeKit's ``data``."""
    body = json.dumps(data) if data is not None else "{}"
    return f"@@mizan-forge-{mark} exit {code} baseline {baseline}\n{body}\n@@mizan-forge-{mark} stderr\n"


def mark_of(command: str) -> str:
    found = re.search(r"@@mizan-forge-([0-9a-f]+)", command)
    assert found, command
    return found.group(1)


# ── What ForgeKit's real JSON says ───────────────────────────────────────


def test_a_passing_npm_suite_is_read_with_its_command_and_counts():
    found = forgekit.verification(fixture("verify-pass-npm.json"))
    assert found["verdict"] == "PASS" and found["passed"] and found["has_tests"]
    assert found["commands"] == [
        {
            "command": "npm test",
            "cwd": ".",
            "status": "PASS",
            "exit_code": 0,
            "duration_ms": 191,
            "counts": {"total": 1, "pass": 1, "fail": 0, "skipped": 0},
        }
    ]
    assert found["counts"] == {"total": 1, "pass": 1, "fail": 0, "skipped": 0}
    assert found["test_integrity"] == "clear" and not found["mutated"]
    assert found["forge"]["version"] == forgekit.FORGEKIT_VERSION
    assert found["forge"]["dirty_hash"] and found["forge"]["scheme"] == "manifest-v3"


def test_a_failing_suite_carries_its_output_for_the_repair():
    found = forgekit.verification(fixture("verify-fail-npm.json"))
    assert found["verdict"] == "FAIL" and not found["passed"]
    assert found["counts"] == {"total": 1, "pass": 0, "fail": 1, "skipped": 0}
    assert "AssertionError" in found["detail"] and "actual: -1" in found["detail"]


def test_no_test_command_and_a_missing_runner_are_not_a_pass():
    none = forgekit.verification(fixture("verify-not-configured.json"))
    assert none["verdict"] == "NOT_CONFIGURED" and not none["has_tests"] and not none["passed"]
    assert none["commands"] == [] and none["counts"] is None
    assert "no recognizable project manifest" in none["detail"]
    missing = forgekit.verification(fixture("verify-incomplete-no-pytest.json"))
    assert missing["verdict"] == "INCOMPLETE" and not missing["passed"]
    assert missing["commands"][0]["command"] == "pytest -q"
    assert missing["commands"][0]["counts"] is None  # pytest reports no counts to ForgeKit
    assert "pytest not on PATH" in missing["detail"]


def test_an_unknown_verdict_is_refused():
    with pytest.raises(forgekit.ForgeKitError) as refused:
        forgekit.verification({"tests": {"status": "GREEN"}})
    assert refused.value.code == "bad_answer"


def test_impact_lists_the_predicted_files():
    found = forgekit.impact(fixture("impact-symbol.json"))
    assert found["target"] == "sum" and found["found"]
    assert found["defined_in"] == ["sum.js"]
    assert found["files"] == ["README.md", "test/sum.test.js", "total.js"]
    assert found["direct"] == ["total.js", "test/sum.test.js", "README.md"]
    assert found["hops"] == {"1": 3} and not found["truncated"]
    assert found["graph"] == {"nodes": 7, "edges": 10, "capped": False}
    nothing = forgekit.impact(fixture("impact-missing.json"))
    assert not nothing["found"] and nothing["files"] == []


def test_docs_sync_names_the_stale_doc_and_line():
    found = forgekit.docs(fixture("docs-sync-stale.json"))
    assert found["changed_files"] == ["total.js"] and found["base"] == "HEAD"
    assert found["stale"] == [
        {
            "file": "README.md",
            "hits": [
                {
                    "identifier": "computeTotal",
                    "line": 3,
                    "text": "`sum(a, b)` adds two numbers; `computeTotal(items)` adds a list "
                    "with `sum`.",
                }
            ],
        }
    ]
    clean = forgekit.docs(fixture("docs-sync-clean.json"))
    assert clean["stale"] == [] and clean["changed_files"] == []
    with pytest.raises(forgekit.ForgeKitError) as unborn:
        forgekit.docs({"error": "unknown base ref: HEAD", "stale": []})
    assert unborn.value.code == "no_git"


# ── The command and its answer ───────────────────────────────────────────


def test_the_command_uses_the_images_forgekit_and_puts_its_state_back():
    mark = "ab" * 16
    script = forgekit.command(["verify"], mark, git="snapshot", limit=90)
    # The image's ForgeKit and node, never the project's node_modules/.bin.
    assert f"{forgekit.NODE} {forgekit.FORGE} verify --json" in script
    assert f"[ ! -x {forgekit.FORGE} ]" in script and "missing" in script
    assert f"{forgekit.TIMEOUT} -k 5 90" in script and f"{forgekit.GIT} add -A" in script
    assert " git " not in script  # every git the script runs is the image's
    # .forge is copied before and put back after; a project without git gets a snapshot.
    assert 'cp -a .forge "$S/kept"' in script and 'mv "$S/kept" .forge' in script
    assert (
        script.index("cp -a .forge") < script.index("verify --json") < script.index("rm -rf .forge")
    )
    assert 'G="$PWD/$S/git"' in script and 'GIT_DIR="$G"; GIT_WORK_TREE="$PWD"' in script
    exclude = next(line for line in script.splitlines() if "info/exclude" in line)
    assert all(f" {name}/" in exclude for name in ("node_modules", ".cache", ".forge"))
    assert f"S=.cache/mizan-forge/{mark}" in script
    plain = forgekit.command(["impact", "sum"], mark)
    assert "MIZAN snapshot" in script  # only verify commits a snapshot of a git-less project
    assert "MIZAN snapshot" not in plain and "nogit" not in plain
    docs = forgekit.command(["docs", "sync", "--base", "HEAD"], mark, git="require")
    assert 'if [ -z "$H" ]; then echo "$M nogit"' in docs and "MIZAN snapshot" not in docs
    for bad in ({"mark": "not-hex"}, {"git": "maybe"}):
        with pytest.raises(ValueError):
            forgekit.command(["verify"], **{"mark": mark, **bad})


def test_git_never_reads_the_projects_config_hooks_or_attributes_files():
    mark = "cd" * 16
    for mode in forgekit.GIT_MODES:
        script = forgekit.command(["impact", "sum"], mark, git=mode)
        for setting in (
            "GIT_CONFIG_NOSYSTEM=1",
            "GIT_CONFIG_GLOBAL=/dev/null",
            "GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false",
            "GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null",
            "GIT_CONFIG_KEY_2=core.pager GIT_CONFIG_VALUE_2=cat",
        ):
            assert setting in script, (mode, setting)
        # ForgeKit reads git through a git directory of MIZAN's own, set before it runs.
        assert script.index('GIT_DIR="$G"') < script.index(f"{forgekit.FORGE} impact")
        assert '"$PWD/.git/objects" > "$G/objects/info/alternates"' in script


def test_the_answer_is_read_after_this_runs_marker_only():
    mark, other = "1" * 32, "2" * 32
    data, code, baseline = forgekit.read(
        answer(mark, fixture("verify-pass-npm.json"), baseline="snapshot"), mark
    )
    assert data["ok"] is True and code == 0 and baseline == "snapshot"
    # A test that prints another run's marker cannot answer for this one.
    forged = answer(other, {"tests": {"status": "PASS"}})
    for stdout, code_name in [
        (forged, "no_answer"),
        (f"@@mizan-forge-{mark} missing\n", "forgekit_missing"),
        (f"@@mizan-forge-{mark} nogit\n", "no_git"),
        (answer(mark, None, code=124), "timeout"),
        (answer(mark, None, code=1) + "node: bad option\n", "bad_answer"),
        ("", "no_answer"),
    ]:
        with pytest.raises(forgekit.ForgeKitError) as refused:
            forgekit.read(stdout, mark)
        assert refused.value.code == code_name
    assert forgekit.ForgeKitError("forgekit_missing", forgekit.MISSING).result() == {
        "error": "ForgeKit is not installed in this sandbox image; the runner needs upgrading",
        "code": "forgekit_missing",
    }


@pytest.mark.parametrize(
    "symbol,path,expected",
    [
        ("total", None, ["impact", "total"]),
        ("Cart.add", None, ["impact", "Cart.add"]),
        (None, "src/cart.js", ["impact", "src/cart.js"]),
    ],
)
def test_an_impact_target_is_one_symbol_or_project_path(symbol, path, expected):
    assert forgekit.impact_args(symbol, path) == expected


@pytest.mark.parametrize(
    "symbol,path",
    [(None, None), ("a", "b.js"), ("--diff", None), ("rm -rf", None), (None, "../x"),
     (None, "/etc/passwd"), (None, "--record"), ("x" * 201, None)],
)  # fmt: skip
def test_an_impact_target_cannot_be_a_flag_or_leave_the_project(symbol, path):
    with pytest.raises(forgekit.ForgeKitError) as refused:
        forgekit.impact_args(symbol, path)
    assert refused.value.code == "invalid"


def test_tests_are_looked_for_only_where_forgekit_finds_a_manifest():
    assert forgekit.needs_tests(["index.html", "web/package.json"])
    assert forgekit.needs_tests({"pyproject.toml"})
    assert not forgekit.needs_tests(["main.py", "test_main.py", "README.md"])


def test_the_runtime_image_pins_this_forgekit_and_checks_it_runs():
    dockerfile = (ROOT / "docker" / "Dockerfile.workspace-runtime").read_text()
    package = f"@codewithjuber/forgekit@{forgekit.FORGEKIT_VERSION}"
    assert package in dockerfile and "forgekit@latest" not in dockerfile
    step = next(block for block in dockerfile.split("\nRUN ") if package in block)
    assert "forge --version" in step and "proxy_ca" in step


# ── The verification record: bound to the files it tested ────────────────


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    store = WorkspaceStore(USER.user_id)
    workspace = store.create("Shop")["id"]
    store.write(workspace, "package.json", '{"scripts": {"test": "node --test"}}\n')
    store.write(workspace, "sum.js", "export const sum = (a, b) => a + b;\n")
    return store, workspace


def record(store, workspace, verdict="PASS", when="2026-11-28T10:00:00.000000+00:00"):
    tree, _ = store.content_tree(workspace)
    return store.record_verification(
        workspace,
        {"tree": tree, "verdict": verdict, "passed": verdict == "PASS", "checked_at": when},
    )


def test_a_later_edit_makes_the_verification_stale_and_a_restore_brings_it_back(project):
    store, workspace = project
    assert store.verification(workspace) is None
    kept = store.checkpoint(workspace, "verified")
    tested = record(store, workspace)
    current = store.verification(workspace)
    assert current["stale"] is False and current["verdict"] == "PASS"
    assert current["tree"] == tested["tree"] == current["current_tree"]
    assert current["checkpoint_id"] == kept["id"]  # the checkpoint holding the tested files
    listed = store.checkpoints(workspace)[0]
    assert listed["verification"] == {
        "verdict": "PASS",
        "passed": True,
        "checked_at": "2026-11-28T10:00:00.000000+00:00",
    }
    store.write(workspace, "sum.js", "export const sum = (a, b) => a - b;\n")
    edited = store.verification(workspace)
    assert edited["stale"] is True and edited["current_tree"] != tested["tree"]
    store.restore(workspace, kept["id"])
    assert store.verification(workspace)["stale"] is False  # same files, same digest


def test_the_current_files_verification_wins_over_a_newer_one_for_other_files(project):
    store, workspace = project
    record(store, workspace, "FAIL", "2026-11-28T09:00:00.000000+00:00")
    store.write(workspace, "sum.js", "export const sum = (a, b) => a + b + 0;\n")
    record(store, workspace, "PASS", "2026-11-28T11:00:00.000000+00:00")
    store.write(workspace, "sum.js", "export const sum = (a, b) => a + b;\n")
    assert store.verification(workspace)["verdict"] == "FAIL"  # these files failed
    assert store.verification(workspace)["stale"] is False


def test_only_a_tree_digest_is_accepted_and_old_trees_are_dropped(project, monkeypatch):
    from fastapi import HTTPException

    from workspace import store as store_module

    store, workspace = project
    with pytest.raises(HTTPException) as refused:
        store.record_verification(workspace, {"tree": "../../etc", "verdict": "PASS"})
    assert refused.value.status_code == 422
    monkeypatch.setattr(store_module, "MAX_CHECKPOINTS", 2)
    for index in range(3):
        store.write(workspace, "n.txt", str(index))
        record(store, workspace, when=f"2026-11-28T1{index}:00:00.000000+00:00")
    assert len(store._verifications(workspace)) == 2


def test_the_checkpoints_route_shows_the_latest_verification(project):
    from api import coding_workspace as api

    store, workspace = project
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: USER
    client = TestClient(app)
    assert client.get(f"/api/workspaces/{workspace}/checkpoints").json()["verification"] is None
    record(store, workspace)
    body = client.get(f"/api/workspaces/{workspace}/checkpoints").json()
    assert body["verification"]["verdict"] == "PASS" and body["verification"]["stale"] is False
    other = TokenPayload("bob", "Bob", ["user"], 9999999999, 0, "bob-token")
    app.dependency_overrides[api.require_auth] = lambda: other
    assert client.get(f"/api/workspaces/{workspace}/checkpoints").status_code == 404


# ── The tools, with the sandbox faked ────────────────────────────────────


class Sandbox:
    """The live session (or a one-shot run) answering with ForgeKit's recorded JSON."""

    def __init__(self, monkeypatch, *, session=True):
        self.commands: list[dict] = []
        self.reply: dict | None = None
        self.baseline = "project"
        self.prints: str | None = None  # a raw answer instead of ForgeKit's JSON
        self.during = None  # what happens to the project while the run runs
        self.changed: list[str] = []

        async def running(user_id, project):
            return session

        async def execute(user_id, project, command, language, timeout_s):
            return self.run(command, language, timeout_s, sandbox="session")

        async def run_project(store, project, command, language, timeout_s, *, apply=True):
            assert apply is False  # a check copies nothing back
            return self.run(command, language, timeout_s, sandbox="isolated-docker")

        monkeypatch.setattr(skill_module.session_client, "running", running)
        monkeypatch.setattr(skill_module.session_client, "execute", execute)
        monkeypatch.setattr(skill_module, "run_project", run_project)

    def run(self, command, language, timeout_s, sandbox):
        self.commands.append({"command": command, "language": language, "timeout_s": timeout_s})
        if self.during:
            self.during()
        mark = mark_of(command)
        stdout = (
            self.prints.replace("MARK", mark)
            if self.prints is not None
            else answer(mark, self.reply, baseline=self.baseline)
        )
        return {"stdout": stdout, "stderr": "", "exit_code": 0, "changed_files": self.changed,
                "sandbox": sandbox}  # fmt: skip


@pytest.fixture
def bound(project):
    store, workspace = project
    principal, selected = bind_principal(USER), bind_workspace(workspace)
    try:
        yield store, workspace
    finally:
        reset_workspace(selected)
        reset_principal(principal)


async def test_verify_runs_in_the_live_session_and_keeps_the_verdict_with_the_files(
    bound, monkeypatch
):
    store, workspace = bound
    sandbox = Sandbox(monkeypatch)
    sandbox.reply, sandbox.baseline = fixture("verify-pass-npm.json"), "snapshot"
    tested = store.content_tree(workspace)[0]
    result = await CodingWorkspaceSkill().verify()
    assert result["tree"] == result["tree_after"] == tested
    assert result["verdict"] == "PASS" and result["passed"] and result["recorded"]
    assert result["commands"][0]["command"] == "npm test" and result["counts"]["pass"] == 1
    assert result["tree"] == store.content_tree(workspace)[0] and result["bound"]
    assert result["baseline"] == "snapshot" and result["sandbox"] == "session"
    run = sandbox.commands[0]
    assert run["language"] == "shell" and run["timeout_s"] == skill_module.VERIFY_TIMEOUT
    assert "timeout -k 5 580" in run["command"]  # ForgeKit stops before the run does
    assert 'G="$PWD/$S/git"' in run["command"]
    kept = store.verification(workspace)
    assert kept["verdict"] == "PASS" and kept["stale"] is False
    assert kept["commands"] == result["commands"] and "detail" not in kept
    store.write(workspace, "sum.js", "export const sum = (a, b) => b + a;\n")
    assert store.verification(workspace)["stale"] is True


async def test_without_a_session_verify_runs_once_offline_and_copies_nothing_back(
    bound, monkeypatch
):
    store, workspace = bound
    sandbox = Sandbox(monkeypatch, session=False)
    sandbox.reply = fixture("verify-fail-npm.json")
    result = await CodingWorkspaceSkill().verify(timeout_s=900)
    assert result["verdict"] == "FAIL" and not result["passed"] and result["recorded"]
    assert result["sandbox"] == "isolated-docker"
    assert sandbox.commands[0]["timeout_s"] == 120  # a one-shot run's limit
    assert store.verification(workspace)["verdict"] == "FAIL"


async def test_an_older_image_without_forgekit_is_a_typed_error_and_nothing_is_kept(
    bound, monkeypatch
):
    store, workspace = bound
    sandbox = Sandbox(monkeypatch)
    sandbox.prints = "@@mizan-forge-MARK missing\n"
    for call in (
        CodingWorkspaceSkill().verify(),
        CodingWorkspaceSkill().impact(symbol="sum"),
        CodingWorkspaceSkill().docs_check(),
    ):
        assert await call == {"error": forgekit.MISSING, "code": "forgekit_missing"}
    assert store.verification(workspace) is None


async def test_an_edit_during_the_run_leaves_the_verdict_unbound(bound, monkeypatch):
    store, workspace = bound
    sandbox = Sandbox(monkeypatch)
    sandbox.reply = fixture("verify-pass-npm.json")
    sandbox.during = lambda: store.write(workspace, "sum.js", "export const sum = 0;\n")
    result = await CodingWorkspaceSkill().verify()
    assert result["verdict"] == "PASS" and result["bound"] is False
    assert result["recorded"] is False and "not bound" in result["note"]
    assert store.verification(workspace) is None


async def test_the_verdict_is_kept_for_the_tree_that_was_tested_not_its_outputs(bound, monkeypatch):
    store, workspace = bound
    sandbox = Sandbox(monkeypatch)
    sandbox.reply = fixture("verify-pass-npm.json")
    tested = store.content_tree(workspace)[0]
    sandbox.during = lambda: store.write(workspace, "junit.xml", "<testsuites/>\n")
    sandbox.changed = ["junit.xml"]  # pulled back from the session by this run
    result = await CodingWorkspaceSkill().verify()
    assert result["bound"] and result["recorded"]
    # The record is the tree that was tested; the files now hold the run's outputs too,
    # which no test ran against, so it is not the current files' verification.
    after = store.content_tree(workspace)[0]
    assert result["tree"] == tested and result["tree_after"] == after != tested
    kept = store.verification(workspace)
    assert kept["tree"] == tested and kept["tree_after"] == after and kept["stale"] is True
    store.delete(workspace, "junit.xml")  # the tested files again: current
    assert store.verification(workspace)["stale"] is False


async def test_impact_and_docs_check_read_the_project_in_its_sandbox(bound, monkeypatch):
    sandbox = Sandbox(monkeypatch)
    sandbox.reply = fixture("impact-symbol.json")
    found = await CodingWorkspaceSkill().impact(symbol="sum")
    assert found["files"] == ["README.md", "test/sum.test.js", "total.js"]
    assert "verify --json" not in sandbox.commands[0]["command"]
    assert "impact sum --json" in sandbox.commands[0]["command"]
    assert await CodingWorkspaceSkill().impact(symbol="--diff") == {
        "error": "symbol must be a name such as total or Cart.add",
        "code": "invalid",
    }
    assert len(sandbox.commands) == 1  # a refused target never reaches the sandbox
    sandbox.reply = fixture("docs-sync-stale.json")
    stale = await CodingWorkspaceSkill().docs_check()
    assert stale["stale"][0]["file"] == "README.md"
    assert "docs sync --base HEAD --json" in sandbox.commands[-1]["command"]
    sandbox.prints = "@@mizan-forge-MARK nogit\n"
    assert (await CodingWorkspaceSkill().docs_check())["code"] == "no_git"


def test_the_three_tools_are_the_skills_own_and_discoverable():
    skill = CodingWorkspaceSkill()
    schemas = {schema["name"]: schema for schema in skill.get_tool_schemas()}
    assert set(TOOLS) <= set(schemas)
    assert schemas["workspace_impact"]["input_schema"]["properties"].keys() >= {"symbol", "path"}
    assert schemas["workspace_verify"]["input_schema"]["required"] == []
    registry = SkillRegistry()
    registry.register(skill)
    for name in TOOLS:
        assert allows_user_workspace_tool(name, registry, native_tools={})
        assert not allows_user_workspace_tool(name, registry, native_tools={name: print})


async def test_the_action_form_reaches_the_tools(bound, monkeypatch):
    sandbox = Sandbox(monkeypatch)
    sandbox.reply = fixture("impact-missing.json")
    found = await CodingWorkspaceSkill().execute({"action": "impact", "symbol": "nosuchthing"})
    assert found["found"] is False


# ── Approvals: ForgeKit's reads observe, verify runs the project's code ───


def test_impact_and_docs_check_are_reads_and_verify_runs_like_workspace_run():
    from agents.base import BaseAgent

    for name in ("workspace_impact", "workspace_docs_check"):
        hint = BaseAgent._read_only_hint(name)
        assert hint and tool_category(name, hint) == "read"
        for mode in ("ask", "auto_edits", "plan"):
            context = ApprovalContext("u", "s", mode)
            assert not context.needs_approval(name, hint) and not context.blocks(name, hint)
    hint = BaseAgent._read_only_hint("workspace_verify")
    assert hint is False
    assert tool_category("workspace_verify", hint) == tool_category("workspace_run") == "execute"
    assert ApprovalContext("u", "s", "auto_edits").needs_approval("workspace_verify")
    assert not ApprovalContext("u", "s", "auto").needs_approval("workspace_verify")
    assert ApprovalContext("u", "s", "plan").blocks("workspace_verify")
    unattended = ApprovalContext("u", "s", "auto_edits", deferred=True)
    assert not unattended.needs_approval("workspace_verify")  # in the sandbox, like run
    assert not unattended.needs_approval("workspace_run")


def test_the_handoff_model_gets_the_tools_and_their_results_are_data():
    from agents import base

    assert set(TOOLS) <= base.WORKSPACE_AGENT_TOOLS
    assert set(TOOLS) <= base._WORKSPACE_READS


# ── The connector preset ─────────────────────────────────────────────────


def test_forge_cortex_is_a_sandbox_stdio_preset():
    from connectors.presets import presets

    preset = next(item for item in presets() if item["id"] == "forge-cortex")
    assert preset["transport"] == "stdio" and preset["auth"] == "none"
    assert preset["command"] == "forge" and preset["args"] == ["cortex-mcp"]
    assert preset["docs_url"].startswith("https://github.com/CodeWithJuber/forgekit/")
    assert "sandbox" in preset["description"] and "url" not in preset


# ── The real command against the real ForgeKit (when it is installed here) ──


def _real():
    found = shutil.which("forge")
    return found and shutil.which("git") and shutil.which("node") and Path(found).resolve()


@pytest.mark.skipif(not _real(), reason="ForgeKit, git and node are not installed here")
def test_the_command_runs_the_real_forgekit_and_changes_no_file(tmp_path, monkeypatch):
    import hashlib
    import secrets

    monkeypatch.setattr(forgekit, "FORGE", shutil.which("forge"))
    monkeypatch.setattr(forgekit, "NODE", shutil.which("node"))
    monkeypatch.setattr(forgekit, "PYTHON", shutil.which("python3"))
    files = {
        "package.json": '{"name": "tiny", "type": "module", "scripts": {"test": "node --test"}}\n',
        "sum.js": "export function sum(a, b) { return a + b; }\n",
        "test/sum.test.js": 'import { test } from "node:test";\nimport assert from '
        '"node:assert/strict";\nimport { sum } from "../sum.js";\n'
        'test("sum", () => { assert.equal(sum(2, 3), 5); });\n',
        ".forge/forge.config.json": '{"verify": {}}\n',  # the project's own ForgeKit config
    }
    for path, content in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(content)

    def tree():
        return {
            str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file()
        }

    def run(args, git):
        mark = secrets.token_hex(16)
        done = subprocess.run(
            ["/bin/sh", "-c", forgekit.command(args, mark, git=git, limit=90)],
            cwd=tmp_path, capture_output=True, text=True, timeout=120,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin:" + str(Path(shutil.which("node")).parent),
                 "HOME": str(tmp_path.parent / "home")},
        )  # fmt: skip
        assert done.returncode == 0, done.stderr
        return forgekit.read(done.stdout, mark)

    before = tree()
    data, _code, baseline = run(["verify"], "snapshot")
    found = forgekit.verification(data)
    assert baseline == "snapshot" and found["verdict"] == "PASS", found["detail"]
    assert found["counts"] == {"total": 1, "pass": 1, "fail": 0, "skipped": 0}
    assert tree() == before  # .forge as it was, no .cache left behind
    (tmp_path / "sum.js").write_text("export function sum(a, b) { return a - b; }\n")
    failed = forgekit.verification(run(["verify"], "snapshot")[0])
    assert failed["verdict"] == "FAIL" and "AssertionError" in failed["detail"]
    impact = forgekit.impact(run(["impact", "sum"], "any")[0])
    assert impact["found"] and "test/sum.test.js" in impact["files"]
    with pytest.raises(forgekit.ForgeKitError) as no_git:
        run(["docs", "sync", "--base", "HEAD"], "require")
    assert no_git.value.code == "no_git"


# ── A repository whose git config would run commands runs none of them ────

HOSTILE = ("fsmonitor", "external", "textconv", "clean", "smudge", "process", "hook",
           "pager", "global")  # fmt: skip


def _hostile_repo(root: Path, bin_dir: Path) -> None:
    """A project whose .git/config, info/attributes and ~/.gitconfig name programs; each
    program leaves a file named after it in ``bin_dir`` when git runs it."""
    bin_dir.mkdir()
    for name in HOSTILE:
        program = bin_dir / name
        program.write_text(f"#!/bin/sh\ntouch {bin_dir}/fired-{name}\ncat\n")
        program.chmod(0o755)
    files = {
        "package.json": '{"name": "tiny", "type": "module", "scripts": {"test": "node --test"}}\n',
        "total.js": "export function computeTotal(items) { return items.length; }\n",
        "README.md": "# tiny\n\n`computeTotal(items)` counts the items.\n",
        ".gitattributes": "*.js diff=evil filter=evil\n*.md filter=proc\n",
        "notes.txt": "a note\n",
    }
    for path, content in files.items():
        (root / path).write_text(content)
    clean = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=clean)

    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "init")
    for key, program in [
        ("core.fsmonitor", "fsmonitor"), ("diff.external", "external"),
        ("diff.evil.textconv", "textconv"), ("filter.evil.clean", "clean"),
        ("filter.evil.smudge", "smudge"), ("filter.proc.process", "process"),
        ("core.hooksPath", ""), ("core.pager", "pager"),
    ]:  # fmt: skip
        git("config", key, str(bin_dir / program) if program else str(bin_dir))
    (bin_dir / "post-index-change").write_text(f"#!/bin/sh\ntouch {bin_dir}/fired-hook\n")
    (bin_dir / "post-index-change").chmod(0o755)
    (root / ".git" / "info" / "attributes").write_text("*.txt filter=evil\n")
    (root / "notes.txt").write_text("a changed note\n")  # filtered by info/attributes
    # The uncommitted change ForgeKit is asked about.
    (root / "total.js").write_text("export function computeTotal(items) { return 0; }\n")


def _run(root, args, git_mode, home):
    import secrets

    mark = secrets.token_hex(16)
    done = subprocess.run(
        ["/bin/sh", "-c", forgekit.command(args, mark, git=git_mode, limit=90)],
        cwd=root, capture_output=True, text=True, timeout=120,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin:" + str(Path(shutil.which("node")).parent),
             "HOME": str(home)},
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    return forgekit.read(done.stdout, mark)


# Stands in for ForgeKit: runs the git commands ForgeKit's verify, impact and docs sync run
# (diffs of the work tree and the index, status, the untracked list) and reports the diff.
FAKE_FORGE = """
const { execFileSync } = require("node:child_process");
const git = (...args) => execFileSync("git", args, { encoding: "utf8" });
const diff = git("diff", "--unified=0", "HEAD");
git("diff", "--cached"); git("status", "--porcelain"); git("ls-files", "--others", "--exclude-standard");
const head = git("rev-parse", "HEAD").trim();
console.log(JSON.stringify({ tests: { status: "PASS" }, head, diff }));
"""


@pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("node") and Path(forgekit.GIT).exists()),
    reason="git and node are not installed here",
)
def test_a_hostile_git_config_runs_nothing_and_the_history_still_reads(tmp_path, monkeypatch):
    project, bin_dir, home = tmp_path / "project", tmp_path / "bin", tmp_path / "home"
    project.mkdir()
    home.mkdir()
    _hostile_repo(project, bin_dir)
    (home / ".gitconfig").write_text(f"[core]\n\tfsmonitor = {bin_dir}/global\n")
    fake = tmp_path / "forge.cjs"
    fake.write_text(FAKE_FORGE)
    fake.chmod(0o755)
    monkeypatch.setattr(forgekit, "FORGE", str(fake))
    monkeypatch.setattr(forgekit, "NODE", shutil.which("node"))
    monkeypatch.setattr(forgekit, "PYTHON", shutil.which("python3"))
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True, check=True
    ).stdout.strip()
    for mode in forgekit.GIT_MODES:
        data, _code, baseline = _run(project, ["verify"], mode, home)
        assert baseline == "project" and data["head"] == expected
        # The project's history is read: the uncommitted change is in the diff.
        assert "return 0;" in data["diff"] and "return items.length" in data["diff"]
        assert sorted(p.name for p in bin_dir.glob("fired-*")) == [], mode
    assert not list(project.rglob(".cache"))


@pytest.mark.skipif(not _real(), reason="ForgeKit, git and node are not installed here")
def test_the_real_forgekit_reads_a_hostile_repository_without_running_it(tmp_path, monkeypatch):
    project, bin_dir, home = tmp_path / "project", tmp_path / "bin", tmp_path / "home"
    project.mkdir()
    home.mkdir()
    _hostile_repo(project, bin_dir)
    monkeypatch.setattr(forgekit, "FORGE", shutil.which("forge"))
    monkeypatch.setattr(forgekit, "NODE", shutil.which("node"))
    monkeypatch.setattr(forgekit, "PYTHON", shutil.which("python3"))
    stale = forgekit.docs(_run(project, ["docs", "sync", "--base", "HEAD"], "require", home)[0])
    assert stale["changed_files"] == ["notes.txt", "total.js"]  # never MIZAN's own state
    assert [entry["file"] for entry in stale["stale"]] == ["README.md"]
    impact = forgekit.impact(_run(project, ["impact", "computeTotal"], "any", home)[0])
    assert impact["found"]
    assert sorted(p.name for p in bin_dir.glob("fired-*")) == []
