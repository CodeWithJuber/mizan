"""Exercise the CI registry fallback with a controlled Docker executable."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/build_workspace_image.sh"


@pytest.fixture
def fake_docker(tmp_path):
    binary = tmp_path / "docker"
    log = tmp_path / "calls.jsonl"
    pushed = tmp_path / "published"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json,os,pathlib,sys\n"
        "log=pathlib.Path(os.environ['WORKSPACE_TEST_LOG'])\n"
        "calls=log.read_text().splitlines() if log.exists() else []\n"
        "statuses=json.loads(os.environ['WORKSPACE_TEST_STATUSES'])\n"
        "with log.open('a') as stream: stream.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "status=statuses[len(calls)] if len(calls)<len(statuses) else 99\n"
        "if status==0 and '--push' in sys.argv:\n"
        " pathlib.Path(os.environ['WORKSPACE_TEST_PUSHED']).write_text('exported')\n"
        "raise SystemExit(status)\n"
    )
    binary.chmod(0o700)

    def invoke(image, mode, statuses, tag="ghcr.io/codewithjuber/mizan/test:fixture"):
        env = os.environ | {
            "PATH": str(tmp_path) + os.pathsep + os.defpath,
            "WORKSPACE_TEST_LOG": str(log),
            "WORKSPACE_TEST_STATUSES": json.dumps(statuses),
            "WORKSPACE_TEST_PUSHED": str(pushed),
        }
        result = subprocess.run(
            ["bash", str(SCRIPT), image, tag, mode],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls, pushed.exists()

    return invoke


@pytest.mark.parametrize("image", ["workspace-runtime", "workspace-runner", "workspace-browser"])
@pytest.mark.parametrize("mode", ["--load", "--push"])
@pytest.mark.parametrize(
    "statuses,expected_registries",
    [
        ([0], ["mirror.gcr.io/library"]),
        ([7, 0], ["mirror.gcr.io/library", "docker.io/library"]),
        ([7, 8], ["mirror.gcr.io/library", "docker.io/library"]),
    ],
)
def test_bounded_fallback_preserves_build_identity_and_failure(
    fake_docker, image, mode, statuses, expected_registries
):
    result, calls, published = fake_docker(image, mode, statuses)
    assert result.returncode == statuses[-1]
    assert len(calls) == len(expected_registries)
    for args, registry in zip(calls, expected_registries, strict=True):
        assert args[:2] == ["buildx", "build"]
        assert args[args.index("--build-arg") + 1] == "BASE_REGISTRY=" + registry
        assert args[args.index("--file") + 1] == "docker/Dockerfile." + image
        assert args[args.index("--tag") + 1] == "ghcr.io/codewithjuber/mizan/test:fixture"
        assert mode in args and args[-1] == "."
        assert ("--provenance=mode=max" in args) == (mode == "--push")
        assert "--pull" not in args and "--allow" not in args
    assert published == (mode == "--push" and statuses[-1] == 0)
    if len(calls) == 2:
        first = list(calls[0])
        first[first.index("--build-arg") + 1] = "BASE_REGISTRY=docker.io/library"
        assert first == calls[1], "only the base registry may change on fallback"


@pytest.mark.parametrize("image,mode", [("backend", "--load"), ("workspace-runtime", "--invalid")])
def test_invalid_arguments_never_build_or_publish(fake_docker, image, mode):
    result, calls, published = fake_docker(image, mode, [0])
    assert result.returncode == 2
    assert calls == [] and not published


def test_attempt_deadline_is_fixed_and_all_workspace_ci_paths_use_helper():
    script = SCRIPT.read_text()
    assert 'timeout --signal=TERM --kill-after=15s "$limit"' in script
    # A fixed deadline per image: the browser image also downloads Chromium.
    assert "limit=3m\n" in script and '[[ "$1" == workspace-browser ]] && limit=10m' in script
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    coding = (ROOT / ".github/workflows/coding-workspace.yml").read_text()
    # Only the images job builds them: three, the ones Deploy Production builds and sends.
    assert ci.count("bash scripts/build_workspace_image.sh") == 3
    assert coding.count("bash scripts/build_workspace_image.sh") == 2
    # One paths list: the isolation runs on main after the merge, not on pull requests.
    assert coding.count("- 'scripts/build_workspace_image.sh'") == 1
    assert coding.count("- 'tests/test_workspace_image_build.py'") == 1
    assert "timeout-minutes: 20" in coding
    assert "BASE_REGISTRY=mirror.gcr.io/library" not in ci + coding
