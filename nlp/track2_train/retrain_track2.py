#!/usr/bin/env python3
"""Phase-3 Track-2: apply preregistered merges + mined data, retrain.

Reads:  $MIZAN_QCSMP_DATA (default ~/workspace/research/stage2/qcsmp_v2.jsonl)
        nlp/mining/mined_interrogative_ayy.jsonl (24 targeted-mined records)
Writes: $MIZAN_STAGE_OUT (default <workdir>/stage_artifact) with
        {model.joblib,manifest.json,sense_inventory.json}
        (the push step places them at nlp/artifacts/candidate_data_v1/)

Merge map (frozen: nlp/SENSE_MERGES_PHASE3.json, Amendment A1):
  9 label-noise merges -> 106 senses. The JEV-approved أَيّ vocative merge
  (S1, 0.80) is REVERTED: the frozen scoring ontology defines exactly the
  9 merges, and the harness fail-closes on any other label space
  (load_merges validates the map against the shipped 115-sense inventory;
  bundle labels must lie within the frozen 106). Logged honestly in
  TRACK2_REPORT.md as superseded-by-frozen-ontology.
Merges apply to train+dev+test records for the INVENTORY; training uses
train-split base records only (frozen Track-1 recipe, verified 627/627).
The test split is never used for training and never relabeled on disk.

Single-sense lemmas after merging (5 of them): honest constant predictor
via sklearn DummyClassifier(strategy='prior') — the lemma has one sense
in the merged inventory, so the model predicts it with probability 1.
"""

import hashlib
import json
import os
import sys
from datetime import date

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.expanduser("~/workspace/mizan-p3work/work"))
# Frozen feature extractor — single-sourced from nlp/wsd.py::_features.
# Works both in-repo (nlp/track2_train/retrain_track2.py -> repo root is
# parent.parent) and from the Track-2 workdir (harness_run/nlp copy).
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (
    os.path.join(_HERE, "..", ".."),
    os.path.expanduser("~/workspace/mizan-p3work/work/harness_run"),
):
    if os.path.isfile(os.path.join(_cand, "nlp", "wsd.py")):
        sys.path.insert(0, os.path.abspath(_cand))
        break
from nlp.wsd import _features as _nlp_features  # noqa: E402  (frozen, single-sourced)


def features_a(record):
    return _nlp_features(record, "a")


def features_b(record):
    return _nlp_features(record, "b")


_HERE2 = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get(
    "MIZAN_QCSMP_DATA", os.path.expanduser("~/workspace/research/stage2/qcsmp_v2.jsonl")
)
MINED = os.environ.get(
    "MIZAN_MINED_JSONL", os.path.join(_HERE2, "..", "mining", "mined_interrogative_ayy.jsonl")
)
STAGE = os.environ.get(
    "MIZAN_STAGE_OUT", os.path.expanduser("~/workspace/mizan-p3work/stage_artifact")
)
WORK = os.path.dirname(STAGE)  # train_phase3.jsonl goes next to the stage dir

MERGE = {
    ("أَجْر", "payment"): "reward",
    ("بَعْض", "some"): "other",
    ("ذُو", "owner"): "possessor",
    ("صالِحَة", "good deeds"): "righteous deeds",
    ("عِلْم", "any knowledge"): "knowledge",
    ("قَرْيَة", "cities"): "town",
    ("قَوْل", "saying"): "word",
    ("كِتاب", "scripture"): "book",
    ("مُبِين", "manifest"): "clear",
}


def apply_merge(rec):
    rec = dict(rec)
    new = MERGE.get((rec["lemma"], rec["sense"]))
    if new:
        rec["sense"] = new
    return rec


