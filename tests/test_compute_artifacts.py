import hashlib
import io
import json
import os
import urllib.error
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts.upload_ci_artifact import (
    ARTIFACTS,
    ORIGIN,
    pack,
    restricted_pull_request,
    retry_delay,
    upload,
    verify_receipt,
)


class ComputeArtifactTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = {
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_REPOSITORY": "CodeWithJuber/mizan",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.example.invalid/get?foo=bar",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "synthetic",
        }
        self.archive = self.root / "artifact.zip"
        self.archive.write_bytes(b"synthetic ZIP")

    def receipt(self):
        return {
            "repository": "CodeWithJuber/mizan",
            "repository_id": "1166364542",
            "run_id": "123",
            "run_attempt": "2",
            "family": "dist",
            "slot": "python-package",
            "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "size_bytes": self.archive.stat().st_size,
            "path": "1166364542/123/2/dist/python-package/artifact.zip",
            "retained_until": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        }

    def test_package_structure_excludes_hidden_files_and_external_symlinks(self):
        source = self.root / "source"
        (source / "playwright-report").mkdir(parents=True)
        (source / "test-results").mkdir()
        (source / "playwright-report/index.html").write_text("report")
        (source / "test-results/error.txt").write_text("error")
        (source / ".env").write_text("private")
        (source / "playwright-report/link").symlink_to(self.root)
        outside = self.root / "outside"
        outside.write_text("private")
        (source / "test-results/link").symlink_to(outside)
        count = pack(self.archive, source, [".", "test-results"], 1024)
        self.assertEqual(count, 2)
        with zipfile.ZipFile(self.archive) as bundle:
            self.assertEqual(
                sorted(bundle.namelist()),
                ["playwright-report/index.html", "test-results/error.txt"],
            )
        with self.assertRaises(ValueError):
            pack(self.archive, source, ["../outside"], 1024)
        with self.assertRaises(ValueError):
            pack(self.archive, source, ["."], 1)

    def test_retry_uploads_identical_bytes_and_checks_server_receipt(self):
        expected = self.archive.read_bytes()
        requests = []
        record = self.receipt()

        class Opener:
            def open(inner, request, timeout):
                if request.get_method() != "PUT":
                    self.assertIn("audience=", request.full_url)
                    return io.BytesIO(b'{"value":"synthetic-oidc"}')
                self.assertEqual(request.full_url, ORIGIN + "/v1/artifacts/dist/python-package")
                self.assertEqual(request.data.read(), expected)
                requests.append(request)
                if len(requests) == 1:
                    raise urllib.error.HTTPError(
                        request.full_url, 503, "retry", {"Retry-After": "30"}, None
                    )
                return io.BytesIO(json.dumps(record).encode())

        with (
            patch.dict(os.environ, self.env),
            patch("scripts.upload_ci_artifact.time.sleep") as sleep,
        ):
            result = upload(self.archive, "dist", Opener())
            self.assertEqual(result[0], record["path"])
            self.assertEqual(len(requests), 2)
            sleep.assert_called_once_with(30)
            with self.assertRaises(ValueError):
                verify_receipt(
                    dict(record, run_attempt="1"),
                    "dist",
                    "python-package",
                    record["sha256"],
                    len(expected),
                )

    def test_receipts_accept_only_exact_receiver_namespace_for_every_family(self):
        with patch.dict(os.environ, self.env):
            for family, (slot, _) in ARTIFACTS.items():
                record = dict(
                    self.receipt(),
                    family=family,
                    slot=slot,
                    path=f"1166364542/123/2/{family}/{slot}/artifact.zip",
                )
                with self.subTest(family=family):
                    self.assertEqual(
                        verify_receipt(
                            record, family, slot, record["sha256"], record["size_bytes"]
                        ),
                        record["path"],
                    )
                    for path in (
                        "/srv/github-actions-direct/" + record["path"],
                        record["path"].replace("/123/", "/124/"),
                        record["path"].replace("/2/", "/1/"),
                        record["path"].replace(f"/{slot}/", "/other/"),
                        record["path"].replace("artifact.zip", "artifact.tar.gz"),
                        record["path"].replace("artifact.zip", "../artifact.zip"),
                        "https://example.invalid/" + record["path"],
                    ):
                        with self.subTest(path=path), self.assertRaises(ValueError):
                            verify_receipt(
                                dict(record, path=path),
                                family,
                                slot,
                                record["sha256"],
                                record["size_bytes"],
                            )

    def test_receipts_reject_identity_digest_size_and_invalid_expiry(self):
        record = self.receipt()
        changes = {
            "repository": ["other/mizan"],
            "repository_id": ["1166364543", 1166364542],
            "run_id": ["124", 123],
            "run_attempt": ["1", 2],
            "family": ["playwright-report"],
            "slot": ["other"],
            "sha256": ["0" * 64],
            "size_bytes": [record["size_bytes"] + 1, float(record["size_bytes"])],
            "retained_until": [None, 1, "invalid", "2000-01-01T00:00:00Z", "2099-01-01"],
        }
        with patch.dict(os.environ, self.env):
            for key, values in changes.items():
                for value in values:
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        verify_receipt(
                            dict(record, **{key: value}),
                            "dist",
                            "python-package",
                            record["sha256"],
                            record["size_bytes"],
                        )

    def test_retry_after_is_bounded_and_malformed_values_use_backoff(self):
        for raw, expected in [("30", 30), ("300", 60), ("0", 2), ("garbage", 2)]:
            with self.subTest(value=raw):
                error = urllib.error.HTTPError(ORIGIN, 503, "retry", {"Retry-After": raw}, None)
                self.assertEqual(retry_delay(error, 2), expected)

    def test_only_fork_or_dependabot_events_qualify_for_missing_identity_notice(self):
        event = self.root / "event.json"
        event.write_text(
            json.dumps({"pull_request": {"head": {"repo": {"full_name": "fork/mizan"}}}})
        )
        values = {
            **self.env,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_ACTOR": "contributor",
        }
        with patch.dict(os.environ, values):
            self.assertTrue(restricted_pull_request())
            event.write_text(
                json.dumps(
                    {"pull_request": {"head": {"repo": {"full_name": "CodeWithJuber/mizan"}}}}
                )
            )
            self.assertFalse(restricted_pull_request())
            os.environ["GITHUB_ACTOR"] = "dependabot[bot]"
            self.assertTrue(restricted_pull_request())
