"""Agent Skills (SKILL.md): parsing, discovery, activation, installs and isolation."""

import io
import tarfile
import zipfile
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_skills import installer, loader, tools
from agent_skills.loader import SkillParseError, parse_skill_md
from agents.specialized import create_agent
from security.auth import TokenPayload, bind_principal, reset_principal
from workspace.context import bind_chat_session, bind_workspace, reset_chat_session, reset_workspace
from workspace.store import WorkspaceStore

ALICE = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")
BOB = TokenPayload("bob", "Bob", ["user"], 9999999999, 0, "bob-token")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    return tmp_path


def skill_md(name, description, body="Do the thing.", extra=""):
    return f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n{body}\n"


def tarball(files: dict[str, bytes], symlink: tuple[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for path, data in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
        if symlink:
            info = tarfile.TarInfo(symlink[0])
            info.type = tarfile.SYMTYPE
            info.linkname = symlink[1]
            bundle.addfile(info)
    return buffer.getvalue()


def test_frontmatter_lenient_parse():
    data, body, notes = parse_skill_md(
        "---\nname: pdf-tools\ndescription: Use this when: the user mentions PDFs\n---\nBody",
        "pdf-tools",
    )
    assert data["description"].startswith("Use this when:") and body == "Body"
    assert any("quoting" in note for note in notes)
    data, _, notes = parse_skill_md("---\ndescription: d\n---\n", "folder-name")
    assert data["name"] == "folder-name" and any("name missing" in n for n in notes)
    _, _, notes = parse_skill_md("---\nname: Bad--Name\ndescription: d\n---\n", "x")
    assert any("lowercase" in n for n in notes) and any("does not match" in n for n in notes)
    for broken in ("no frontmatter", "---\nname: x\n---\n", "---\n: [\n---\n"):
        with pytest.raises(SkillParseError):
            parse_skill_md(broken, "x")


def test_bundled_skills_ship_and_have_clean_metadata():
    names = {skill.name: skill for skill in loader.bundled_skills()}
    assert {"web-app-builder", "python-project", "quran-hadith-sources"} <= set(names)
    assert all(not skill.diagnostics for skill in names.values())


def test_precedence_disable_and_owner_scope(data_dir):
    installer.write_skill(ALICE.user_id, "python-project", "Alice's own Python rules", "Mine.")
    skills = loader.available_skills(ALICE.user_id)
    assert skills["python-project"].scope == "user"
    assert loader.available_skills(BOB.user_id)["python-project"].scope == "bundled"
    loader.set_enabled(ALICE.user_id, "web-app-builder", False)
    assert "web-app-builder" not in loader.available_skills(ALICE.user_id)
    assert "web-app-builder" in loader.available_skills(BOB.user_id)


def test_project_skills_come_from_the_selected_workspace(data_dir):
    store = WorkspaceStore(ALICE.user_id)
    project = store.create("App")["id"]
    store.write(
        project, ".agents/skills/house-style/SKILL.md", skill_md("house-style", "Repo style")
    )
    store.write(project, ".agents/skills/house-style/references/style.md", "Use tabs.")
    skills = loader.available_skills(ALICE.user_id, project)
    assert skills["house-style"].scope == "project"
    assert skills["house-style"].files == ["references/style.md"]
    assert skills["house-style"].read("references/style.md") == b"Use tabs."
    assert "house-style" not in loader.available_skills(BOB.user_id)


async def test_catalog_in_activate_skill_enum_and_activation_persists(data_dir):
    agent = create_agent("general", name="Skilled", wali=MagicMock(), izn=MagicMock())
    agent.ai_client = MagicMock(supports_tools=True)
    principal, session = bind_principal(ALICE), bind_chat_session("chat-7")
    try:
        schemas = {s["name"]: s for s in tools.tool_schemas(ALICE.user_id, None)}
        enum = schemas["activate_skill"]["input_schema"]["properties"]["name"]["enum"]
        assert "quran-hadith-sources" in enum
        assert "quran-hadith-sources:" in schemas["activate_skill"]["description"]
        result = await agent._tool_activate_skill("quran-hadith-sources")
        assert result["instructions"].startswith('<skill_content name="quran-hadith-sources">')
        assert "surah:ayah" in result["instructions"]
        later = agent._build_messages("next question", {"session_id": "chat-7"})
        assert "[ACTIVE SKILLS" in later[-2]["content"]
        assert (await agent._tool_activate_skill("missing-skill"))["error"]
        assert "activate_skill" in {s["name"] for s in agent.get_tool_schemas()}
    finally:
        reset_chat_session(session)
        reset_principal(principal)


async def test_read_skill_file_confined(data_dir):
    root = loader.user_root(ALICE.user_id) / "notes"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text(skill_md("notes", "Notes skill"))
    (root / "references" / "a.md").write_text("alpha")
    (data_dir / "secret.txt").write_text("secret")
    principal = bind_principal(ALICE)
    try:
        assert tools.read_file("notes", "references/a.md")["content"] == "alpha"
        for escape in ("../secret.txt", "/etc/passwd", "references/../../secret.txt", ""):
            assert "error" in tools.read_file("notes", escape)
    finally:
        reset_principal(principal)


def test_tar_install_rejects_symlink_traversal_oversize(data_dir):
    archive = tarball(
        {
            "repo-abc123/skills/good/SKILL.md": skill_md("good", "A good skill").encode(),
            "repo-abc123/skills/good/scripts/run.py": b"print(1)",
            "repo-abc123/skills/good/../../escape.txt": b"nope",
            "repo-abc123/skills/big/SKILL.md": skill_md("big", "Too big").encode(),
            "repo-abc123/skills/big/blob.bin": b"x" * (installer.MAX_FILE_BYTES + 1),
        },
        symlink=("repo-abc123/skills/good/link", "/etc/passwd"),
    )
    installed = installer.install_archive(ALICE.user_id, archive, "skills")
    assert {item["name"] for item in installed} == {"good", "big"}
    good = loader.user_root(ALICE.user_id) / "good"
    assert sorted(p.relative_to(good).as_posix() for p in good.rglob("*") if p.is_file()) == [
        "SKILL.md",
        "scripts/run.py",
    ]
    assert not (data_dir / "escape.txt").exists()
    assert not (loader.user_root(ALICE.user_id) / "big" / "blob.bin").exists()
    with pytest.raises(installer.InstallError):
        installer.install_archive(ALICE.user_id, archive, "skills")  # already installed
    with pytest.raises(installer.InstallError):
        installer.install_archive(ALICE.user_id, tarball({"README.md": b"hi"}))


def test_zip_install_and_github_url_parsing(data_dir):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("pdf-tools/SKILL.md", skill_md("pdf-tools", "PDF helpers"))
    assert installer.install_archive(ALICE.user_id, buffer.getvalue())[0]["name"] == "pdf-tools"
    assert installer.parse_github_url("https://github.com/acme/skills") == (
        "acme",
        "skills",
        ["HEAD", "main", "master"],
        "",
    )
    assert installer.parse_github_url(
        "https://github.com/acme/skills/tree/main/document-skills/pdf"
    ) == ("acme", "skills", ["main"], "document-skills/pdf")
    for bad in ("http://github.com/a/b", "https://evil.example/a/b", "https://github.com/a"):
        with pytest.raises(installer.InstallError):
            installer.parse_github_url(bad)


def test_slash_skill_activates_not_command(data_dir):
    assert tools.resolve_slash_skill("/web-app-builder make a todo app", "alice", None) == (
        "web-app-builder",
        "make a todo app",
    )
    assert tools.resolve_slash_skill("/help", "alice", None) is None
    assert tools.resolve_slash_skill("no slash", "alice", None) is None


def test_skills_api_is_owner_scoped(data_dir):
    from api import agent_skills as api

    def client(user):
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.require_auth] = lambda: user
        return TestClient(app)

    alice, bob = client(ALICE), client(BOB)
    created = alice.post(
        "/api/agent-skills",
        json={"name": "my-notes", "description": "Personal notes", "body": "Be brief."},
    )
    assert created.status_code == 200
    assert "my-notes" in {s["name"] for s in alice.get("/api/agent-skills").json()["skills"]}
    assert "my-notes" not in {s["name"] for s in bob.get("/api/agent-skills").json()["skills"]}
    assert alice.get("/api/agent-skills/my-notes").json()["body"] == "Be brief."
    assert bob.get("/api/agent-skills/my-notes").status_code == 404
    assert bob.delete("/api/agent-skills/my-notes").status_code == 404
    toggled = alice.post("/api/agent-skills/python-project/enabled", json={"enabled": False})
    assert toggled.json() == {"name": "python-project", "enabled": False}
    listed = {s["name"]: s for s in alice.get("/api/agent-skills").json()["skills"]}
    assert listed["python-project"]["enabled"] is False
    assert alice.delete("/api/agent-skills/my-notes").status_code == 200
    assert (
        alice.post("/api/agent-skills", json={"name": "Bad Name", "description": "d"}).status_code
        == 422
    )


def test_a_skill_mizan_earned_waits_for_trust_and_says_so(data_dir):
    """Itqan saves an earned skill pending: held from use whatever its words, listed
    as earned, usable once the person trusts it (docs/agent-skills.md)."""
    from api import agent_skills as api

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: ALICE
    alice = TestClient(app)
    installer.write_skill(ALICE.user_id, "mizan-learned-sales", "Earned", "Keywords: sales")
    loader.hold(ALICE.user_id, "mizan-learned-sales")
    listed = {s["name"]: s for s in alice.get("/api/agent-skills").json()["skills"]}
    assert listed["mizan-learned-sales"]["held"] and listed["mizan-learned-sales"]["earned"]
    assert not listed["quran-hadith-sources"]["earned"]
    assert "mizan-learned-sales" not in loader.available_skills(ALICE.user_id)
    assert alice.post("/api/agent-skills/mizan-learned-sales/trust").json()["held"] is False
    assert "mizan-learned-sales" in loader.available_skills(ALICE.user_id)
    # Changing it afterwards holds it again.
    installer.write_skill(
        ALICE.user_id, "mizan-learned-sales", "Earned", "Other words", overwrite=True
    )
    assert "mizan-learned-sales" not in loader.available_skills(ALICE.user_id)


def test_selected_project_binding_reaches_skill_tools(data_dir):
    store = WorkspaceStore(ALICE.user_id)
    project = store.create("App")["id"]
    store.write(project, ".claude/skills/deploy-notes/SKILL.md", skill_md("deploy-notes", "Deploy"))
    principal, selected = bind_principal(ALICE), bind_workspace(project)
    try:
        enum = tools.tool_schemas(ALICE.user_id, project)[0]["input_schema"]["properties"]["name"][
            "enum"
        ]
        assert "deploy-notes" in enum
        assert tools.activate("deploy-notes", record=False)["scope"] == "project"
    finally:
        reset_workspace(selected)
        reset_principal(principal)
