"""Verify OCI evidence checks; the CI job additionally performs the real export."""

import hashlib
import importlib.util
import io
import json
import re
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_provenance", ROOT / "scripts/verify_build_provenance.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def archive_fixture(path, *, fault=None, version="v0.2"):
    files = {}

    def descriptor(value, media="application/vnd.oci.image.manifest.v1+json"):
        raw = json.dumps(value).encode()
        digest = hashlib.sha256(raw).hexdigest()
        files["blobs/sha256/" + digest] = raw
        return {"digest": "sha256:" + digest, "size": len(raw), "mediaType": media}

    image = descriptor({"schemaVersion": 2, "layers": []})
    predicate = {
        "buildType": "fixture-build-type",
        "invocation": {},
        "metadata": {"private_fixture_detail": "never print raw provenance"},
    }
    if version == "v1":
        predicate = {
            "buildDefinition": {
                "buildType": "fixture-build-type",
                "externalParameters": {},
            },
            "runDetails": {"metadata": {"private_fixture_detail": "never print raw provenance"}},
        }
    statement = {
        "_type": "https://in-toto.io/Statement/" + ("v1" if version == "v1" else "v0.1"),
        "predicateType": "https://slsa.dev/provenance/" + version,
        "subject": [{"digest": {"sha256": image["digest"][7:]}}],
        "predicate": predicate,
    }
    if fault == "wrong_subject":
        statement["subject"][0]["digest"]["sha256"] = "0" * 64
    elif fault == "wrong_predicate":
        statement["predicateType"] = "https://example.invalid/not-provenance"
    elif fault == "malformed_predicate":
        statement["predicate"] = []
    layer = descriptor(statement, "application/vnd.in-toto+json")
    attestation = descriptor({"schemaVersion": 2, "layers": [layer]})
    attestation["annotations"] = {
        "vnd.docker.reference.type": "attestation-manifest",
        "vnd.docker.reference.digest": image["digest"],
    }
    if fault == "wrong_target":
        attestation["annotations"]["vnd.docker.reference.digest"] = "sha256:" + "0" * 64
    manifests = [image] if fault == "no_attestation" else [image, attestation]
    inner = descriptor(
        {"schemaVersion": 2, "manifests": manifests}, "application/vnd.oci.image.index.v1+json"
    )
    files["index.json"] = json.dumps({"schemaVersion": 2, "manifests": [inner]}).encode()
    if fault == "bad_digest":
        files["blobs/sha256/" + layer["digest"][7:]] += b" "
    with tarfile.open(path, "w") as output:
        for name, raw in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(raw)
            output.addfile(entry, io.BytesIO(raw))
    return image["digest"][7:]


@pytest.mark.parametrize("version", ["v0.2", "v1"])
def test_nested_oci_export_checks_linked_provenance_without_richness_assumptions(tmp_path, version):
    archive = tmp_path / "probe.tar"
    digest = archive_fixture(archive, version=version)
    result = probe.verify_archive(archive)
    assert result == {
        "verified": True,
        "predicate_type": "https://slsa.dev/provenance/" + version,
        "subject_sha256": digest,
    }


@pytest.mark.parametrize(
    "fault",
    [
        "no_attestation",
        "wrong_subject",
        "wrong_target",
        "wrong_predicate",
        "malformed_predicate",
        "bad_digest",
    ],
)
@pytest.mark.parametrize("version", ["v0.2", "v1"])
def test_missing_or_invalid_provenance_is_a_failed_gate(tmp_path, fault, version):
    archive = tmp_path / "probe.tar"
    archive_fixture(archive, fault=fault, version=version)
    with pytest.raises(ValueError):
        probe.verify_archive(archive)


def test_failure_summary_exposes_counts_without_raw_metadata(tmp_path):
    archive = tmp_path / "probe.tar"
    archive_fixture(archive, fault="wrong_subject", version="v1")
    with pytest.raises(ValueError) as error:
        probe.verify_archive(archive)
    message = str(error.value)
    counts = json.loads(message.partition("; ")[2])
    assert counts == {
        "images_found": 1,
        "attestation_manifests": 1,
        "recognized_predicates": 1,
        "valid_statement_objects": 1,
        "matched_targets": 1,
        "matched_subjects": 0,
    }
    assert "private_fixture_detail" not in message
    assert "never print raw provenance" not in message


def test_incompatible_driver_fails_before_build_or_push(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="Name: default\nDriver: docker\nNodes:\n")

    monkeypatch.setattr(probe.subprocess, "run", run)
    with pytest.raises(SystemExit, match="docker-container"):
        probe.main()
    assert len(calls) == 1
    assert calls[0][-3:] == ["docker", "buildx", "inspect"]


def test_probe_checks_exported_archive_without_publishing(monkeypatch, capsys):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[-1] == "inspect":
            return SimpleNamespace(stdout="Name: fixture\nDriver: docker-container\nNodes:\n")
        assert "--provenance=mode=max" in args
        assert "--push" not in args and "--load" not in args
        assert args[args.index("--tag") + 1] == "mizan-provenance-probe:ci"
        output = args[args.index("--output") + 1]
        assert output.startswith("type=oci,dest=")
        context = Path(args[-1])
        assert sorted(path.name for path in context.iterdir()) == ["Dockerfile", "probe.txt"]
        assert (context / "Dockerfile").read_bytes() == probe.DOCKERFILE
        archive_fixture(Path(output.removeprefix("type=oci,dest=")))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(probe.subprocess, "run", run)
    probe.main()
    assert len(calls) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["verified"] is True
    assert receipt["requested_mode"] == "max"
    assert "mode" not in receipt


def test_the_real_probe_gates_premerge_and_the_production_images():
    source = (ROOT / ".github/workflows/ci.yml").read_text()
    parts = re.split(r"(?m)^  ([a-z][a-z-]*):\n", source)
    jobs = dict(zip(parts[1::2], parts[2::2], strict=True))
    dependencies = re.search(r"needs: \[([^\]]+)\]", jobs["production-images"])
    assert "provenance" in dependencies[1].replace(" ", "").split(",")
    job = jobs["provenance"]
    pin = "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069"
    check = "python3 scripts/verify_build_provenance.py"
    assert "id: buildx" in job and "driver: docker-container" in job
    assert job.index(pin) < job.index(check)
    for step in job.split("      - "):
        if check in step:
            assert "BUILDX_BUILDER: ${{ steps.buildx.outputs.name }}" in step
    # The production images stay in the runner's own Docker: Deploy Production sends them to
    # the server over SSH. Nothing logs in to or pushes to a registry (docs/deployment.md).
    images = jobs["production-images"]
    assert images.count("--load") == 3 and images.count("docker build -f docker/") == 2
    for job in jobs.values():
        assert "--push" not in job and "login-action" not in job and "build-push-action" not in job
    assert "setup-buildx-action" not in images
