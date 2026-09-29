#!/usr/bin/env python3
"""Phase-3 eval harness for mizan.nlp candidate artifacts.

Compares a candidate artifact (joblib + manifest.json + sense_inventory.json)
against the locked Phase-3 baseline on the frozen Phase-1 whole-surah holdout
test split, and applies the preregistered decision rule
(PREREGISTRATION_PHASE3.md) to produce a PASS/FAIL verdict.

Trust boundary: the artifact directory is operator-supplied. The manifest is
fully validated (schema + required files + sha256 checksums + size budget)
BEFORE the joblib is unpickled. Any validation failure is fail-closed: the
harness exits non-zero and, in candidate mode, writes a report with
pass=false and the reason recorded.

Usage:
  # Lock the baseline (run once, on the main artifact, AFTER the prereg freeze):
  python3 eval_phase3.py --artifact <dir> --data qcsmp_v2.jsonl \\
      --lock-baseline BASELINE_PHASE3.json

  # Evaluate a candidate against the locked baseline:
  python3 eval_phase3.py --artifact <dir> --data qcsmp_v2.jsonl \\
      --baseline BASELINE_PHASE3.json --out report.json

Determinism: lbfgs/DictVectorizer are deterministic; bootstrap CIs use the
frozen seed 137 with 10,000 resamples (same recipe as Track 1).
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

# The harness ships inside backend/nlp/, so the nlp package is importable
# from the repo's backend/ directory. Manifest validation stays single-sourced
# in nlp/artifact.py; the feature extractor stays single-sourced in nlp/wsd.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nlp import wsd as wsd_mod  # noqa: E402  (frozen feature extractor)
from nlp.artifact import (  # noqa: E402
    ArtifactManifest,
)

# ── Frozen protocol constants (PREREGISTRATION_PHASE3.md §1-§4) ────────────
DATA_MD5 = "35c1a6bf0cbaa58aa7d52d3683d68b5d"
SPLIT_COUNTS = {"train": 4691, "dev": 451, "test": 627}
N_SENSES_UNIVERSE = 115
PRIMARY_MODEL_KEY = "model_a_surface_ctx"
SECONDARY_MODEL_KEY = "model_b_surface_ctx_morph"
BOOT_SEED = 137
BOOT_N = 10000

TARGET_SENSES = [  # (lemma, sense) — frozen §3, baseline recall 0.0 on all 12
    ("أَجْر", "payment"),
    ("أَيّ", "so which"),
    ("بَعْض", "some"),
    ("ذُو", "owner"),
    ("صالِحَة", "good deeds"),
    ("عِلْم", "any knowledge"),
    ("قَرْيَة", "cities"),
    ("قَوْل", "saying"),
    ("كِتاب", "scripture"),
    ("مُبِين", "manifest"),
    ("نَذِير", "warning"),
    ("نِساء", "wives"),
]

# Frozen decision rule (PREREGISTRATION_PHASE3.md §4; tolerances via JEV §7)
RULE = {
    "win_lift_bar": 0.10,  # mean target-sense recall lift (JEV, conf 0.33)
    "guard_acc_drop": 0.02,  # max accuracy drop (JEV, conf 0.73)
    "guard_f1_drop": 0.02,  # max macro-F1 drop (JEV, conf 0.73)
    "regression_support_floor": 5,  # n_test >= 5 for hard regression (JEV, conf 0.69)
}


class HarnessError(Exception):
    """Fail-closed: something about the artifact/data/protocol is invalid."""


# ── Frozen feature extractors ─────────────────────────────────────────────
# Byte-identical logic to nlp/wsd.py::_features (frozen 2026-09-29, copied
# verbatim from Track 1's training code). The harness self-tests equality
# against wsd._features on load and aborts on any mismatch (fail-closed:
# silent feature drift would invalidate every number).


def _ngrams(s, lo=2, hi=4):
    s = " " + (s or "") + " "
    out = {}
    for n in range(lo, hi + 1):
        for i in range(len(s) - n + 1):
            g = f"c{n}:{s[i : i + n]}"
            out[g] = out.get(g, 0) + 1
    return out


def _features_a(record):
    d = {}
    for k, s in (
        ("f", record.get("form")),
        ("p", (record.get("prev") or {}).get("form")),
        ("n", (record.get("next") or {}).get("form")),
    ):
        for g, c in _ngrams(s).items():
            d[f"{k}:{g}"] = c
    d[f"len={(record.get('morph') or {}).get('n_letters')}"] = 1
    return d


def _features_b(record):
    d = dict(_features_a(record))
    m = record.get("morph") or {}
    d[f"root={record.get('root')}"] = 1
    d[f"prev_root={(record.get('prev') or {}).get('root')}"] = 1
    d[f"next_root={(record.get('next') or {}).get('root')}"] = 1
    d[f"n_seg={m.get('n_seg')}"] = 1
    d[f"n_letters={m.get('n_letters')}"] = 1
    d[f"pos={record.get('pos')}"] = 1
    return d


def _self_test_features():
    """Abort unless the harness extractors match the shipped frozen one."""
    probe = {
        "form": "يَوْمِ",
        "prev": {"form": "مَٰلِكِ"},
        "next": {"form": "ٱلدِّينِ"},
        "root": "يوم",
        "pos": "N",
        "morph": {"n_seg": 1, "n_letters": 3},
    }
    if _features_a(probe) != wsd_mod._features(probe, variant="a"):
        raise HarnessError("feature extractor drift: variant a != nlp.wsd._features")
    if _features_b(probe) != wsd_mod._features(probe, variant="b"):
        raise HarnessError("feature extractor drift: variant b != nlp.wsd._features")


# ── Data loading + split-identity verification ───────────────────────────


def _md5(path: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_split_verified(data_path: Path):
    """Load base items; verify dataset md5, split counts, per-lemma surah
    disjointness (the Phase-1 whole-surah holdout identity)."""
    if _md5(data_path) != DATA_MD5:
        raise HarnessError(f"dataset md5 mismatch: {data_path} is not the frozen Q-CSMP v2 build")
    rows = {"train": [], "dev": [], "test": []}
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("perturbation") != "base":
                continue
            rows[r["split"]].append(r)
    for split, want in SPLIT_COUNTS.items():
        got = len(rows[split])
        if got != want:
            raise HarnessError(f"split identity broken: {split} has {got}, want {want}")
    # Per-lemma whole-surah holdout: no lemma's test/dev surah may appear in
    # its train surahs (or dev in train).
    surahs = defaultdict(lambda: defaultdict(set))
    for split in rows:
        for r in rows[split]:
            surahs[r["lemma"]][split].add(r["surah"])
    for lemma, d in surahs.items():
        if (d["test"] | d["dev"]) & d["train"] or d["test"] & d["dev"]:
            raise HarnessError(f"split identity broken: surah overlap for {lemma}")
    universe = sorted({(r["lemma"], r["sense"]) for s in rows.values() for r in s})
    if len(universe) != N_SENSES_UNIVERSE:
        raise HarnessError(f"label universe is {len(universe)}, want {N_SENSES_UNIVERSE}")
    for t in TARGET_SENSES:
        if t not in universe:
            raise HarnessError(f"target sense {t} not in label universe")
    return rows, universe


# ── Artifact loading (manifest verified BEFORE unpickle) ─────────────────


def load_artifact_verified(artifact_dir: Path):
    """Validate manifest (schema + files + sha256 + size) then unpickle."""
    manifest_path = artifact_dir / "manifest.json"
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = ArtifactManifest.from_dict(json.load(f))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"manifest unreadable: {exc}") from exc
    problems = manifest.validate(artifact_dir)
    if problems:
        raise HarnessError("manifest validation failed: " + "; ".join(problems))
    # NOTE: sha256 of model.joblib + sense_inventory.json was verified inside
    # manifest.validate(artifact_dir) — this unpickle happens only after.
    import joblib

    try:
        bundle = joblib.load(artifact_dir / manifest.model_file)
    except Exception as exc:  # noqa: BLE001 — fail closed, never half-load
        raise HarnessError(f"joblib load failed: {exc}") from exc
    models = bundle.get("models")
    if not isinstance(models, dict) or PRIMARY_MODEL_KEY not in models:
        raise HarnessError(f"bundle contract violated: missing primary {PRIMARY_MODEL_KEY!r}")
    per_lemma = models[PRIMARY_MODEL_KEY].get("per_lemma")
    if not isinstance(per_lemma, dict):
        raise HarnessError("bundle contract violated: per_lemma is not a dict")
    for lemma, m in per_lemma.items():
        if not all(k in m for k in ("vec", "clf", "labels")):
            raise HarnessError(f"bundle contract violated: lemma {lemma!r} incomplete")
    inv_path = artifact_dir / "sense_inventory.json"
    with open(inv_path, encoding="utf-8") as f:
        sense_inventory = json.load(f)
    versions = {}
    for mod, attr in (
        ("sklearn", "__version__"),
        ("joblib", "__version__"),
        ("numpy", "__version__"),
    ):
        try:
            versions[mod] = __import__(mod).__dict__.get(attr, "?")
        except ImportError:
            versions[mod] = "missing"
    version_warnings = []
    for mod, key in (("sklearn", "sklearn_version"),):
        want = getattr(manifest, key, "")
        if want and versions.get(mod) != want:
            version_warnings.append(f"{mod} runtime {versions.get(mod)} != manifest {want}")
    return {
        "manifest": manifest,
        "bundle": bundle,
        "sense_inventory": sense_inventory,
        "versions": versions,
        "version_warnings": version_warnings,
    }


# ── Metrics (exact Track-1 recipes) ───────────────────────────────────────


def predict_primary(bundle, rows):
    per_lemma = bundle["models"][PRIMARY_MODEL_KEY]["per_lemma"]
    pred = []
    for r in rows:
        m = per_lemma.get(r["lemma"])
        if m is None:
            pred.append(None)
            continue
        X = m["vec"].transform([_features_a(r)])
        p = m["clf"].predict_proba(X)[0]
        pred.append(m["labels"][int(np.argmax(p))])
    return pred


def predict_secondary(bundle, rows):
    """Variant b if present — informational only, no decision weight."""
    models = bundle["models"]
    if SECONDARY_MODEL_KEY not in models:
        return None
    per_lemma = models[SECONDARY_MODEL_KEY]["per_lemma"]
    pred = []
    for r in rows:
        m = per_lemma.get(r["lemma"])
        if m is None:
            pred.append(None)
            continue
        X = m["vec"].transform([_features_b(r)])
        p = m["clf"].predict_proba(X)[0]
        pred.append(m["labels"][int(np.argmax(p))])
    return pred


def accuracy(pred, rows):
    ok = [p == r["sense"] for p, r in zip(pred, rows, strict=True)]
    return sum(ok) / len(ok), ok


def macro_f1(pred, rows, senses_all):
    """Macro-F1 over the full 115 sense inventory; absent-from-test senses
    contribute 0.0 (frozen Track-1 rule, replicated exactly)."""
    from sklearn.metrics import f1_score

    inv = {s: i for i, s in enumerate(senses_all)}
    y_true = np.array([inv[(r["lemma"], r["sense"])] for r in rows])
    y_pred = np.array(
        [
            inv[(r["lemma"], p)] if p is not None and (r["lemma"], p) in inv else -1
            for p, r in zip(pred, rows, strict=True)
        ]
    )
    y_p2 = np.where(y_pred == -1, len(senses_all), y_pred)
    f1 = f1_score(
        np.append(y_true, [len(senses_all)]),
        np.append(y_p2, [-1]),
        labels=list(range(len(senses_all))),
        average="macro",
        zero_division=0,
    )
    return float(f1)


def per_sense_table(pred, rows, universe):
    """Per-sense recall for all 115 senses; test-absent -> recall None."""
    s_ok, s_t = defaultdict(int), defaultdict(int)
    for r, p in zip(pred, rows, strict=True):
        k = (r["lemma"], r["sense"])
        s_t[k] += 1
        if p == r["sense"]:
            s_ok[k] += 1
    out = {}
    for lemma, sense in universe:
        k = (lemma, sense)
        n = s_t.get(k, 0)
        out[f"{lemma} :: {sense}"] = {
            "recall": round(s_ok[k] / n, 6) if n else None,
            "n_test": n,
        }
    return out


def per_lemma_acc(pred, rows):
    acc = {}
    for r, p in zip(rows, pred, strict=True):
        a, t = acc.get(r["lemma"], (0, 0))
        acc[r["lemma"]] = (a + (p == r["sense"]), t + 1)
    return {lemma: round(a / t, 6) for lemma, (a, t) in sorted(acc.items())}


def ece(probs, ok, bins=10):
    # Exact Track-1 recipe (incl. its operator-precedence shape).
    e, n = 0.0, len(ok)
    for b in range(bins):
        sel = [
            i
            for i, p in enumerate(probs)
            if p is not None and b / bins <= p < (b + 1) / bins or (b == bins - 1 and p == 1.0)
        ]
        if not sel:
            continue
        conf = sum(probs[i] for i in sel) / len(sel)
        acc = sum(ok[i] for i in sel) / len(sel)
        e += len(sel) / n * abs(conf - acc)
    return e


def bootstrap_cis(pred, rows, senses_all):
    rng = np.random.RandomState(BOOT_SEED)
    n = len(rows)
    ba, bf = [], []
    for _ in range(BOOT_N):
        idx = rng.randint(0, n, n)
        sub = [rows[i] for i in idx]
        sp = [pred[i] for i in idx]
        a, _ = accuracy(sp, sub)
        ba.append(a)
        bf.append(macro_f1(sp, sub, senses_all))

    def _ci(v):
        return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]

    return _ci(ba), _ci(bf)


def evaluate(bundle, rows, universe):
    test = rows["test"]
    pred = predict_primary(bundle, test)
    acc, ok = accuracy(pred, test)
    f1 = macro_f1(pred, test, universe)
    acc_ci, f1_ci = bootstrap_cis(pred, test, universe)
    attested = [k for k in per_sense_table(pred, test, universe).values() if k["n_test"] > 0]
    mean_recall = float(np.mean([k["recall"] for k in attested]))
    # ECE needs confidences: recompute top-1 probs
    per_lemma = bundle["models"][PRIMARY_MODEL_KEY]["per_lemma"]
    probs = []
    for r in test:
        m = per_lemma.get(r["lemma"])
        if m is None:
            probs.append(None)
            continue
        X = m["vec"].transform([_features_a(r)])
        probs.append(float(np.max(m["clf"].predict_proba(X)[0])))
    metrics = {
        "accuracy": round(acc, 6),
        "accuracy_ci95": acc_ci,
        "macro_f1": round(f1, 6),
        "macro_f1_ci95": f1_ci,
        "mean_sense_recall": round(mean_recall, 6),
        "ece": round(ece(probs, ok), 6),
        "per_sense_recall": per_sense_table(pred, test, universe),
        "per_lemma_accuracy": per_lemma_acc(pred, test),
        "n_test": len(test),
    }
    sec = predict_secondary(bundle, test)
    if sec is not None:
        sa, _ = accuracy(sec, test)
        metrics["secondary_variant_b"] = {
            "accuracy": round(sa, 6),
            "macro_f1": round(macro_f1(sec, test, universe), 6),
            "note": "informational only — no decision weight (Track-1 protocol)",
        }
    return metrics


# ── Decision rule ─────────────────────────────────────────────────────────


def apply_rule(candidate_metrics, baseline_metrics):
    cm, bm = candidate_metrics, baseline_metrics
    d_acc = cm["accuracy"] - bm["accuracy"]
    d_f1 = cm["macro_f1"] - bm["macro_f1"]
    targets = []
    for lemma, sense in TARGET_SENSES:
        key = f"{lemma} :: {sense}"
        rc = cm["per_sense_recall"][key]["recall"]
        rb = bm["per_sense_recall"][key]["recall"]
        targets.append(
            {
                "sense": key,
                "baseline_recall": rb,
                "candidate_recall": rc,
                "delta": round((rc or 0.0) - (rb or 0.0), 6),
                "n_test": cm["per_sense_recall"][key]["n_test"],
            }
        )
    lift = float(np.mean([t["delta"] for t in targets]))
    regressions, warnings = [], []
    for key, b in bm["per_sense_recall"].items():
        c = cm["per_sense_recall"][key]
        if b["recall"] not in (None, 0.0) and b["n_test"] > 0 and c["recall"] == 0.0:
            entry = {"sense": key, "baseline_recall": b["recall"], "n_test": b["n_test"]}
            if b["n_test"] >= RULE["regression_support_floor"]:
                regressions.append(entry)
            else:
                warnings.append({**entry, "note": "n_test < 5: warning, not fail"})
    legs = {
        "win_lift": {
            "value": round(lift, 6),
            "bar": RULE["win_lift_bar"],
            "pass": lift >= RULE["win_lift_bar"],
        },
        "guard_accuracy": {
            "delta": round(d_acc, 6),
            "max_drop": RULE["guard_acc_drop"],
            "pass": d_acc >= -RULE["guard_acc_drop"],
        },
        "guard_macro_f1": {
            "delta": round(d_f1, 6),
            "max_drop": RULE["guard_f1_drop"],
            "pass": d_f1 >= -RULE["guard_f1_drop"],
        },
        "no_regression": {"violations": regressions, "pass": len(regressions) == 0},
    }
    verdict = all(legs[k]["pass"] for k in legs)
    return {
        "pass": verdict,
        "legs": legs,
        "target_senses": targets,
        "mean_target_recall_lift": round(lift, 6),
        "accuracy_delta": round(d_acc, 6),
        "macro_f1_delta": round(d_f1, 6),
        "regression_warnings": warnings,
        "rule": RULE,
    }


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description="Phase-3 eval harness for mizan.nlp")
    ap.add_argument(
        "--artifact",
        required=True,
        help="candidate artifact directory (manifest.json + model.joblib + sense_inventory.json)",
    )
    ap.add_argument("--data", required=True, help="Q-CSMP v2 jsonl path")
    ap.add_argument(
        "--lock-baseline",
        metavar="OUT",
        help="baseline-lock mode: write BASELINE_PHASE3.json (no verdict)",
    )
    ap.add_argument(
        "--baseline", metavar="JSON", help="candidate mode: locked baseline JSON for deltas"
    )
    ap.add_argument("--out", metavar="JSON", help="candidate mode: write report here")
    args = ap.parse_args()

    _self_test_features()
    rows, universe = load_split_verified(Path(args.data))
    art = load_artifact_verified(Path(args.artifact))
    manifest = art["manifest"]
    metrics = evaluate(art["bundle"], rows, universe)

    artifact_id = {
        "name": manifest.name,
        "version": manifest.version,
        "variant": manifest.variant,
        "model_sha256": manifest.model_sha256,
        "sense_inventory_sha256": manifest.sense_inventory_sha256,
        "sklearn_version_manifest": manifest.sklearn_version,
        "runtime_versions": art["versions"],
        "version_warnings": art["version_warnings"],
    }
    protocol = {
        "preregistration": "backend/nlp/PREREGISTRATION_PHASE3.md (frozen 2026-09-29)",
        "dataset": "Q-CSMP v2",
        "dataset_md5": DATA_MD5,
        "split": "per-lemma whole-surah holdout, base items only",
        "n_train": SPLIT_COUNTS["train"],
        "n_dev": SPLIT_COUNTS["dev"],
        "n_test": SPLIT_COUNTS["test"],
        "label_universe": N_SENSES_UNIVERSE,
        "primary_model": PRIMARY_MODEL_KEY,
        "bootstrap": {"seed": BOOT_SEED, "resamples": BOOT_N},
        "run_at": datetime.now(UTC).isoformat(),
    }

    if args.lock_baseline:
        baseline = {
            "kind": "BASELINE_PHASE3",
            "artifact": artifact_id,
            "protocol": protocol,
            "metrics": metrics,
            "target_senses": [
                {
                    "sense": f"{lemma} :: {sense}",
                    "sense_id": next(
                        (
                            sid
                            for sid, v in art["sense_inventory"].items()
                            if v.get("lemma") == lemma and v.get("sense") == sense
                        ),
                        None,
                    ),
                    "baseline_recall": metrics["per_sense_recall"][f"{lemma} :: {sense}"]["recall"],
                    "n_test": metrics["per_sense_recall"][f"{lemma} :: {sense}"]["n_test"],
                }
                for lemma, sense in TARGET_SENSES
            ],
            "claim": "locked by eval_phase3.py --lock-baseline on the main artifact; "
            "deltas for all future candidates are computed against these numbers",
        }
        with open(args.lock_baseline, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=1)
        print(f"baseline locked -> {args.lock_baseline}")
        print(
            f"accuracy={metrics['accuracy']} ci95={metrics['accuracy_ci95']} "
            f"macro_f1={metrics['macro_f1']} ci95={metrics['macro_f1_ci95']}"
        )
        return

    if not args.baseline or not args.out:
        print("candidate mode needs --baseline and --out", file=sys.stderr)
        sys.exit(2)
    with open(args.baseline, encoding="utf-8") as f:
        baseline = json.load(f)
    verdict = apply_rule(metrics, baseline["metrics"])
    report = {
        "kind": "PHASE3_CANDIDATE_REPORT",
        "candidate_artifact": artifact_id,
        "protocol": protocol,
        "baseline_ref": {
            "accuracy": baseline["metrics"]["accuracy"],
            "macro_f1": baseline["metrics"]["macro_f1"],
            "artifact": baseline["artifact"]["name"] + " v" + baseline["artifact"]["version"],
            "model_sha256": baseline["artifact"]["model_sha256"],
        },
        "candidate_metrics": metrics,
        "verdict": verdict,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    v = verdict
    print(
        f"verdict: {'PASS' if v['pass'] else 'FAIL'} "
        f"(lift={v['mean_target_recall_lift']} d_acc={v['accuracy_delta']} "
        f"d_f1={v['macro_f1_delta']} regressions={len(v['legs']['no_regression']['violations'])})"
    )
    print(f"report -> {args.out}")


if __name__ == "__main__":
    try:
        main()
    except HarnessError as e:
        print(f"HARNESS FAIL-CLOSED: {e}", file=sys.stderr)
        sys.exit(2)
