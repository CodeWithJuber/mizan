#!/usr/bin/env python3
"""Request max-mode provenance and verify an exported image-linked SLSA attestation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

DOCKERFILE = b"FROM scratch\nCOPY probe.txt /probe.txt\n"
PROVENANCE = "https://slsa.dev/provenance/v0.2"
PROVENANCE_V1 = "https://slsa.dev/provenance/v1"
MAX_BYTES = 16 * 1024 * 1024


def verify_archive(path: Path) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Unexpectedly large provenance probe archive")
    with tarfile.open(path, "r:*") as archive:
        members = archive.getmembers()
        if len(members) > 256:
            raise ValueError("Unexpected provenance probe archive layout")
        entries = {member.name.removeprefix("./"): member for member in members}
        if len(entries) != len(members):
            raise ValueError("Duplicate OCI archive entries")

        def read_json(name: str, descriptor: dict | None = None) -> dict:
            member = entries[name]
            if not member.isfile() or member.size > MAX_BYTES:
                raise ValueError("Invalid OCI JSON entry")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Missing OCI JSON entry")
            with stream:
                raw = stream.read(MAX_BYTES + 1)
            if descriptor and (
                len(raw) != descriptor["size"]
                or "sha256:" + hashlib.sha256(raw).hexdigest() != descriptor["digest"]
            ):
                raise ValueError("OCI descriptor digest or size mismatch")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("OCI JSON object required")
            return value

        def blob(descriptor: dict) -> dict:
            digest = descriptor.get("digest", "")
            if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ValueError("Invalid OCI descriptor digest")
            return read_json("blobs/sha256/" + digest[7:], descriptor)

        images = set()
        attestations = []

        def walk(index: dict, depth: int = 0) -> None:
            if depth > 3:
                raise ValueError("Unexpected OCI index nesting")
            for descriptor in index.get("manifests", []):
                manifest = blob(descriptor)
                if "manifests" in manifest:
                    walk(manifest, depth + 1)
                elif any(
                    layer.get("mediaType") == "application/vnd.in-toto+json"
                    for layer in manifest.get("layers", [])
                ):
                    attestations.append((descriptor, manifest))
                else:
                    images.add(descriptor["digest"])

        walk(read_json("index.json"))
        diagnostics = {
            "images_found": len(images),
            "attestation_manifests": len(attestations),
            "recognized_predicates": 0,
            "valid_statement_objects": 0,
            "matched_targets": 0,
            "matched_subjects": 0,
        }
        for descriptor, manifest in attestations:
            annotations = descriptor.get("annotations", {})
            target = annotations.get("vnd.docker.reference.digest") or manifest.get(
                "subject", {}
            ).get("digest")
            target_matches = isinstance(target, str) and target in images
            diagnostics["matched_targets"] += int(target_matches)
            for layer in manifest.get("layers", []):
                if layer.get("mediaType") != "application/vnd.in-toto+json":
                    continue
                statement = blob(layer)
                predicate = statement.get("predicate", {})
                subjects = statement.get("subject", [])
                predicate_type = statement.get("predicateType")
                recognized = predicate_type in (PROVENANCE, PROVENANCE_V1)
                diagnostics["recognized_predicates"] += int(recognized)
                valid_statement = (
                    statement.get("_type")
                    in {"https://in-toto.io/Statement/v0.1", "https://in-toto.io/Statement/v1"}
                    and isinstance(predicate, dict)
                    and bool(predicate)
                )
                diagnostics["valid_statement_objects"] += int(valid_statement)
                subject_matches = (
                    target_matches
                    and isinstance(subjects, list)
                    and any(
                        isinstance(subject, dict)
                        and isinstance(subject.get("digest"), dict)
                        and subject["digest"].get("sha256") == target[7:]
                        for subject in subjects
                    )
                )
                diagnostics["matched_subjects"] += int(subject_matches)
                if recognized and valid_statement and subject_matches:
                    return {
                        "verified": True,
                        "predicate_type": predicate_type,
                        "subject_sha256": target[7:],
                    }
    raise ValueError(
        "OCI export lacks image-linked SLSA provenance; " + json.dumps(diagnostics, sort_keys=True)
    )


def main() -> None:
    inspected = subprocess.run(
        [
            "timeout",
            "--kill-after=5s",
            "30s",
            "docker",
            "buildx",
            "inspect",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    driver = re.search(r"(?m)^Driver:\s+(\S+)\s*$", inspected)
    if driver is None or driver[1] != "docker-container":
        raise SystemExit("Provenance preflight requires the configured docker-container builder")
    with tempfile.TemporaryDirectory(prefix="mizan-provenance-") as temporary:
        root = Path(temporary)
        context = root / "context"
        context.mkdir()
        (context / "Dockerfile").write_bytes(DOCKERFILE)
        (context / "probe.txt").write_text("Mizan CI provenance export probe\n")
        output = root / "probe.oci.tar"
        subprocess.run(
            [
                "timeout",
                "--signal=TERM",
                "--kill-after=15s",
                "2m",
                "docker",
                "buildx",
                "build",
                "--progress=plain",
                "--provenance=mode=max",
                "--output",
                f"type=oci,dest={output}",
                str(context),
            ],
            check=True,
            cwd=context,
        )
        print(json.dumps(verify_archive(output) | {"requested_mode": "max"}, sort_keys=True))


if __name__ == "__main__":
    main()
