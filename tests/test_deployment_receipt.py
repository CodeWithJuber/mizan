import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.deployment_receipt import receipt


class DeploymentReceiptTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.identity = ("101", "202", "2")
        self.path = self.root / "101/202-2.json"
        self.sha = "a" * 40

    def test_parallel_writes_are_idempotent_and_keep_the_first_sha(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(receipt, self.root, "write", *self.identity, self.sha) for _ in range(4)
            ]
            for future in futures:
                future.result()
        with self.assertRaises(ValueError):
            receipt(self.root, "write", *self.identity, "b" * 40)
        self.assertEqual(receipt(self.root, "read", *self.identity), self.sha)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertIsNone(receipt(self.root, "read", "101", "202", "1"))

    def test_rejects_tampering_and_cross_attempt_replay(self):
        receipt(self.root, "write", *self.identity, self.sha)
        record = json.loads(self.path.read_text())
        (self.path.parent / "202-1.json").write_text(self.path.read_text())
        with self.assertRaises(ValueError):
            receipt(self.root, "read", "101", "202", "1")
        record["payload"] = record["payload"].replace(self.sha, "b" * 40)
        self.path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            receipt(self.root, "read", *self.identity)
        with self.assertRaises(ValueError):
            receipt(self.root, "read", "101", "../202", "1")

    def test_expired_receipts_are_ignored_and_pruned_on_next_deployment(self):
        receipt(self.root, "write", *self.identity, self.sha)
        os.utime(self.path, (1, 1))
        self.assertIsNone(receipt(self.root, "read", *self.identity))
        receipt(self.root, "write", "101", "203", "1", self.sha)
        self.assertFalse(self.path.exists())


class ArchivedDeploymentReceiptTests(TestCase):
    def setUp(self):
        from datetime import datetime

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = "100"
        self.started = "2026-11-17T11:00:00Z"
        self.now = datetime(2026, 11, 17, 12, tzinfo=UTC)
        self.sha = "b" * 40

    def write_archive(self, created="2026-11-17T11:01:00Z", expires="2026-12-01T00:00:00Z"):
        import hashlib
        import zipfile

        folder = self.root / self.run / "200"
        folder.mkdir(parents=True)
        archive = folder / "artifact.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("deployed-sha.txt", self.sha + "\n")
        record = {
            "name": "production-deployment",
            "id": 200,
            "workflow_run": {"id": int(self.run)},
            "created_at": created,
            "expires_at": expires,
            "size_in_bytes": archive.stat().st_size,
            "digest": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
        }
        (folder / "metadata.json").write_text(json.dumps(record))
        return archive

    def test_reads_historical_proof_and_rejects_modified_archive(self):
        from scripts.deployment_receipt import archived_receipt

        archive = self.write_archive()
        self.assertEqual(archived_receipt(self.root, self.run, self.started, self.now), self.sha)
        data = archive.read_bytes()
        archive.write_bytes(data.replace(b"b" * 40, b"c" * 40))
        with self.assertRaises(ValueError):
            archived_receipt(self.root, self.run, self.started, self.now)

    def test_earlier_attempt_and_expired_proof_do_not_authorize_release(self):
        from scripts.deployment_receipt import archived_receipt

        self.write_archive(created="2026-11-17T10:00:00Z")
        self.assertIsNone(archived_receipt(self.root, self.run, self.started, self.now))
        self.assertIsNone(
            archived_receipt(
                self.root, self.run, "2026-11-17T09:00:00Z", self.now.replace(month=12)
            )
        )
