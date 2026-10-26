"""Verify OCI evidence checks; the CI job additionally performs the real export."""

import base64
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
    build_config = {"llbDefinition": [{"id": "copy"}]}
    source = {
        "infos": [{"filename": "Dockerfile", "data": base64.b64encode(probe.DOCKERFILE).decode()}]
    }
    predicate = {
        "buildType": probe.BUILD_TYPE,
        "buildConfig": build_config,
        "metadata": {probe.BUILD_TYPE + "#metadata": {"source": source}},
    }
    if version == "v1":
        predicate = {
            "buildDefinition": {
                "buildType": probe.BUILD_TYPE_V1,
                "internalParameters": {"buildConfig": build_config},
            },
            "runDetails": {"metadata": {"buildkit_metadata": {"source": source}}},
        }
    statement = {
        "_type": "https://in-toto.io/Statement/" + ("v1" if version == "v1" else "v0.1"),
        "predicateType": "https://slsa.dev/provenance/" + version,
        "subject": [{"digest": {"sha256": image["digest"][7:]}}],
        "predicate": predicate,
    }
    if fault == "wrong_subject":
        statement["subject"][0]["digest"]["sha256"] = "0" * 64
    elif fault == "minimum_mode":
        build_config.clear()
    elif fault == "wrong_source":
        source["infos"] = []
    layer = descriptor(statement, "application/vnd.in-toto+json")
    attestation = descriptor({"schemaVersion": 2, "layers": [layer]})
    attestation["annotations"] = {
        "vnd.docker.reference.type": "attestation-manifest",
        "vnd.docker.reference.digest": image["digest"],
    }
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
def test_nested_oci_export_requires_real_linked_max_mode_evidence(tmp_path, version):
    archive = tmp_path / "probe.tar"
    digest = archive_fixture(archive, version=version)
    result = probe.verify_archive(archive)
    assert result == {
        "verified": True,
        "mode": "max",
        "predicate_type": "https://slsa.dev/provenance/" + version,
        "subject_sha256": digest,
    }


@pytest.mark.parametrize(
    "fault", ["no_attestation", "wrong_subject", "minimum_mode", "wrong_source", "bad_digest"]
)
@pytest.mark.parametrize("version", ["v0.2", "v1"])
def test_missing_or_invalid_provenance_is_a_failed_gate(tmp_path, fault, version):
    archive = tmp_path / "probe.tar"
    archive_fixture(archive, fault=fault, version=version)
    with pytest.raises(ValueError):
        probe.verify_archive(archive)


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
    assert json.loads(capsys.readouterr().out)["verified"] is True


def test_same_builder_and_real_probe_gate_premerge_and_publisher():
    source = (ROOT / ".github/workflows/ci.yml").read_text()
    parts = re.split(r"(?m)^  ([a-z][a-z-]*):\n", source)
    jobs = dict(zip(parts[1::2], parts[2::2], strict=True))
    for name in ("build", "docker", "publish-production"):
        dependencies = re.search(r"needs: \[([^\]]+)\]", jobs[name])
        assert "provenance" in dependencies[1].replace(" ", "").split(",")
    for name in ("provenance", "publish-production"):
        job = jobs[name]
        pin = "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069"
        check = "python3 scripts/verify_build_provenance.py"
        assert "id: buildx" in job and "driver: docker-container" in job
        assert job.index(pin) < job.index(check)
        for step in job.split("      - "):
            if check in step or "scripts/build_workspace_image.sh" in step:
                assert "BUILDX_BUILDER: ${{ steps.buildx.outputs.name }}" in step
        if name == "publish-production":
            assert job.index(check) < job.index("Publish production backend")
            assert job.index(check) < job.index("scripts/build_workspace_image.sh")
    assert "setup-buildx-action" not in jobs["docker"]
