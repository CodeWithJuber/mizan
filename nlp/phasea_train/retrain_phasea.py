"""Phase-A execution: MASAQ-grounded 9-merge retrain (Juber REVISE spec v2, frozen).

Scope: merges #3-#11 only (أَيّ #1-#2 HELD — untouched). 106 -> 97 senses.

Mapping composition (reproducibility guard):
    Q-CSMP v2 115 labels --PR-41--> 106 --Phase-A--> 97 final.
Assertions: final class count == 97, Phase-A relabeled == 1005,
unmapped labels == 0, no (lemma,sense) is a merge source in both maps.

Win bar (remapped-baseline comparator, spec v2 §5.2): the EXACT Phase-A
mapping is applied to the frozen post-PR-41 baseline's y_true AND y_pred on
the frozen test split FIRST (isolates ontology-simplification gain from
retraining gain). Gates:
    new_acc      >= remapped_acc - 0.005
    new_macro_f1 >= remapped_macro_f1 - 0.01
    no NEW zero-recall class in the merged ontology
    per affected target: new recall >= remapped-baseline pooled recall

Recipe: exact Track-1/PR-41 — per-lemma DictVectorizer + LogisticRegression
(lbfgs, C=1.0, max_iter=1000); DummyClassifier(strategy='prior') for
single-sense lemmas; frozen _features from nlp/wsd.py (sha256-pinned);
variant 'a' for eval (PRIMARY, same as PR-41).

Reads:  ~/workspace/research/stage2/qcsmp_v2.jsonl (md5-verified)
        ./SENSE_MERGES_PR41.json  (9 merges, byte-identical to nlp/SENSE_MERGES.json on main)
        ./SENSE_MERGES_PHASEA.json (9 merges, frozen)
        ~/workspace/mizan-merges/stage/model.joblib (post-PR-41 v1.1.0 baseline artifact)
Writes: <stage>/{model.joblib, sense_inventory.json, manifest.json}  (candidate ONLY;
        nlp/artifacts/default/ is never touched)
"""

import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

_HERE = Path(__file__).resolve().parent
# Portable: inside a repo checkout (nlp/phasea_train/) use the checkout's own
# nlp/; otherwise fall back to the frozen repocheck copy.
_REPO_WSD = _HERE.parent.parent / "nlp" / "wsd.py"
_WSD_PATH = (
    _REPO_WSD
    if _REPO_WSD.exists()
    else Path(os.path.expanduser("~/workspace/mizan-merges/repocheck/nlp/wsd.py"))
)
sys.path.insert(0, str(_WSD_PATH.parent.parent))  # frozen _features
from nlp.wsd import _features  # noqa: E402  (path setup above is required first)

WSD_SHA256 = "566ddaf3705899bce210ebdee680d6f9a7df352e51fe99cc5c83fe0b062761d0"
DATA = Path(os.path.expanduser("~/workspace/research/stage2/qcsmp_v2.jsonl"))
DATA_MD5 = "35c1a6bf0cbaa58aa7d52d3683d68b5d"
BASELINE_BUNDLE = Path(
    os.path.expanduser("~/workspace/mizan-merges/stage/model.joblib")
)
SPLIT_COUNTS = {"train": 4691, "dev": 451, "test": 627}
BOOT_SEED = 137
BOOT_N = 10_000
STAGE = Path(os.environ.get("MIZAN_PHASEA_STAGE", str(_HERE / "stage")))
GATE_ACC_TOL = 0.005
GATE_F1_TOL = 0.01