def main():
    base = []
    for line in open(DATA, encoding="utf-8"):
        r = json.loads(line)
        if r["perturbation"] == "base":
            base.append(r)
    mined = [json.loads(line) for line in open(MINED, encoding="utf-8")]
    assert all(m["split"] == "train" and m["perturbation"] == "base" for m in mined)

    merged = [apply_merge(r) for r in base]
    train = [r for r in merged if r["split"] == "train"] + mined
    with open(f"{WORK}/train_phase3.jsonl", "w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(
        f"train records: {len(train)} (base train {len(train) - len(mined)} + mined {len(mined)})"
    )

    # merged sense universe over all splits (for the inventory)
    universe = sorted({(r["lemma"], r["sense"]) for r in merged})
    print(f"merged inventory senses: {len(universe)}")
    n_merge_applied = sum(1 for a, b in zip(base, merged, strict=True) if a["sense"] != b["sense"])
    print(f"records relabeled by merges: {n_merge_applied}")

    lemmas = sorted({r["lemma"] for r in train})
    assert len(lemmas) == 48, lemmas
    per_a, per_b = {}, {}
    single = []
    for lem in lemmas:
        tr = [r for r in train if r["lemma"] == lem]
        senses = sorted({r["sense"] for r in tr})
        lab = {s: i for i, s in enumerate(senses)}
        y = np.array([lab[r["sense"]] for r in tr])
        for _key, feat, store in (("a", features_a, per_a), ("b", features_b, per_b)):
            vec = DictVectorizer()
            X = vec.fit_transform([feat(r) for r in tr])
            if len(senses) == 1:
                clf = DummyClassifier(strategy="prior")
            else:
                clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
            clf.fit(X, y)
            store[lem] = {"vec": vec, "clf": clf, "labels": senses}
        if len(senses) == 1:
            single.append(lem)
    print(f"single-sense lemmas (constant predictor): {len(single)}: {' '.join(single)}")

    bundle = {
        "meta": {
            "dataset": "Q-CSMP v2",
            "data_md5": "35c1a6bf0cbaa58aa7d52d3683d68b5d",
            "trained": str(date.today()),
            "solver": "lbfgs",
            "feat_a": "char2-4(surface,prev,next)+len",
            "feat_b": "feat_a + root/prev_root/next_root/n_seg/n_letters/pos",
            "track": "phase3-track2-data",
            "merges_applied": len(MERGE),
            "mined_items": len(mined),
        },
        "models": {
            "model_a_surface_ctx": {"per_lemma": per_a},
            "model_b_surface_ctx_morph": {"per_lemma": per_b},
        },
        "senses_all": [[lemma, s] for lemma, s in universe],
    }
    os.makedirs(STAGE, exist_ok=True)
    joblib.dump(bundle, f"{STAGE}/model.joblib")
    # The harness (load_merges) validates the frozen 9-merge map against the
    # SHIPPED inventory: merged-away sense_ids must be present. Ship the
    # ORIGINAL 115-sense inventory (byte-identical to artifacts/default/).
    import shutil

    _orig_inv = os.environ.get(
        "MIZAN_ORIG_INVENTORY",
        os.path.join(_HERE2, "..", "artifacts", "default", "sense_inventory.json"),
    )
    shutil.copyfile(_orig_inv, f"{STAGE}/sense_inventory.json")

    def sha256(p):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for c in iter(lambda: fh.read(1 << 20), b""):
                h.update(c)
        return h.hexdigest()

    import sklearn

    manifest = {
        "schema_version": "1",
        "name": "mizan-sense-wsd",
        "version": "1.1.0-data",
        "dataset": "Q-CSMP v2",
        "dataset_doi": "10.5281/zenodo.23024527",
        "dataset_note": (
            "Derived weights only. The dataset itself (Q-CSMP v2) "
            "is NOT redistributed. Train = Q-CSMP v2 base train split "
            "with the 9 frozen label-noise merges (Amendment A1) + "
            "24 targeted-mined interrogative أَيّ items "
            "(label_source=targeted-mining, real surah:ayah:word). "
            "Shipped sense_inventory.json is the original 115-sense "
            "inventory (required by the harness merge-map check); "
            "the bundle predicts the frozen 106-label space."
        ),
        "architecture": (
            "per-lemma sklearn LogisticRegression (lbfgs, C=1.0); "
            "char 2-4-gram surface+context features (variant 'a') + "
            "optional morph family (variant 'b'); single-sense lemmas "
            "use a constant prior predictor"
        ),
        "model_file": "model.joblib",
        "model_type": "sklearn-pipeline-dict",
        "sklearn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
        "numpy_version": np.__version__,
        "trained_at": str(date.today()),
        "variant": "a (surface+context; PRIMARY)",
        "license": "Apache-2.0",
        "num_lemmas": 48,
        "num_senses": 115,  # shipped inventory senses (harness merge check needs all 115)
        "eval_accuracy": None,  # filled by the eval step below
        "eval_macro_f1": None,  # filled by the eval step below
        "eval_n": 627,
        "sense_id_scheme": "qcsmp2:<lemma>:<sense-slug>",
        "sense_inventory_sha256": sha256(f"{STAGE}/sense_inventory.json"),
        "model_sha256": sha256(f"{STAGE}/model.joblib"),
        "files": ["manifest.json", "model.joblib", "sense_inventory.json"],
    }
    with open(f"{STAGE}/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"staged artifact: {STAGE}  senses={len(universe)}")


if __name__ == "__main__":
    main()
