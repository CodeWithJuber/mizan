"""Tests for ruh_model.sense (torch-free, deterministic).

Dual-mode import: normal package import when torch is installed, file-path
loading otherwise (``ruh_model/__init__.py`` imports torch, which minimal
``[dev, nlp]`` installs don't have). This file never touches torch.

Covers: inventory build determinism + merge handling, JSONL roundtrip,
provenance receipt shape (no invented signals), disambiguation scoring,
conservative abstention (incl. the JEV-tiered 0.6/0.8 bars), and the عين
fixture.
"""

import json
import sys
from pathlib import Path

import pytest

SENSE_DIR = Path(__file__).resolve().parent.parent / "sense"


def _load_sense_modules():
    try:
        import importlib.util

        # import_module (not `from ... import`) — the package __init__
        # re-exports a `disambiguate` *function* that would shadow the submodule.
        dis_mod = importlib.import_module("ruh_model.sense.disambiguate")
        inv_mod = importlib.import_module("ruh_model.sense.inventory")
        prov_mod = importlib.import_module("ruh_model.sense.provenance")
        return inv_mod, prov_mod, dis_mod
    except ImportError:
        # Torch-less env: ruh_model/__init__ needs torch — load by file path.
        mods = {}
        for name in ("inventory", "provenance", "disambiguate"):
            key = f"test_sense_{name}"
            spec = importlib.util.spec_from_file_location(key, SENSE_DIR / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            spec.loader.exec_module(module)
            mods[name] = module
        return mods["inventory"], mods["provenance"], mods["disambiguate"]


inv_mod, prov_mod, dis_mod = _load_sense_modules()


def _ayn_inventory():
    """Fixture: عين with three senses carrying reviewed Arabic glosses."""
    entries = [
        inv_mod.SenseEntry(
            sense_id="test:ayn:eye",
            lemma="عين",
            gloss_en="eye",
            gloss_ar="البصر الرؤية",
            religious=False,
        ),
        inv_mod.SenseEntry(
            sense_id="test:ayn:spring",
            lemma="عين",
            gloss_en="spring",
            gloss_ar="الماء النبع",
            religious=False,
        ),
        inv_mod.SenseEntry(
            sense_id="test:ayn:spy",
            lemma="عين",
            gloss_en="spy",
            gloss_ar="الجاسوس الرقيب",
            religious=False,
        ),
    ]
    return inv_mod.SenseInventory(entries=entries)


# ── merge handling ──────────────────────────────────────────────────────


class TestNormalizeSenseId:
    def test_passthrough_unknown(self):
        assert inv_mod.normalize_sense_id("q:x:y", {}) == "q:x:y"

    def test_single_merge(self):
        merges = {"q:a:old": "q:a:new"}
        assert inv_mod.normalize_sense_id("q:a:old", merges) == "q:a:new"

    def test_transitive_merge(self):
        merges = {"q:a:v1": "q:a:v2", "q:a:v2": "q:a:v3"}
        assert inv_mod.normalize_sense_id("q:a:v1", merges) == "q:a:v3"

    def test_cycle_raises(self):
        merges = {"q:a:1": "q:a:2", "q:a:2": "q:a:1"}
        with pytest.raises(ValueError, match="cycle"):
            inv_mod.normalize_sense_id("q:a:1", merges)


class TestBuildInventory:
    def _seed(self):
        return [
            {"lemma": "آية", "sense": "verse"},
            {"lemma": "آية", "sense": "sign"},
            {"lemma": "أجر", "sense": "reward"},
        ]

    def test_deterministic(self, tmp_path):
        merges = {"qcsmp2:أجر:payment": "qcsmp2:أجر:reward"}
        first = inv_mod.build_inventory(self._seed(), merges)
        second = inv_mod.build_inventory(self._seed(), merges)
        p1 = inv_mod.dump_inventory_jsonl(first, tmp_path / "a.jsonl")
        p2 = inv_mod.dump_inventory_jsonl(second, tmp_path / "b.jsonl")
        assert p1.read_bytes() == p2.read_bytes()

    def test_sorted_by_sense_id(self):
        inventory = inv_mod.build_inventory(self._seed(), {})
        ids = [e.sense_id for e in inventory.entries]
        assert ids == sorted(ids)

    def test_merge_target_must_exist(self):
        with pytest.raises(ValueError, match="absent from the seeded inventory"):
            inv_mod.build_inventory(self._seed(), {"qcsmp2:x:old": "qcsmp2:x:ghost"})

    def test_version_stamped(self):
        inventory = inv_mod.build_inventory(self._seed(), {}, version="9.9.9")
        assert inventory.version == "9.9.9"
        assert all(e.version == "9.9.9" for e in inventory.entries)

    def test_diacritic_insensitive_lookup(self):
        inventory = inv_mod.build_inventory(self._seed(), {})
        assert len(inventory.senses_for("آية")) == 2
        assert len(inventory.senses_for("آيَة")) == 2  # diacritized query works


class TestJsonlRoundtrip:
    def test_roundtrip(self, tmp_path):
        inventory = inv_mod.build_inventory(
            [{"lemma": "آية", "sense": "verse", "gloss_ar": "الآية الكريمة"}],
            {},
        )
        path = inv_mod.dump_inventory_jsonl(inventory, tmp_path / "inv.jsonl")
        loaded = inv_mod.load_inventory_jsonl(path)
        assert loaded.version == inventory.version
        assert len(loaded) == len(inventory)
        entry = loaded.get("qcsmp2:آية:verse")
        assert entry is not None
        assert entry.gloss_ar == "الآية الكريمة"
        assert entry.gloss_ar_status == "pending_scholar_review"

    def test_mixed_versions_rejected(self, tmp_path):
        path = tmp_path / "mixed.jsonl"
        path.write_text(
            '{"sense_id": "q:a:1", "lemma": "a", "gloss_en": "one", "version": "1.0.0"}\n'
            '{"sense_id": "q:a:2", "lemma": "a", "gloss_en": "two", "version": "2.0.0"}\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="mixed inventory versions"):
            inv_mod.load_inventory_jsonl(path)

    def test_missing_key_rejected(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"sense_id": "q:a:1", "lemma": "a"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="missing required key"):
            inv_mod.load_inventory_jsonl(path)

    def test_built_data_file_loads(self):
        # The committed output of scripts/build_sense_inventory.py.
        path = SENSE_DIR / "data" / "sense_inventory.v1.0.0.jsonl"
        assert path.exists(), "run scripts/build_sense_inventory.py first"
        inventory = inv_mod.load_inventory_jsonl(path)
        assert inventory.version == "1.0.0"
        assert len(inventory) == 96
        assert len(inventory.lemmas()) == 48
        assert all(e.religious for e in inventory.entries)
        assert all(e.gloss_ar is None for e in inventory.entries)  # never invented
        assert all(e.root is None for e in inventory.entries)  # never guessed


# ── provenance ──────────────────────────────────────────────────────────


class TestProvenance:
    def test_receipt_shape(self):
        receipt = prov_mod.build_receipt(
            [
                prov_mod.ProvenanceSignal(
                    signal="inventory", source="sense-inventory/v1.0.0", weight=1.0
                ),
                prov_mod.ProvenanceSignal(
                    signal="context_overlap",
                    source="ruh_model.sense.disambiguate:context_overlap/v1",
                    weight=0.83,
                ),
            ]
        )
        assert receipt == [
            {"signal": "inventory", "source": "sense-inventory/v1.0.0", "weight": 1.0},
            {
                "signal": "context_overlap",
                "source": "ruh_model.sense.disambiguate:context_overlap/v1",
                "weight": 0.83,
            },
        ]

    def test_empty_receipt_valid(self):
        assert prov_mod.build_receipt([]) == []

    def test_unknown_signal_rejected(self):
        with pytest.raises(ValueError, match="unknown provenance signal"):
            prov_mod.ProvenanceSignal(signal="vibes", source="x/1", weight=0.5)

    def test_weight_bounds(self):
        with pytest.raises(ValueError, match="weight must be in"):
            prov_mod.ProvenanceSignal(signal="model", source="m/1", weight=1.5)

    def test_empty_source_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            prov_mod.ProvenanceSignal(signal="model", source="  ", weight=0.5)

    def test_all_known_signals_accepted(self):
        for signal in ("inventory", "qcsmp_label", "lexicon", "context_overlap", "model"):
            s = prov_mod.ProvenanceSignal(signal=signal, source="s/1", weight=0.5)
            assert s.signal == signal


# ── disambiguation ──────────────────────────────────────────────────────


class TestDisambiguateAyn:
    @pytest.mark.parametrize(
        ("context", "want"),
        [
            ("شربت من العين ماء عذبا", "test:ayn:spring"),
            ("فتح بصره ونظر الى الافق", "test:ayn:eye"),
            ("ارسل الملك جاسوسا يراقب العدو", "test:ayn:spy"),
        ],
    )
    def test_context_selects_sense(self, context, want):
        result = dis_mod.disambiguate("عين", context, _ayn_inventory())
        assert result.status == "ok"
        assert result.sense_id == want
        assert result.abstained is False
        assert result.inventory_version == inv_mod.INVENTORY_VERSION

    def test_diacritized_word_matches(self):
        result = dis_mod.disambiguate("عَيْن", "شربت من العين ماء عذبا", _ayn_inventory())
        assert result.sense_id == "test:ayn:spring"

    def test_deterministic(self):
        inventory = _ayn_inventory()
        first = dis_mod.disambiguate("عين", "شربت من العين ماء عذبا", inventory)
        second = dis_mod.disambiguate("عين", "شربت من العين ماء عذبا", inventory)
        assert first.to_dict() == second.to_dict()

    def test_to_dict_json_serializable(self):
        result = dis_mod.disambiguate("عين", "شربت من العين ماء عذبا", _ayn_inventory())
        json.dumps(result.to_dict(), ensure_ascii=False)


class TestAbstention:
    def test_zero_evidence_abstains(self):
        result = dis_mod.disambiguate("عين", "قال الرجل كلاما طويلا", _ayn_inventory())
        assert result.status == "uncertain"
        assert result.sense_id is None
        assert result.abstained is True
        assert len(result.alternatives) == 3  # candidates still shown

    def test_unknown_lemma(self):
        result = dis_mod.disambiguate("قمر", "طلع القمر", _ayn_inventory())
        assert result.status == "unknown_lemma"
        assert result.sense_id is None
        assert result.confidence is None
        assert result.alternatives == ()
        assert result.provenance == ()

    def test_low_confidence_abstains_below_default_bar(self):
        # Two senses tie on evidence -> 0.5 each < 0.6 default bar.
        entries = [
            inv_mod.SenseEntry(
                sense_id="t:w:a", lemma="w", gloss_en="x", gloss_ar="الماء", religious=False
            ),
            inv_mod.SenseEntry(
                sense_id="t:w:b", lemma="w", gloss_en="y", gloss_ar="الماء", religious=False
            ),
        ]
        inventory = inv_mod.SenseInventory(entries=entries)
        result = dis_mod.disambiguate("w", "شرب الماء", inventory)
        assert result.status == "uncertain"
        assert result.sense_id is None
        assert result.threshold_used == pytest.approx(0.6)

    def test_explicit_threshold_overrides(self):
        entries = [
            inv_mod.SenseEntry(
                sense_id="t:w:a", lemma="w", gloss_en="x", gloss_ar="الماء", religious=False
            ),
            inv_mod.SenseEntry(
                sense_id="t:w:b", lemma="w", gloss_en="y", gloss_ar="الماء", religious=False
            ),
        ]
        inventory = inv_mod.SenseInventory(entries=entries)
        result = dis_mod.disambiguate("w", "شرب الماء", inventory, threshold=0.4)
        assert result.status == "ok"
        assert result.threshold_used == pytest.approx(0.4)

    def test_religious_bar_stricter(self):
        # Same evidence shape, religious flag -> 0.8 bar (JEV 0.92).
        entries = [
            inv_mod.SenseEntry(
                sense_id="t:w:a", lemma="w", gloss_en="x", gloss_ar="الماء", religious=True
            ),
            inv_mod.SenseEntry(
                sense_id="t:w:b", lemma="w", gloss_en="y", gloss_ar="الماء", religious=True
            ),
        ]
        inventory = inv_mod.SenseInventory(entries=entries)
        result = dis_mod.disambiguate("w", "شرب الماء", inventory)
        assert result.status == "uncertain"
        assert result.threshold_used == pytest.approx(0.8)

    def test_invalid_inputs_raise(self):
        inventory = _ayn_inventory()
        with pytest.raises(ValueError):
            dis_mod.disambiguate("", "context", inventory)
        with pytest.raises(ValueError):
            dis_mod.disambiguate("عين", "  ", inventory)
        with pytest.raises(ValueError):
            dis_mod.disambiguate("عين", "context", inventory, threshold=2.0)


class TestModelHook:
    def test_model_signal_only_when_wired(self):
        inventory = _ayn_inventory()
        without = dis_mod.disambiguate("عين", "شربت من العين ماء عذبا", inventory)
        assert "model" not in {p["signal"] for p in without.to_dict()["provenance"]}

        with_model = dis_mod.disambiguate(
            "عين",
            "شربت من العين ماء عذبا",
            inventory,
            model_scores={"test:ayn:spring": 0.9, "test:ayn:eye": 0.05, "test:ayn:spy": 0.05},
            model_source="mizan-sense-wsd/1.2.1",
        )
        prov = with_model.to_dict()["provenance"]
        by_signal = {p["signal"]: p for p in prov}
        assert by_signal["model"]["source"] == "mizan-sense-wsd/1.2.1"
        # The two shares decompose the winner's confidence.
        assert by_signal["model"]["weight"] + by_signal["context_overlap"][
            "weight"
        ] == pytest.approx(1.0)

    def test_empty_model_scores_ignored(self):
        inventory = _ayn_inventory()
        result = dis_mod.disambiguate("عين", "شربت من العين ماء عذبا", inventory, model_scores={})
        assert "model" not in {p["signal"] for p in result.to_dict()["provenance"]}
