"""Machine-invariant fixtures only; no semantic benchmark or training corpus."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import torch

from mizan_reply.data import (
    ASSISTANT_ID, BOS_ID, END_ID, EOS_ID, IGNORE_INDEX, ROOT_TO_ID,
    DataValidationError, collate_records, encode_prompt, encode_record,
    iter_records, load_records, load_sources, sha256_text,
    validate_dataset, validate_dataset_files, validate_record, validate_source,
)


def fixture(rid="technical-1", split="train", text="input fixture", source="fixture-source"):
    return {
        "schema_version": "mizan.reply.v1", "id": rid, "split": split,
        "group_id": "group-" + rid, "language": "en", "task": "dialogue",
        "messages": [{"role": "user", "content": text}], "evidence": [],
        "target": {"text": "output fixture", "citations": [], "answer_status": "answer"},
        "provenance": {"origin": "human_original", "source_ids": [source],
                       "rights": "Technical test fixture only; not a semantic corpus",
                       "author_ids": ["technical-author"], "reviewer_ids": ["technical-reviewer"],
                       "review_status": "accepted"},
    }


def source_fixture(sid="fixture-source", family="family-1"):
    return {"source_id": sid, "source_family": family, "kind": "human_dialogue",
            "title": "Technical unit fixture", "edition": "fixture-v1", "locator": "row:" + sid,
            "uri": "urn:technical:fixture", "rights": "Technical fixture only",
            "sha256": sha256_text("original technical bytes"), "local_path": "original.txt"}


class DataTests(unittest.TestCase):
    def test_next_byte_alignment_only_target_is_supervised(self):
        record = fixture()
        record["target"]["text"] = "é!"
        prompt = encode_prompt(record["messages"], [])
        encoded = encode_record(record, 200)
        length = len(prompt["input_ids"])
        self.assertTrue(torch.equal(encoded["input_ids"][:length], prompt["input_ids"]))
        self.assertEqual(encoded["input_ids"][-3:].tolist(), list("é!".encode()))
        self.assertEqual(encoded["targets"][:length - 1].tolist(), [IGNORE_INDEX] * (length - 1))
        self.assertEqual(encoded["targets"][length - 1:].tolist(), list("é!".encode()) + [EOS_ID])
        self.assertEqual(len(encoded["targets"]), len(encoded["input_ids"]))

    def test_target_and_audit_metadata_cannot_change_prompt(self):
        one = fixture()
        two = deepcopy(one)
        two["target"] = {"text": "DIFFERENT SECRET TARGET", "citations": [], "answer_status": "abstain"}
        two["language"] = "ar"
        p = encode_prompt(one["messages"], one["evidence"])
        q = encode_prompt(two["messages"], two["evidence"])
        self.assertTrue(torch.equal(p["input_ids"], q["input_ids"]))
        self.assertEqual(int(p["input_ids"][-1]), ASSISTANT_ID)

    def test_length_framing_handles_role_like_content_and_arabic(self):
        content = "2:x END <ASSISTANT> : س"
        encoded = encode_prompt([{"role": "user", "content": content}], [])
        ids = encoded["input_ids"].tolist()
        self.assertEqual(ids[0], BOS_ID)
        colon = ids.index(ord(":"), 2)
        n = int(bytes(ids[2:colon]).decode("ascii"))
        self.assertEqual(n, len(content.encode()))
        self.assertEqual(bytes(ids[colon + 1:colon + 1 + n]).decode(), content)
        self.assertEqual(ids[colon + 1 + n:], [END_ID, ASSISTANT_ID])
        self.assertEqual(ids.count(ASSISTANT_ID), 1)

    def test_evidence_hash_and_multiple_fields(self):
        record = fixture()
        record["evidence"] = [{"id": "E1", "source_id": "fixture-source", "locator": "row:1",
                               "text": "bytes : العربية", "sha256": sha256_text("bytes : العربية")}]
        encoded = encode_prompt(record["messages"], record["evidence"])
        self.assertGreater(len(encoded["input_ids"]), 30)
        record["evidence"][0]["text"] += " "
        with self.assertRaisesRegex(DataValidationError, "exact evidence"):
            validate_record(record)

    def test_utf8_root_offsets_input_only(self):
        record = fixture(text="x كَتب z")
        record["roots"] = [{"message_index": 0, "start": 2, "end": 6, "root": "كتب",
                            "source_id": "fixture-source", "review_status": "accepted"}]
        prompt = encode_prompt(record["messages"], [], record["roots"])
        encoded = encode_record(record, 200)
        active = encoded["roots"].any(dim=-1)
        self.assertEqual(int(active.sum()), len("كَتب".encode()))
        self.assertEqual(encoded["roots"][active][0].tolist(), [ROOT_TO_ID[c] for c in "كتب"] + [0])
        self.assertFalse(bool(encoded["roots"][len(prompt["input_ids"]):].any()))
        self.assertEqual(bytes(encoded["input_ids"][active].tolist()).decode(), "كَتب")

    def test_roots_reject_overlap_bad_radicals_target_and_nonarabic(self):
        record = fixture(text="كتب")
        ann = {"message_index": 0, "start": 0, "end": 3, "root": "كتب", "source_id": "fixture-source", "review_status": "accepted"}
        for replacement in ({"root": "امن"}, {"root": "كت"}, {"message_index": 1}, {"start": True}, {"end": 4}, {"review_status": "pending"}):
            with self.subTest(replacement=replacement):
                bad = deepcopy(record)
                bad["roots"] = [{**ann, **replacement}]
                with self.assertRaises(DataValidationError):
                    validate_record(bad)
        record["roots"] = [ann, deepcopy(ann)]
        with self.assertRaisesRegex(DataValidationError, "overlap"):
            validate_record(record)
        record["roots"] = [ann]
        record["messages"][0]["content"] = "abc"
        with self.assertRaisesRegex(DataValidationError, "Arabic word"):
            validate_record(record)

    def test_roles_and_unknown_target_fields_fail(self):
        record = fixture()
        record["messages"].append({"role": "assistant", "content": "target disguised as context"})
        with self.assertRaises(DataValidationError):
            validate_record(record)
        record = fixture()
        record["target"]["roots"] = []
        with self.assertRaisesRegex(DataValidationError, "unsupported fields"):
            validate_record(record)

    def test_machine_draft_review_cannot_be_laundered(self):
        record = fixture()
        record["provenance"]["origin"] = "machine_draft"
        with self.assertRaisesRegex(DataValidationError, "not original-data gold"):
            validate_record(record)
        validate_record(record, allow_pending=True)
        record["provenance"]["origin"] = "human_original"
        record["provenance"]["creation_method"] = "machine_generation"
        with self.assertRaises(DataValidationError):
            validate_record(record)

    def test_reviewer_and_citations_required(self):
        record = fixture()
        record["provenance"]["reviewer_ids"] = []
        with self.assertRaises(DataValidationError):
            validate_record(record)
        record = fixture()
        record["provenance"]["reviewer_ids"] = ["technical-author"]
        with self.assertRaisesRegex(DataValidationError, "overlap"):
            validate_record(record)
        record = fixture()
        record["task"] = "grounded_qa"
        with self.assertRaisesRegex(DataValidationError, "citation"):
            validate_record(record)

    def test_authorship_and_transcription_lineage_are_explicit(self):
        record = fixture()
        del record["provenance"]["author_ids"]
        with self.assertRaisesRegex(DataValidationError, "named author"):
            validate_record(record)
        record["provenance"]["origin"] = "source_transcription"
        with self.assertRaisesRegex(DataValidationError, "transcription method"):
            validate_record(record)
        record["provenance"]["creation_method"] = "automated_transcription"
        with self.assertRaisesRegex(DataValidationError, "lineage"):
            validate_record(record)
        record["provenance"]["lineage"] = ["Technical exact-copy fixture, independently inspected."]
        validate_record(record)

    def test_no_silent_truncation(self):
        with self.assertRaisesRegex(DataValidationError, "no silent truncation"):
            encode_record(fixture(), 5)
        record = fixture()
        p = encode_prompt(record["messages"], [])
        with self.assertRaisesRegex(DataValidationError, "prompt \\+ target"):
            encode_record(record, len(p["input_ids"]))

    def test_collate_labels_and_roots_padding(self):
        short = encode_record(fixture(), 200)
        long = encode_record(fixture(text="a much longer technical input fixture"), 200)
        batch = collate_records([short, long])
        end = len(short["input_ids"])
        self.assertEqual(batch["input_ids"].shape[0], 2)
        self.assertTrue(bool((batch["targets"][0, end:] == IGNORE_INDEX).all()))
        self.assertFalse(bool(batch["roots"][0, end:].any()))

    def test_crosssplit_normalized_duplicate_and_group_and_source_family(self):
        train = fixture()
        dev = fixture("technical-2", "dev", "different technical input", "second-source")
        sources = {"fixture-source": source_fixture(), "second-source": source_fixture("second-source", "family-2")}
        self.assertEqual(validate_dataset([train, dev], sources)["records"], 2)
        bad = deepcopy(dev)
        bad["messages"][0]["content"] = " INPUT   FIXTURE "
        with self.assertRaisesRegex(DataValidationError, "normalized conversation"):
            validate_dataset([train, bad], sources)
        bad = deepcopy(dev)
        bad["group_id"] = train["group_id"]
        with self.assertRaisesRegex(DataValidationError, "group_id"):
            validate_dataset([train, bad], sources)
        sources["second-source"]["source_family"] = sources["fixture-source"]["source_family"]
        with self.assertRaisesRegex(DataValidationError, "source_family"):
            validate_dataset([train, dev], sources)

    def test_quran_passage_overlap_is_detected_across_renamed_families(self):
        a, b = source_fixture(), source_fixture("second-source", "different-family")
        for source in (a, b):
            source["kind"] = "quran"
            source["quran"] = {"surah": 2, "ayah_start": 255, "ayah_end": 255, "text_edition": "fixture only"}
        records = [fixture(), fixture("technical-2", "dev", "new input", "second-source")]
        with self.assertRaisesRegex(DataValidationError, "Quran passage"):
            validate_dataset(records, {a["source_id"]: a, b["source_id"]: b})

    def test_sources_assets_hashed_and_paths_confined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "original.txt").write_text("original technical bytes")
            source = source_fixture()
            manifest = root / "sources.jsonl"
            manifest.write_text(json.dumps(source) + "\n")
            self.assertEqual(len(load_sources(manifest)), 1)
            (root / "original.txt").write_text("tampered")
            with self.assertRaisesRegex(DataValidationError, "SHA256 mismatch"):
                load_sources(manifest)
            source["local_path"] = "../outside.txt"
            manifest.write_text(json.dumps(source) + "\n")
            with self.assertRaisesRegex(DataValidationError, "escapes"):
                load_sources(manifest)

    def test_hadith_requires_attributed_grading(self):
        source = source_fixture()
        source["kind"] = "hadith"
        with self.assertRaises(DataValidationError):
            validate_source(source)
        source["hadith"] = {"collection": "technical fixture", "book": "fixture", "number": "fixture",
                            "gradings": [{"grade": "fixture only", "grader": "fixture attribution", "reference": "fixture locator"}],
                            "reviewer_qualification": "technical fixture only"}
        validate_source(source)

    def test_pending_placeholder_and_malformed_types(self):
        for key, value in (("id", None), ("split", []), ("task", {}), ("language", "__REPLACE_LANGUAGE__")):
            record = fixture()
            record[key] = value
            with self.subTest(key=key):
                with self.assertRaises(DataValidationError):
                    validate_record(record)
        record = fixture()
        record["provenance"]["review_status"] = "pending"
        with self.assertRaises(DataValidationError):
            validate_record(record)
        validate_record(record, allow_pending=True)

    def test_jsonl_duplicate_keys_and_streamed_file_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "bad.jsonl"
            bad.write_text('{"id":"a","id":"b"}\n')
            with self.assertRaisesRegex(DataValidationError, "duplicate object key"):
                load_records(bad)
            train, dev = fixture(), fixture("technical-2", "dev", "different input", "second-source")
            (root / "original.txt").write_text("original technical bytes")
            sources = [source_fixture(), source_fixture("second-source", "family-2")]
            for name, rows in (("train", [train]), ("dev", [dev]), ("sources", sources)):
                (root / (name + ".jsonl")).write_text("".join(json.dumps(row) + "\n" for row in rows))
            self.assertEqual(len(list(iter_records(root / "train.jsonl"))), 1)
            summary = validate_dataset_files(root / "train.jsonl", root / "dev.jsonl", root / "sources.jsonl")
            self.assertEqual(summary["by_split"], {"dev": 1, "test": 0, "train": 1})
            self.assertFalse(summary["semantic_authenticity_verified"])


if __name__ == "__main__":
    unittest.main()