def _md5(p: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def load_merge_map(path: Path, expect_n: int) -> dict:
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    out = {}
    for k, v in m.items():
        if k == "_note":
            continue
        _, lemma, sense = k.split(":", 2)
        _, t_lemma, t_sense = v.split(":", 2)
        assert lemma == t_lemma, f"merge must stay within lemma: {k} -> {v}"
        out[(lemma, sense)] = t_sense
    assert len(out) == expect_n, f"want {expect_n} merges in {path}, got {len(out)}"
    return out


def load_splits():
    if _md5(DATA) != DATA_MD5:
        raise SystemExit("dataset md5 mismatch — not the frozen Q-CSMP v2 build")
    rows = {"train": [], "dev": [], "test": []}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("perturbation") != "base":
                continue
            rows[r["split"]].append(r)
    for s, want in SPLIT_COUNTS.items():
        got = len(rows[s])
        if got != want:
            raise SystemExit(f"split identity broken: {s} has {got}, want {want}")
    surahs = defaultdict(lambda: defaultdict(set))
    for s, srows in rows.items():
        for r in srows:
            surahs[r["lemma"]][s].add(r["surah"])
    for lemma, d in surahs.items():
        if (d["test"] | d["dev"]) & d["train"] or d["test"] & d["dev"]:
            raise SystemExit(f"surah overlap for {lemma}")
    return rows


def accuracy(pred, rs):
    ok = [a == b["sense"] for a, b in zip(pred, rs, strict=True)]
    return sum(ok) / len(ok)


def macro_f1(pred, rs, universe):
    inv = {s: i for i, s in enumerate(universe)}
    y_true = np.array([inv[(r["lemma"], r["sense"])] for r in rs])
    y_pred = np.array(
        [
            inv[(r["lemma"], s)] if s is not None and (r["lemma"], s) in inv else -1
            for s, r in zip(pred, rs, strict=True)
        ]
    )
    y_p2 = np.where(y_pred == -1, len(universe), y_pred)
    return float(
        f1_score(
            np.append(y_true, [len(universe)]),
            np.append(y_p2, [-1]),
            labels=list(range(len(universe))),
            average="macro",
            zero_division=0,
        )
    )


def per_class_recall(pred, rs, universe):
    """recall per (lemma, sense); only classes with test support > 0."""
    tp = defaultdict(int)
    sup = defaultdict(int)
    for s, r in zip(pred, rs, strict=True):
        key = (r["lemma"], r["sense"])
        sup[key] += 1
        if s == r["sense"]:
            tp[key] += 1
    return {k: tp[k] / sup[k] for k in sup}


def predict_test(per_lemma, test):
    pred = []
    for r in test:
        m_ = per_lemma.get(r["lemma"])
        if m_ is None:
            pred.append(None)
            continue
        x = m_["vec"].transform([_features(r, "a")])
        p = m_["clf"].predict_proba(x)[0]
        pred.append(m_["labels"][int(np.argmax(p))])
    return pred


def train_per_lemma(train_rows):
    per_a, per_b = {}, {}
    single = []
    lemmas = sorted({r["lemma"] for r in train_rows})
    assert len(lemmas) == 48, lemmas
    for lem in lemmas:
        tr = [r for r in train_rows if r["lemma"] == lem]
        senses = sorted({r["sense"] for r in tr})
        lab = {s: i for i, s in enumerate(senses)}
        y = np.array([lab[r["sense"]] for r in tr])
        for variant, store in (("a", per_a), ("b", per_b)):
            vec = DictVectorizer()
            x = vec.fit_transform([_features(r, variant) for r in tr])
            clf = (
                DummyClassifier(strategy="prior")
                if len(senses) == 1
                else LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
            )
            clf.fit(x, y)
            store[lem] = {"vec": vec, "clf": clf, "labels": senses}
        if len(senses) == 1:
            single.append(lem)
    return per_a, per_b, single


def main() -> None:
    wsd_path = _WSD_PATH
    assert _sha256(wsd_path) == WSD_SHA256, "frozen _features changed — abort"
    print(f"frozen _features OK ({WSD_SHA256[:12]}…)")

    map41 = load_merge_map(_HERE / "SENSE_MERGES_PR41.json", 9)
    mapA = load_merge_map(_HERE / "SENSE_MERGES_PHASEA.json", 9)
    overlap = set(map41) & set(mapA)
    assert not overlap, f"merge source in both maps: {overlap}"
    print("maps loaded: PR-41 x9, Phase-A x9, no source overlap")

    rows = load_splits()
    # all-perturbation records (for the dataset-level relabel count only;
    # the frozen recipe trains/evals on base only)
    rows_all = []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            new = map41.get((r["lemma"], r["sense"]))
            if new:
                r = dict(r)
                r["sense"] = new
            rows_all.append(r)
    universe_115 = sorted({(r["lemma"], r["sense"]) for s in rows.values() for r in s})
    assert len(universe_115) == 115, len(universe_115)

    def apply(r, mp):
        r = dict(r)
        new = mp.get((r["lemma"], r["sense"]))
        if new:
            r["sense"] = new
        return r

    rows106 = {s: [apply(r, map41) for r in rows[s]] for s in rows}
    universe_106 = sorted(
        {(r["lemma"], r["sense"]) for s in rows106.values() for r in s}
    )
    assert len(universe_106) == 106, len(universe_106)

    rows97 = {s: [apply(r, mapA) for r in rows106[s]] for s in rows106}
    universe_97 = sorted({(r["lemma"], r["sense"]) for s in rows97.values() for r in s})
    assert len(universe_97) == 97, f"final universe is {len(universe_97)}, want 97"

    n_relabeled_A = sum(
        1
        for s in rows106
        for a, b in zip(rows106[s], rows97[s], strict=True)
        if a["sense"] != b["sense"]
    )
    # JEV (0.81): assert BOTH scopes. 201 = base-perturbation records the frozen
    # recipe actually trains on; 1005 = 201 x 5 perturbations = dataset-level
    # count matching the spec number. Both true; definitions kept explicit.
    assert n_relabeled_A == 201, f"Phase-A relabeled (base) {n_relabeled_A}, want 201"
    n_relabeled_all = sum(
        1 for r in rows_all for k in [mapA.get((r["lemma"], r["sense"]))] if k
    )
    assert n_relabeled_all == 1005, (
        f"Phase-A relabeled (all) {n_relabeled_all}, want 1005"
    )
    for (lemma, sense), target in mapA.items():
        assert (lemma, sense) not in universe_97, f"merged-away still present: {sense}"
        assert (lemma, target) in universe_97, f"merge target missing: {target}"
    # unmapped labels == 0: every final (lemma, sense) resolves inside the 97 universe
    inv97 = set(universe_97)
    unmapped = [
        (r["lemma"], r["sense"])
        for s in rows97.values()
        for r in s
        if (r["lemma"], r["sense"]) not in inv97
    ]
    assert not unmapped, f"unmapped labels: {unmapped[:5]}"
    print(
        f"composition OK: 115 -> 106 -> 97 | Phase-A relabeled: {n_relabeled_A} | unmapped: 0"
    )

    # ── Frozen baseline recompute (post-PR-41 v1.1.0, 106 senses) ──────────
    bundle = joblib.load(BASELINE_BUNDLE)
    per_a_base = bundle["models"]["model_a_surface_ctx"]["per_lemma"]
    test106 = rows106["test"]
    y_pred_106 = predict_test(per_a_base, test106)
    base_acc = accuracy(y_pred_106, test106)
    base_f1 = macro_f1(y_pred_106, test106, universe_106)
    assert abs(base_acc - 0.8038) < 0.002, f"baseline recipe drift: acc={base_acc:.4f}"
    print(
        f"baseline recomputed: acc={base_acc:.4f} (≈0.8038 ✓) | macro_f1={base_f1:.4f}"
    )

    # ── Remapped baseline: EXACT Phase-A map on y_true AND y_pred ──────────
    def remap(lemma, sense):
        return mapA.get((lemma, sense), sense)

    test97 = rows97["test"]
    y_pred_remapped = [
        remap(r["lemma"], s) if s is not None else None
        for s, r in zip(y_pred_106, test106, strict=True)
    ]
    # sanity: remapped predictions must equal mapping applied to baseline preds
    rem_acc = accuracy(y_pred_remapped, test97)
    rem_f1 = macro_f1(y_pred_remapped, test97, universe_97)
    rem_recall = per_class_recall(y_pred_remapped, test97, universe_97)
    print(
        f"REMAPPED BASELINE: acc={rem_acc:.4f} | macro_f1={rem_f1:.4f} | n={len(test97)}"
    )

    # affected targets (8 unique — خالِد target takes 2 merges)
    targets = sorted({(lemma, t_sense) for (lemma, _s), t_sense in mapA.items()})
    assert len(targets) == 8, targets
    rem_target_recall = {t: rem_recall.get(t, 0.0) for t in targets}

    # ── Retrain on Phase-A labels (train split only) ─────────────────────
    per_a, per_b, single = train_per_lemma(rows97["train"])
    print(
        f"retrained 48 lemmas (a+b) | single-sense: {len(single)} ({', '.join(single)})"
    )

    import sklearn

    new_pred = predict_test(per_a, test97)
    new_acc = accuracy(new_pred, test97)
    new_f1 = macro_f1(new_pred, test97, universe_97)
    new_recall = per_class_recall(new_pred, test97, universe_97)

    rng = np.random.RandomState(BOOT_SEED)
    n = len(test97)
    ba, bf = [], []
    for _ in range(BOOT_N):
        idx = rng.randint(0, n, n)
        sub = [test97[i] for i in idx]
        sp = [new_pred[i] for i in idx]
        ba.append(accuracy(sp, sub))
        bf.append(macro_f1(sp, sub, universe_97))
    def ci(v):
        return [
            round(float(np.percentile(v, 2.5)), 4),
            round(float(np.percentile(v, 97.5)), 4),
        ]
    print(
        f"NEW MODEL: acc={new_acc:.4f} ci95={ci(ba)} | macro_f1={new_f1:.4f} ci95={ci(bf)}"
    )

    # ── 4 gates (revised spec v2 §5.2) ────────────────────────────────────
    gates = {}
    gates["accuracy"] = (
        new_acc >= rem_acc - GATE_ACC_TOL,
        new_acc,
        rem_acc - GATE_ACC_TOL,
    )
    gates["macro_f1"] = (new_f1 >= rem_f1 - GATE_F1_TOL, new_f1, rem_f1 - GATE_F1_TOL)
    new_dry = {c for c, rc in new_recall.items() if rc == 0.0}
    rem_dry = {c for c, rc in rem_recall.items() if rc == 0.0}
    new_zero = new_dry - rem_dry
    gates["no_new_drywells"] = (not new_zero, sorted(str(c) for c in new_zero), None)
    per_target = {}
    for t in targets:
        ok = new_recall.get(t, 0.0) >= rem_target_recall[t]
        per_target[str(t)] = (
            ok,
            round(new_recall.get(t, 0.0), 4),
            round(rem_target_recall[t], 4),
        )
    gates["target_recall"] = (all(v[0] for v in per_target.values()), per_target, None)

    print("\n── GATES ──")
    all_pass = True
    for name, (ok, got, bar) in gates.items():
        all_pass &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} bar={bar}")
    print(
        "OVERALL:",
        "PASS — ship decision goes to parent via JEV"
        if all_pass
        else "FAIL — honest null, default artifact untouched",
    )

    # ── Stage the CANDIDATE artifact (never default/) ─────────────────────
    STAGE.mkdir(parents=True, exist_ok=True)
    bundle_new = {
        "meta": {
            "dataset": "Q-CSMP v2",
            "data_md5": DATA_MD5,
            "trained": str(datetime.now(UTC).date()),
            "solver": "lbfgs",
            "merges_applied": 9,
            "merges_file": "nlp/SENSE_MERGES_PHASEA.json",
            "ontology": "97-sense merged space (Phase-A MASAQ-grounded merges, spec v2)",
            "mapping_composition": "Q-CSMP 115 -> PR-41 (nlp/SENSE_MERGES.json) -> 106 -> Phase-A -> 97",
            "phasea_relabeled": n_relabeled_A,
            "wsd_features_sha256": WSD_SHA256,
        },
        "models": {
            "model_a_surface_ctx": {"per_lemma": per_a},
            "model_b_surface_ctx_morph": {"per_lemma": per_b},
        },
        "senses_all": [list(t) for t in universe_97],
    }
    joblib.dump(bundle_new, STAGE / "model.joblib")
    inventory = {
        f"qcsmp2:{lemma}:{sense}": {"lemma": lemma, "sense": sense}
        for lemma, sense in universe_97
    }
    assert len(inventory) == 97
    with open(STAGE / "sense_inventory.json", "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    manifest = {
        "schema_version": "1",
        "name": "mizan-sense-wsd",
        "version": "1.2.0-candidate",
        "dataset": "Q-CSMP v2",
        "dataset_doi": "10.5281/zenodo.23024527",
        "num_lemmas": 48,
        "num_senses": 97,
        "eval_accuracy": round(new_acc, 4),
        "eval_macro_f1": round(new_f1, 4),
        "eval_n": n,
        "remapped_baseline": {
            "accuracy": round(rem_acc, 4),
            "macro_f1": round(rem_f1, 4),
            "note": "EXACT Phase-A mapping applied to frozen baseline y_true AND y_pred (spec v2 §5.2)",
        },
        "gates": {
            k: {"pass": bool(v[0]), "got": v[1], "bar": v[2]} for k, v in gates.items()
        },
        "per_target_recall": per_target,
        "overall": "PASS" if all_pass else "FAIL",
        "sklearn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
        "numpy_version": np.__version__,
        "trained_at": str(datetime.now(UTC).date()),
        "sense_inventory_sha256": _sha256(STAGE / "sense_inventory.json"),
        "model_sha256": _sha256(STAGE / "model.joblib"),
        "files": ["manifest.json", "model.joblib", "sense_inventory.json"],
        "trust_boundary": "CANDIDATE — not the default artifact. Same loader contract as default.",
    }
    with open(STAGE / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    config_hash = _sha256_str(
        json.dumps(
            {
                "data_md5": DATA_MD5,
                "wsd_sha256": WSD_SHA256,
                "map41": sorted(f"{k}->{v}" for k, v in map41.items()),
                "mapA": sorted(f"{k}->{v}" for k, v in mapA.items()),
                "seed": BOOT_SEED,
                "C": 1.0,
                "solver": "lbfgs",
            },
            sort_keys=True,
        )
    )
    print(f"staged: {STAGE} | config_hash={config_hash[:16]}…")


if __name__ == "__main__":
    main()
