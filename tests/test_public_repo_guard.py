"""The workflows of a public repository (scripts/ci/public-repo-guard.sh; docs/ci-artifacts.md)."""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
GUARD = ROOT / "scripts/ci/public-repo-guard.sh"
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))
PIN = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
# The workflows that reach production: never on a pull request, always behind the environment.
PRODUCTION = {
    "deploy.yml",
    "auto-release.yml",
    "chat-stream-diagnostics.yml",
    "research-import.yml",
    "research-import-key.yml",
    "workspace-runner-diagnostics.yml",
    "workspace-runner-preflight.yml",
    "workspace-runner-recovery.yml",
    "workspace-runner-setup.yml",
}


def guard(tmp_path, text):
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(text)
    return subprocess.run(["bash", str(GUARD), str(workflow)], capture_output=True, text=True)


def job(runs_on, steps=f"      - uses: {PIN}\n"):
    return f"on: push\njobs:\n  a:\n    runs-on: {runs_on}\n    steps:\n{steps}"


def test_the_repository_keeps_the_rules():
    result = subprocess.run(["bash", str(GUARD)], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("runs_on", ["ubuntu-24.04", "ubuntu-latest", "'ubuntu-22.04'", "macos-15"])
def test_a_standard_hosted_runner_passes(tmp_path, runs_on):
    assert guard(tmp_path, job(runs_on)).returncode == 0


@pytest.mark.parametrize(
    "runs_on",
    [
        "[self-hosted, linux, x64, mizan]",
        "self-hosted",
        "ubuntu-24.04-4core",  # a larger runner: billed
        "${{ matrix.os }}",
        "${{ vars.RUNNER }}",
        "\n      group: big-runners",
        "\n      - self-hosted\n      - linux",
    ],
)
def test_a_self_hosted_larger_or_chosen_runner_fails(tmp_path, runs_on):
    result = guard(tmp_path, job(runs_on))
    assert result.returncode == 1
    assert "workflow.yml:4:" in result.stdout


@pytest.mark.parametrize(
    "uses",
    ["actions/checkout@v7", "actions/checkout@main", "owner/repo/.github/workflows/x.yml@v1"],
)
def test_an_action_not_pinned_to_a_commit_fails(tmp_path, uses):
    result = guard(tmp_path, job("ubuntu-24.04", f"      - uses: {uses}\n"))
    assert result.returncode == 1 and "full commit SHA" in result.stdout


def test_local_and_docker_actions_need_no_pin(tmp_path):
    steps = "      - uses: ./.github/actions/local\n      - uses: docker://alpine:3\n"
    assert guard(tmp_path, job("ubuntu-24.04", steps)).returncode == 0


def test_pull_request_target_never_runs_the_pull_requests_code(tmp_path):
    target = (
        "on:\n  pull_request_target:\n    types: [opened]\njobs:\n  a:\n    runs-on: ubuntu-24.04\n"
    )
    checkout = f"    steps:\n      - uses: {PIN}\n"
    head = "    steps:\n      - run: echo ${{ github.event.pull_request.head.sha }}\n"
    assert guard(tmp_path, target + checkout).returncode == 1
    assert guard(tmp_path, target + head).returncode == 1
    assert guard(tmp_path, target + "    steps:\n      - run: echo ok\n").returncode == 0
    # The same checkout under pull_request runs with a read-only token: allowed.
    assert (
        guard(tmp_path, target.replace("pull_request_target", "pull_request") + checkout).returncode
        == 0
    )


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_every_workflow_reads_by_default_and_keeps_no_credentials(workflow):
    data = yaml.safe_load(workflow.read_text())
    assert data["permissions"] == {"contents": "read"}, workflow.name
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False, workflow.name


@pytest.mark.parametrize("name", sorted(PRODUCTION))
def test_production_workflows_wait_for_the_environment_and_use_a_key(name):
    text = (ROOT / ".github/workflows" / name).read_text()
    data = yaml.safe_load(text)
    assert "pull_request" not in data[True] and "pull_request_target" not in data[True], name
    ssh_jobs = [job for job in data["jobs"].values() if "DEPLOY_SSH_KEY" in str(job)]
    assert ssh_jobs, name
    assert all(job.get("environment") == "production" for job in ssh_jobs), name
    assert "sshpass" not in text and "SSH_COMPUTING_HOST" not in text, name
    assert "StrictHostKeyChecking=yes" in text and "known_hosts" in text, name


def test_auto_release_stays_off_until_the_owner_turns_it_on():
    data = yaml.safe_load((ROOT / ".github/workflows/auto-release.yml").read_text())
    assert "vars.ENABLE_AUTO_RELEASE == 'true'" in data["jobs"]["determine-release"]["if"]
