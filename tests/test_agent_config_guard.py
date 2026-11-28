"""Pull requests that change what coding agents run (scripts/ci/agent-config-guard.sh; docs/forgekit.md)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GUARD = ROOT / "scripts/ci/agent-config-guard.sh"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A repository holding the guard and one base commit."""
    (tmp_path / "scripts/ci").mkdir(parents=True)
    shutil.copy(GUARD, tmp_path / "scripts/ci/agent-config-guard.sh")
    (tmp_path / "README.md").write_text("base\n")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def change(repo: Path, path: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("changed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"change {path}")


def run(repo: Path, **env: str) -> subprocess.CompletedProcess:
    environment = {
        k: v for k, v in os.environ.items() if k not in {"PR_AUTHOR", "REPO_OWNER", "PR_LABELS"}
    }
    environment.update(env)
    return subprocess.run(
        ["bash", str(repo / "scripts/ci/agent-config-guard.sh")],
        cwd=repo,
        env=environment,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "path",
    [
        ".claude/settings.json",
        ".mcp.json",
        ".codex/hooks.json",
        ".github/hooks/forge.json",
        ".opencode/plugins/x.js",
        "AGENTS.md",
        ".claude/skills/forge-learned-x/SKILL.md",
        ".agents/skills/mizan/SKILL.md",
        ".pi/mcp.json",
        ".forge/decisions.md",
    ],
)
def test_a_stranger_changing_agent_config_needs_the_label(repo, path):
    change(repo, path)
    result = run(repo, PR_AUTHOR="someone", REPO_OWNER="owner", PR_LABELS="bug")
    assert result.returncode == 1
    assert path in result.stdout
    assert "agent-config-reviewed" in result.stderr


def test_the_label_lets_it_through(repo):
    change(repo, ".claude/settings.json")
    result = run(
        repo, PR_AUTHOR="someone", REPO_OWNER="owner", PR_LABELS="bug,agent-config-reviewed"
    )
    assert result.returncode == 0


def test_the_owner_needs_no_label(repo):
    change(repo, ".claude/settings.json")
    assert run(repo, PR_AUTHOR="owner", REPO_OWNER="owner").returncode == 0


def test_other_files_pass_and_a_push_only_lists(repo):
    change(repo, "backend/app.py")
    assert run(repo, PR_AUTHOR="someone", REPO_OWNER="owner").returncode == 0
    change(repo, ".mcp.json")
    pushed = run(repo)
    assert pushed.returncode == 0
    assert "listed only" in pushed.stdout


def test_editing_the_guard_itself_is_watched(repo):
    change(repo, "scripts/ci/agent-config-guard.sh.note")
    assert run(repo, PR_AUTHOR="someone", REPO_OWNER="owner").returncode == 0
    (repo / "scripts/ci/agent-config-guard.sh").write_text(GUARD.read_text() + "\n# edited\n")
    git(repo, "commit", "-q", "-am", "edit guard")
    assert run(repo, PR_AUTHOR="someone", REPO_OWNER="owner").returncode == 1


def test_the_repository_wires_it_into_ci():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "bash scripts/ci/agent-config-guard.sh" in ci
    assert "labeled" in ci
    # Values reach the script through the environment, never pasted into the shell line.
    assert "run: bash scripts/ci/agent-config-guard.sh\n" in ci
