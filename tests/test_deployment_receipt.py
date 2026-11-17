import json
import os
from concurrent.futures import ThreadPoolExecutor
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
