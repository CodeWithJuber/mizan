"""What one CI run checks (scripts/ci/plan.py; docs/ci-artifacts.md, What a run checks)."""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("ci_plan", ROOT / "scripts/ci/plan.py")
ci_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_plan)

SUITES = ("bayan", "utils")
# Only a full run (a push to main, the weekly run, a run by hand) checks these.
FULL_ONLY = ("lint", "provenance", "browser", "images")


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


def test_a_pull_request_gets_the_unit_tests_its_change_reaches(repo):
    result = pull_request(["backend/leaf/words.py"], repo)
    # words.py is reached through reader.py; the tree scan reads every backend module.
    assert selected(result) == ["tests/test_leaf.py", "tests/test_scan.py"]
    assert result["verified"] == "false"
    assert all(result[name] == "false" for name in SUITES + FULL_ONLY + ("training",))
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
    assert result["bayan"] == "true"
    assert all(result[name] == "false" for name in FULL_ONLY + ("training",))


def test_a_pull_request_without_a_diff_runs_every_unit_test(repo):
    result = pull_request(None, repo)
    assert result["pytest"] == "all" and result["vitest"] == "all" and result["utils"] == "true"


def test_a_pull_request_never_selects_the_model_and_training_tests(repo):
    # They install torch or run the owned model's training stages: weekly and by hand only.
    model = pull_request(["ruh_model/model.py"], repo)
    assert model["pytest"] == "none" and model["bayan"] == "false"
    owned = pull_request(["backend/mizan_owned/cycle.py"], repo)
    assert selected(owned) == ["tests/test_scan.py"]  # not tests/test_owned_learning_cycle.py
    assert pull_request(["research/own_model/tests/test_own.py"], repo)["pytest"] == "none"
    assert pull_request(["tests/test_owned_learning_cycle.py"], repo)["pytest"] == "none"


def test_bayan_runs_on_a_pull_request_only_when_it_reaches_it(repo):
    assert pull_request(["packages/bayan/src/bayan/__init__.py"], repo)["bayan"] == "true"
    # The vendored copy must match ruh_model/tokenizer/ (packages/bayan/scripts/sync_vendor.py).
    tokenizer = pull_request(["ruh_model/tokenizer/bayan.py"], repo)
    assert tokenizer["bayan"] == "true" and tokenizer["pytest"] == "none"
    assert pull_request(["backend/leaf/words.py"], repo)["bayan"] == "false"


def test_a_pull_request_runs_the_frontend_specs_its_change_reaches(repo):
    page = pull_request(["frontend/src/App.tsx"], repo)
    assert page["vitest"] == "changed" and page["utils"] == "true" and page["pytest"] == "none"
    configs = ("frontend/package-lock.json", "frontend/vite.config.js", "frontend/tsconfig.json")
    for config in configs:
        assert pull_request([config], repo)["vitest"] == "all", config
    assert pull_request(["backend/leaf/words.py"], repo)["utils"] == "false"


@pytest.mark.parametrize("event", ["push", "schedule", "workflow_dispatch"])
def test_main_the_weekly_run_and_a_run_by_hand_run_every_unit_test(repo, event):
    # They read no diff: the same answer whatever changed.
    for changed in (["docs/other.md"], ["frontend/src/App.tsx"], None):
        result = ci_plan.plan(event, changed, repo)
        assert result["verified"] == "false"
        assert result["pytest"] == "all" and result["vitest"] == "all"
        # Lint, provenance, the frontend build and browser tests, and the images.
        assert all(result[name] == "true" for name in SUITES + FULL_ONLY)
        # CPU torch and the training stages: the weekly run and a run by hand, not every merge.
        assert result["training"] == ("false" if event == "push" else "true")
    # The weekly run and a run by hand check even files that passed before.
    assert ci_plan.plan(event, None, repo, passed_by="push")["verified"] == (
        "true" if event == "push" else "false"
    )


@pytest.mark.parametrize("passed_by", ["push", "schedule", "workflow_dispatch"])
def test_main_skips_to_the_production_images_only_after_a_full_run_passed(repo, passed_by):
    result = push(["backend/leaf/words.py"], repo, passed_by=passed_by)
    assert result["verified"] == "true"
    assert result["pytest"] == "none" and result["vitest"] == "none"
    assert all(result[name] == "false" for name in SUITES + FULL_ONLY + ("training",))


def test_a_pull_requests_partial_run_never_lets_main_skip(repo):
    result = push(["frontend/src/App.tsx"], repo, passed_by="pull_request")
    assert result["verified"] == "false" and result["pytest"] == "all"
    assert result["vitest"] == "all" and all(result[name] == "true" for name in FULL_ONLY)


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
QUICK = {"lint", "test", "typecheck", "bayan", "frontend"}


def needs(job):
    value = JOBS[job].get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def runs(job):
    return "\n".join(step.get("run", "") for step in JOBS[job]["steps"])


def test_the_images_wait_for_every_check_and_not_for_a_skipped_one():
    assert all("plan" in needs(job) for job in JOBS if job != "plan")
    images = JOBS["images"]
    assert QUICK | {"provenance"} <= needs("images")
    # A check the plan skipped must not hold the images back; a failed one must.
    assert "!cancelled()" in images["if"] and "!failure()" in images["if"]
    assert "needs.plan.outputs.images == 'true'" in images["if"]


