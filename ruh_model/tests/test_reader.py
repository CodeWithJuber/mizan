"""Tests for the RootSpace Reader backend (use case #5).

Torch-free: ``ruh_model/__init__.py`` needs torch (absent in CI), so the
modules under test are loaded directly by file path instead of via
package imports. Run with ``--noconftest`` to skip the pre-existing
``ruh_model/tests/conftest.py``, which imports ``ruh_model.config``
(and thereby torch).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_KEYS = {
    "word_index",
    "surface",
    "root",
    "pattern",
    "sense_id",
    "sense_pending",
    "confidence",
}


def _load(relpath: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def annotator() -> ModuleType:
    return _load("ruh_model/reader/annotator.py", "test_reader_annotator")


@pytest.fixture(scope="module")
def store_mod() -> ModuleType:
    return _load("ruh_model/reader/store.py", "test_reader_store")


class TestAnnotateText:
    def test_schema_keys(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("العلم نور")
        assert len(out) == 2
        for entry in out:
            assert set(entry.keys()) == EXPECTED_KEYS

    def test_word_index_sequential(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("قال رسول الله")
        assert [e["word_index"] for e in out] == [0, 1, 2]

    def test_empty_text(self, annotator: ModuleType) -> None:
        assert annotator.annotate_text("") == []
        assert annotator.annotate_text("   ") == []

    def test_surface_preserved(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("الرحمن الرحيم")
        assert [e["surface"] for e in out] == ["الرحمن", "الرحيم"]

    def test_stopword(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("من الله")
        stop = out[0]
        assert stop["pattern"] == "STOPWORD"
        assert stop["root"] == ""
        assert stop["sense_id"] is None
        assert stop["sense_pending"] is False
        assert stop["confidence"] == pytest.approx(0.95)

    def test_non_arabic(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("hello")
        assert out[0]["pattern"] == "NON_ARABIC"
        assert out[0]["root"] == ""
        assert out[0]["sense_pending"] is True

    def test_diacritics_handled(self, annotator: ModuleType) -> None:
        # Fully vowelled Quranic spelling must not break analysis.
        out = annotator.annotate_text("ٱلرَّحْمَـٰنِ")
        assert out[0]["root"] != "" or out[0]["pattern"] == "UNKNOWN"

    def test_ref_id_ignored_but_accepted(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("نور", ref_id="24:35")
        assert out[0]["word_index"] == 0


class TestSenseHook:
    """The sense hook must never fabricate a sense (amana)."""

    def test_no_inventory_means_pending(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("الرحمن")
        assert out[0]["sense_id"] is None
        assert out[0]["sense_pending"] is True

    def test_single_sense_inventory_assigns(self, annotator: ModuleType) -> None:
        inventory = {"رحم": [{"sense_id": "qcsmp:mercy", "gloss_en": "mercy"}]}
        out = annotator.annotate_text("الرحمن", sense_inventory=inventory)
        assert out[0]["sense_id"] == "qcsmp:mercy"
        assert out[0]["sense_pending"] is False

    def test_ambiguous_inventory_stays_pending(self, annotator: ModuleType) -> None:
        inventory = {
            "رحم": [{"sense_id": "s1"}, {"sense_id": "s2"}],
        }
        out = annotator.annotate_text("الرحمن", sense_inventory=inventory)
        # NEVER pick one of several candidates -- that would be a guess.
        assert out[0]["sense_id"] is None
        assert out[0]["sense_pending"] is True

    def test_lookup_callable(self, annotator: ModuleType) -> None:
        out = annotator.annotate_text("الرحمن", sense_lookup=lambda root, surface: ["only-sense"])
        assert out[0]["sense_id"] == "only-sense"
        assert out[0]["sense_pending"] is False

    def test_broken_lookup_does_not_corrupt(self, annotator: ModuleType) -> None:
        def bad_lookup(root: str, surface: str) -> list[str]:
            raise RuntimeError("inventory exploded")

        out = annotator.annotate_text("الرحمن", sense_lookup=bad_lookup)
        assert out[0]["sense_id"] is None
        assert out[0]["sense_pending"] is True


class TestAnnotationStore:
    def test_round_trip(self, annotator: ModuleType, store_mod: ModuleType, tmp_path: Path) -> None:
        annotations = annotator.annotate_text("العلم نور")
        db = tmp_path / "a.sqlite"
        with store_mod.AnnotationStore(db) as store:
            n = store.put_many("1:1", annotations)
            assert n == 2
            got = store.get("1:1", 0)
            assert got is not None
            assert got["surface"] == "العلم"
            assert got["word_index"] == 0
            assert set(got.keys()) == EXPECTED_KEYS | {"ref_id"}

    def test_get_missing_returns_none(self, store_mod: ModuleType, tmp_path: Path) -> None:
        with store_mod.AnnotationStore(tmp_path / "b.sqlite") as store:
            assert store.get("9:9", 0) is None
            assert store.get_all("9:9") == []

    def test_get_all_ordered(
        self, annotator: ModuleType, store_mod: ModuleType, tmp_path: Path
    ) -> None:
        annotations = annotator.annotate_text("قال رسول الله")
        with store_mod.AnnotationStore(tmp_path / "c.sqlite") as store:
            # insert out of order; reads must come back ordered
            store.put("2:3", annotations[2])
            store.put("2:3", annotations[0])
            store.put("2:3", annotations[1])
            all_rows = store.get_all("2:3")
            assert [r["word_index"] for r in all_rows] == [0, 1, 2]

    def test_refs_and_stats(
        self, annotator: ModuleType, store_mod: ModuleType, tmp_path: Path
    ) -> None:
        with store_mod.AnnotationStore(tmp_path / "d.sqlite") as store:
            store.put_many("1:1", annotator.annotate_text("نور"))
            store.put_many("1:2", annotator.annotate_text("هدى للناس"))
            assert store.refs() == ["1:1", "1:2"]
            stats = store.stats()
            assert stats["n_refs"] == 2
            assert stats["n_words"] == 3
            assert stats["schema_version"] == 1
            assert isinstance(stats["db_bytes"], int) and stats["db_bytes"] > 0
            assert "scholar-eval pending" in stats["beta_note"]

    def test_requires_open(self, store_mod: ModuleType, tmp_path: Path) -> None:
        store = store_mod.AnnotationStore(tmp_path / "e.sqlite")
        with pytest.raises(RuntimeError):
            store.get("1:1", 0)


class TestDbSize:
    """KB-scale check: measure, don't assume (report numbers, not claims)."""

    SAMPLE_WORDS = (
        "بسم الله الرحمن الرحيم الحمد لله رب العالمين الرحمن الرحيم مالك يوم الدين "
        "إياك نعبد وإياك نستعين اهدنا الصراط المستقيم صراط الذين أنعمت عليهم "
        "غير المغضوب عليهم ولا الضالين"
    ).split()

    def test_measured_size_is_kb_scale(
        self, annotator: ModuleType, store_mod: ModuleType, tmp_path: Path
    ) -> None:
        repetitions = 12  # ~600 words
        words = self.SAMPLE_WORDS * repetitions
        text = " ".join(words)
        annotations = annotator.annotate_text(text)
        assert len(annotations) == len(words)

        db = tmp_path / "size.sqlite"
        with store_mod.AnnotationStore(db) as store:
            store.put_many("1:1", annotations)
            stats = store.stats()

        db_bytes = stats["db_bytes"]
        assert isinstance(db_bytes, int)
        per_word = db_bytes / len(words)
        # Sanity bounds for the report -- the measured values are what
        # matter, not these thresholds.
        assert db_bytes < 512 * 1024, f"unexpectedly large: {db_bytes} bytes"
        assert per_word < 1024, f"unexpectedly large per-word: {per_word}"
        print(f"\n[measured] words={len(words)} db_bytes={db_bytes} per_word={per_word:.1f}B")

    def test_jsonl_output_shape(self, annotator: ModuleType, tmp_path: Path) -> None:
        annotations = annotator.annotate_text("العلم نور", ref_id="1:1")
        path = tmp_path / "a.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for annotation in annotations:
                fh.write(json.dumps({"ref_id": "1:1", **annotation}, ensure_ascii=False) + "\n")
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["ref_id"] == "1:1"
        assert set(first.keys()) == EXPECTED_KEYS | {"ref_id"}
