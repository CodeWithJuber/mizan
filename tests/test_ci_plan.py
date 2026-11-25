"""What one CI run checks (scripts/ci/plan.py; docs/ci-artifacts.md, What a run checks)."""

import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("ci_plan", ROOT / "scripts/ci/plan.py")
ci_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_plan)

HEAVY = ("docker", "browser", "build", "frontend_build")
SUITES = ("ruh", "own", "bayan", "utils")


@pytest.fixture
def repo(tmp_path):
    """A small checkout: conftest, a hub module it imports, a leaf only one test reaches."""
    files = {
        "tests/__init__.py": "",
        "tests/conftest.py": "import pytest\n\n\ndef fixture():\n    from hub import shared\n",
        "tests/test_leaf.py": "from leaf.reader import read\n",
        "tests/test_api.py": "import backend.hub.shared\n",
        "tests/test_guide.py": 'GUIDE = "docs/guide.md"\n',
        "tests/test_script.py": 'SCRIPT = ROOT / "scripts" / "tool.sh"\n',
        "tests/test_scan.py": 'for path in BACKEND.rglob("*.py"):\n    pass\n',
        "tests/test_owned_learning_cycle.py": "from mizan_owned import (\n    cycle,  # x\n)\n",
        "backend/hub/__init__.py": "",
        "backend/hub/shared.py": "",
        "backend/leaf/__init__.py": "",
        "backend/leaf/reader.py": "from . import words\n",
        "backend/leaf/words.py": "",
        "backend/leaf/data.json": "{}",
        "backend/lonely.py": "",
        "backend/mizan_owned/__init__.py": "",
        "backend/mizan_owned/cycle.py": "",
        "backend/core/adaptive.py": "",
        "ruh_model/__init__.py": "",
        "ruh_model/model.py": "",
        "ruh_model/tokenizer/__init__.py": "",
        "ruh_model/tokenizer/bayan.py": "",
        "ruh_model/tests/test_model.py": "from ruh_model import model\n",
        "ruh_model/tests/test_tokenizer.py": "from ruh_model.tokenizer import bayan\n",
        "packages/bayan/src/bayan/__init__.py": "",
        "packages/bayan/tests/test_bayan.py": "import bayan\n",
        "research/own_model/tests/test_own.py": "",
        "scripts/tool.sh": "",
        "docs/guide.md": "",
        "docs/other.md": "",
        "frontend/src/App.tsx": "",
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def pull_request(changed, root):
    return ci_plan.plan("pull_request", changed, root)


def push(changed, root, passed_by=None):
    return ci_plan.plan("push", changed, root, passed_by=passed_by)


def selected(result):
    return [] if result["pytest"] == "none" else result["pytest"].split()


def test_a_pull_request_gets_the_unit_tests_its_change_reaches_and_nothing_heavy(repo):
    result = pull_request(["backend/leaf/words.py"], repo)
    # words.py is reached through reader.py; the tree scan reads every backend module.
    assert selected(result) == ["tests/test_leaf.py", "tests/test_scan.py"]
    assert result["lint"] == "false" and result["verified"] == "false"
    assert all(result[job] == "false" for job in HEAVY + ("provenance",))
    assert all(result[suite] == "false" for suite in SUITES)
    assert result["vitest"] == "none"


def test_a_pull_request_runs_a_changed_test_and_the_tests_that_name_a_changed_file(repo):
    assert selected(pull_request(["tests/test_guide.py"], repo)) == ["tests/test_guide.py"]
    assert selected(pull_request(["docs/guide.md"], repo)) == ["tests/test_guide.py"]
    assert selected(pull_request(["scripts/tool.sh"], repo)) == ["tests/test_script.py"]
    # Nothing reads it, so nothing runs; a deleted test file runs nothing either.
    assert pull_request(["docs/other.md", "tests/test_gone.py"], repo)["pytest"] == "none"


@pytest.mark.parametrize(
    "path",
    [
        "tests/conftest.py",  # every test's setup
        "backend/hub/shared.py",  # conftest imports it
        "backend/core/adaptive.py",  # shared code
        "backend/leaf/data.json",  # data a module reads
        "pyproject.toml",  # configuration and dependencies
        "backend/requirements.txt",
        ".github/workflows/docs.yml",  # a workflow
        "scripts/ci/plan.py",
        "backend/lonely.py",  # no test reaches it: the mapping cannot decide
        "backend/leaf/removed.py",  # a deleted module
    ],
)
def test_a_pull_request_runs_every_unit_test_when_the_change_cannot_be_placed(repo, path):
    result = pull_request(["docs/other.md", path], repo)
    assert result["pytest"] == "all"
    assert all(result[suite] == "true" for suite in ("ruh", "own", "bayan"))
    assert all(result[job] == "false" for job in HEAVY)
    assert result["lint"] == "false"


def test_a_pull_request_without_a_diff_runs_every_unit_test(repo):
    result = pull_request(None, repo)
    assert result["pytest"] == "all" and result["vitest"] == "all" and result["utils"] == "true"
    assert all(result[job] == "false" for job in HEAVY)


def test_the_other_unit_test_jobs_run_on_a_pull_request_only_when_it_reaches_them(repo):
    ruh = pull_request(["ruh_model/model.py"], repo)
    assert ruh["ruh"] == "true" and ruh["own"] == "false" and ruh["pytest"] == "none"
    own = pull_request(["backend/mizan_owned/cycle.py"], repo)
    assert own["own"] == "true"
    assert selected(own) == ["tests/test_owned_learning_cycle.py", "tests/test_scan.py"]
    assert pull_request(["research/own_model/tests/test_own.py"], repo)["own"] == "true"
    assert pull_request(["packages/bayan/src/bayan/__init__.py"], repo)["bayan"] == "true"
    # The vendored copy must match ruh_model/tokenizer/ (packages/bayan/scripts/sync_vendor.py).
    tokenizer = pull_request(["ruh_model/tokenizer/bayan.py"], repo)
    assert tokenizer["bayan"] == "true" and tokenizer["ruh"] == "true"
    assert tokenizer["pytest"] == "none"


def test_a_pull_request_runs_the_frontend_specs_its_change_reaches(repo):
    page = pull_request(["frontend/src/App.tsx"], repo)
    assert page["vitest"] == "changed" and page["utils"] == "true" and page["pytest"] == "none"
    configs = ("frontend/package-lock.json", "frontend/vite.config.js", "frontend/tsconfig.json")
    for config in configs:
        assert pull_request([config], repo)["vitest"] == "all", config
    assert pull_request(["backend/leaf/words.py"], repo)["utils"] == "false"


def test_main_after_a_merge_runs_lint_every_unit_test_and_the_heavy_jobs_it_reaches(repo):
    docs = push(["docs/guide.md"], repo)
    assert docs["lint"] == "true" and docs["pytest"] == "all" and docs["vitest"] == "all"
    assert all(docs[suite] == "true" for suite in SUITES)
    assert docs["provenance"] == "true"  # it gates the production images of every push
    assert all(docs[job] == "false" for job in HEAVY)

    def heavy(*paths):
        result = push(list(paths), repo)
        return {job for job in HEAVY if result[job] == "true"}

    assert heavy("frontend/src/App.tsx") == {"docker", "frontend_build"}
    assert heavy("backend/workspace/browse_agent.py") == {"docker", "browser", "build"}
    assert heavy("docker/Dockerfile.workspace-browser") == {"docker", "browser"}
    assert heavy("tests/test_leaf.py", "scripts/tool.sh", "deploy/known_hosts") == set()
    # What it cannot place, and CI itself, run every heavy job.
    assert heavy("newdir/thing.txt") == set(HEAVY)
    assert heavy("scripts/ci/plan.py") == set(HEAVY)
    assert heavy(".github/workflows/ci.yml") == set(HEAVY)
    # No commit before the push to compare with: everything.
    assert {job for job in HEAVY if push(None, repo)[job] == "true"} == set(HEAVY)


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_the_weekly_run_and_a_run_by_hand_check_everything(repo, event):
    result = ci_plan.plan(event, ["docs/other.md"], repo, passed_by="push")
    assert result["verified"] == "false" and result["lint"] == "true"
    assert result["pytest"] == "all" and result["vitest"] == "all"
    assert all(result[name] == "true" for name in HEAVY + SUITES + ("provenance",))


@pytest.mark.parametrize("passed_by", ["push", "schedule", "workflow_dispatch"])
def test_main_skips_to_the_production_images_only_after_a_full_run_passed(repo, passed_by):
    result = push(["backend/leaf/words.py"], repo, passed_by=passed_by)
    assert result["verified"] == "true"
    assert result["lint"] == "false" and result["pytest"] == "none" and result["vitest"] == "none"
    assert all(result[name] == "false" for name in HEAVY + SUITES + ("provenance",))


def test_a_pull_requests_partial_run_never_lets_main_skip(repo):
    result = push(["frontend/src/App.tsx"], repo, passed_by="pull_request")
    assert result["verified"] == "false" and result["lint"] == "true"
    assert result["docker"] == "true" and result["frontend_build"] == "true"


def test_changed_files_needs_a_commit_to_compare_with(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    def commit(name):
        (tmp_path / name).write_text(name)
        git("add", name)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", name)

    git("init", "-q")
    commit("a.txt")
    commit("b.txt")
    assert ci_plan.changed_files("HEAD^1", tmp_path) == ["b.txt"]
    assert ci_plan.changed_files("", tmp_path) is None
    assert ci_plan.changed_files("0" * 40, tmp_path) is None  # a push with no commit before it
    assert ci_plan.changed_files("1" * 40, tmp_path) is None  # one this checkout does not have


def test_the_real_repository_places_a_frontend_change_and_a_test_change():
    # Built from parts, so that this file does not name it.
    page = "/".join(["frontend", "src", "main" + ".tsx"])
    assert ci_plan.plan("pull_request", [page], ROOT)["pytest"] == "none"
    own = "tests/test_ci_plan.py"
    assert ci_plan.plan("pull_request", [own], ROOT)["pytest"] == own


# ci.yml acts on the plan. These pin what the plan cannot enforce by itself.
JOBS = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
QUICK = {"lint", "test", "typecheck", "ruh", "bayan", "frontend", "own-research"}


def needs(job):
    value = JOBS[job].get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def test_heavy_jobs_wait_for_the_quick_ones_and_run_when_the_plan_skipped_them():
    assert all("billing" in needs(job) for job in JOBS if job != "billing")
    for job in ("build", "docker", "browser"):
        assert QUICK <= needs(job), job
        # A quick job the plan skipped must not skip the heavy job; a failed one must.
        assert "!cancelled()" in JOBS[job]["if"] and "!failure()" in JOBS[job]["if"], job
    images = JOBS["production-images"]
    assert QUICK | {"build", "docker", "browser", "provenance"} <= needs("production-images")
    assert "github.event_name == 'push'" in images["if"] and "!failure()" in images["if"]


def test_each_job_runs_only_when_the_plan_says_so():
    outputs = {"lint": "lint", "ruh": "ruh", "bayan": "bayan", "own-research": "own"}
    outputs |= {"build": "build", "docker": "docker", "browser": "browser"}
    outputs |= {"provenance": "provenance", "test": "pytest", "typecheck": "verified"}
    for job, output in outputs.items():
        assert f"needs.billing.outputs.{output}" in JOBS[job]["if"], job
    steps = {step.get("run", ""): step.get("if", "") for step in JOBS["frontend"]["steps"]}
    assert "needs.billing.outputs.lint" in steps["npm run lint"]
    for run in ("npm run build", "npm run size", "npx playwright install chromium && npm run e2e"):
        assert "needs.billing.outputs.frontend_build" in steps[run], run


def test_only_a_full_run_lets_main_skip_its_checks():
    steps = JOBS["billing"]["steps"]
    duplicate = next(step for step in steps if "skip-duplicate-actions" in step.get("uses", ""))
    assert "pull_request" in duplicate["with"]["do_not_skip"]
    # The plan reads which run passed these files: a pull request's partial run never counts.
    planned = next(step for step in steps if "scripts/ci/plan.py" in step.get("run", ""))
    assert "skipped_by" in planned["env"]["SKIPPED_BY"]
    assert JOBS["billing"]["outputs"]["verified"] == "${{ steps.plan.outputs.verified }}"


def test_the_coding_workspace_isolation_runs_once_on_main_after_the_merge():
    triggers = yaml.safe_load((ROOT / ".github/workflows/coding-workspace.yml").read_text())[True]
    assert "pull_request" not in triggers
    assert triggers["push"]["branches"] == ["main"] and triggers["push"]["paths"]