def test_each_job_runs_only_when_the_plan_says_so():
    outputs = {"bayan": "bayan", "provenance": "provenance", "test": "pytest", "lint": "lint"}
    outputs |= {"typecheck": "verified", "ruh": "training", "own-research": "training"}
    for job, output in outputs.items():
        assert f"needs.plan.outputs.{output}" in JOBS[job]["if"], job
    # The first job passes on every answer the plan gives, and nothing else.
    given = set(ci_plan.plan("workflow_dispatch", None, ROOT))
    assert set(JOBS["plan"]["outputs"]) == given
    # Only a pull request's plan reads a diff.
    planned = next(step for step in JOBS["plan"]["steps"] if step.get("id") == "plan")
    assert planned["env"]["BASE"] == "${{ github.event_name == 'pull_request' && 'HEAD^1' || '' }}"
    # The first job checks every workflow against the public-repository rules.
    assert "bash scripts/ci/public-repo-guard.sh" in runs("plan")


def test_full_runs_lint_and_start_a_browser():
    # Lint: ruff on the Python, oxlint and the colour ratchet (npm run lint) on the frontend.
    assert "ruff check backend/ nlp/ tests/" in runs("lint")
    assert "ruff format --check backend/ nlp/ tests/" in runs("lint")
    frontend = {step.get("run"): step.get("if", "") for step in JOBS["frontend"]["steps"]}
    assert "needs.plan.outputs.lint == 'true'" in frontend["npm run lint"]
    # The frontend build, its size budget and the browser tests (Playwright, mocked API).
    for command in ("npm run build", "npm run size"):
        assert "needs.plan.outputs.browser == 'true'" in frontend[command], command
    e2e = next(run for run in frontend if run and "npm run e2e" in run)
    assert "playwright install --with-deps chromium" in e2e
    assert "needs.plan.outputs.browser == 'true'" in frontend[e2e]
    # Shahid's browser sandbox runs its self-test with production's hardening.
    images = runs("images")
    assert "python3 -I /browse_selftest.py" in images and "--cap-drop ALL" in images


def test_torch_and_the_training_tests_run_only_weekly_or_by_hand():
    for event in ("pull_request", "push"):
        assert ci_plan.plan(event, None, ROOT)["training"] == "false", event
    for event in ("schedule", "workflow_dispatch"):
        assert ci_plan.plan(event, None, ROOT)["training"] == "true", event
    learning = [path for path in ci_plan.TRAINING_TESTS if path.startswith("tests/")]
    assert len(learning) == 3
    assert "pytest ruh_model/tests/" in runs("ruh")
    assert all(path in runs("own-research") for path in learning)
    assert "research/own_model/tests" in runs("own-research")
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        jobs = yaml.safe_load(workflow.read_text())["jobs"]
        for name, job in jobs.items():
            run = "\n".join(step.get("run", "") for step in job.get("steps", []))
            if workflow.name == "ci.yml" and name in ("ruh", "own-research"):
                continue
            for line in run.splitlines():
                assert not ("pip install" in line and "torch" in line), (workflow.name, line)
            assert "ruh_model/tests" not in run and "own_model/tests" not in run, workflow.name
            # A run of the whole suite names the learning-cycle files only to leave them out.
            for path in learning:
                if path in run or re.search(r"\bpytest tests/(\s|$)", run):
                    assert path in run and "--ignore" in run, (workflow.name, path)


def test_deploy_production_builds_and_sends_what_ci_checks():
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text()
    images = runs("images")
    # The same Dockerfiles: CI builds them as a check, the deploy builds the commit's to ship.
    for dockerfile in ("docker/Dockerfile.backend.prod", "docker/Dockerfile.frontend.prod"):
        assert dockerfile in images and dockerfile in deploy, dockerfile
    for role in ("runtime", "runner", "browser"):
        assert f"workspace-{role} mizan-workspace-{role}:ci --load" in images, role
    assert 'bash scripts/build_workspace_image.sh "workspace-$role"' in deploy
    # The site's two images, then the workspace runner's images the server says it needs.
    assert '"$images/backend:$DEPLOY_SHA" "$images/frontend:$DEPLOY_SHA"' in deploy
    assert "needed='runner runtime browser'" in deploy
    # The backend image is checked for its runtime dependencies before it is used or sent.
    assert images.index("Dockerfile.backend.prod") < images.index("torch.version.cuda is None")
    assert deploy.index("Dockerfile.backend.prod") < deploy.index("torch.version.cuda is None")
    assert deploy.index("torch.version.cuda is None") < deploy.index('docker save "${site[@]}"')
    # Nothing is pushed to or pulled from a registry.
    for text in (deploy, images):
        assert "--push" not in text and "docker push" not in text and "docker login" not in text


def test_only_a_full_run_lets_main_skip_its_checks():
    steps = JOBS["plan"]["steps"]
    duplicate = next(step for step in steps if "skip-duplicate-actions" in step.get("uses", ""))
    assert "pull_request" in duplicate["with"]["do_not_skip"]
    # The plan reads which run passed these files: a pull request's partial run never counts.
    planned = next(step for step in steps if step.get("id") == "plan")
    assert "skipped_by" in planned["env"]["SKIPPED_BY"]
    assert JOBS["plan"]["outputs"]["verified"] == "${{ steps.plan.outputs.verified }}"


def test_the_coding_workspace_isolation_runs_once_on_main_after_the_merge():
    triggers = yaml.safe_load((ROOT / ".github/workflows/coding-workspace.yml").read_text())[True]
    assert "pull_request" not in triggers
    assert triggers["push"]["branches"] == ["main"] and triggers["push"]["paths"]
