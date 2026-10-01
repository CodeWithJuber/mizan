"""Morphology head-to-head eval: Ruh analyzer vs CAMeL Tools (beta harness).

Gold format (either):
  TSV:  ``word<TAB>root<TAB>pattern`` per line (``#`` comments, blank lines skipped)
  JSONL: ``{"word": ..., "root": ..., "pattern": ...}`` per line

``root`` is the triliteral root string (e.g. ``كتب``). ``pattern`` should use the
analyzer's coarse category vocabulary: VERB_PAST, VERB_PRESENT,
ACTIVE_PARTICIPLE, PASSIVE_PARTICIPLE, INSTRUMENT_NOUN, PLACE_NOUN,
VERBAL_NOUN, NOUN, ADJECTIVE, UNKNOWN, STOPWORD.

Ruh side: :class:`ruh_model.tokenizer.morphology.ArabicMorphAnalyzer`
(stdlib-only rule-based core of Bayan). This measures the *analyzer*, not a
trained Ruh checkpoint — no trained-model quality claim is made here.

CAMeL side: optional. If ``camel_tools`` is importable and usable, its
analyzer runs on the same gold items; otherwise the CAMeL leg is skipped with
an explicit note. A skipped comparison is reported as skipped — never as a
fabricated number.

Status: beta / unverified. Torch-free.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Torch-free analyzer loading
# ---------------------------------------------------------------------------


def _ensure_torchfree() -> None:
    """Install stub packages so ruh_model.* imports bypass torch (if needed)."""
    try:
        import ruh_model  # noqa: F401

        return
    except ImportError:
        pass
    boot_path = Path(__file__).resolve().parent / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("ruh_eval__bootstrap", boot_path)
    boot = importlib.util.module_from_spec(spec)
    sys.modules["ruh_eval__bootstrap"] = boot
    spec.loader.exec_module(boot)
    boot.ensure_torchfree()


def _ruh_analyzer() -> Any:
    """Return an ArabicMorphAnalyzer instance (stdlib-only, torch-free)."""
    try:
        from ruh_model.tokenizer.morphology import ArabicMorphAnalyzer
    except ImportError:
        _ensure_torchfree()
        from ruh_model.tokenizer.morphology import ArabicMorphAnalyzer
    return ArabicMorphAnalyzer()


# ---------------------------------------------------------------------------
# Gold data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldItem:
    word: str
    root: str
    pattern: str


def load_gold_tsv(path: str | Path) -> list[GoldItem]:
    """Load ``word<TAB>root<TAB>pattern`` gold file."""
    items: list[GoldItem] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                raise ValueError(f"{path}:{lineno}: expected 3 tab-separated fields")
            items.append(GoldItem(word=parts[0], root=parts[1], pattern=parts[2]))
    if not items:
        raise ValueError(f"{path}: no gold items found")
    return items


def load_gold_jsonl(path: str | Path) -> list[GoldItem]:
    """Load JSONL gold file with ``word``/``root``/``pattern`` keys."""
    items: list[GoldItem] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            rec = json.loads(line)
            try:
                items.append(GoldItem(word=rec["word"], root=rec["root"], pattern=rec["pattern"]))
            except KeyError as exc:
                raise ValueError(f"{path}:{lineno}: missing key {exc}") from exc
    if not items:
        raise ValueError(f"{path}: no gold items found")
    return items


def load_gold(path: str | Path) -> list[GoldItem]:
    """Dispatch gold loading on file suffix (.tsv or .jsonl)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"gold file not found: {path} — provide word<TAB>root<TAB>pattern TSV or JSONL"
        )
    if path.suffix == ".jsonl":
        return load_gold_jsonl(path)
    return load_gold_tsv(path)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

Prediction = tuple[str, str] | None  # (root, pattern) or None if analyzer failed


def score_predictions(predicted: list[Prediction], gold: list[GoldItem]) -> dict[str, Any]:
    """Score (root, pattern) predictions against gold items.

    Words the analyzer failed on (None) are excluded from denominators and
    counted in ``n_failed``. All metrics are exact string match.
    """
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold lengths differ")
    n = len(gold)
    root_ok = pattern_ok = exact_ok = n_failed = 0
    for pred, item in zip(predicted, gold, strict=True):
        if pred is None:
            n_failed += 1
            continue
        proot, ppattern = pred
        r_ok = proot == item.root
        p_ok = ppattern == item.pattern
        root_ok += r_ok
        pattern_ok += p_ok
        exact_ok += r_ok and p_ok
    scored = n - n_failed
    return {
        "n": n,
        "n_scored": scored,
        "n_failed": n_failed,
        "root_accuracy": root_ok / scored if scored else 0.0,
        "pattern_accuracy": pattern_ok / scored if scored else 0.0,
        "exact_accuracy": exact_ok / scored if scored else 0.0,
    }


def _analyze_ruh(words: list[str]) -> list[Prediction]:
    analyzer = _ruh_analyzer()
    out: list[Prediction] = []
    for word in words:
        try:
            root, pattern = analyzer.analyze(word)
            out.append((root, pattern))
        except Exception:
            out.append(None)
    return out


# ---------------------------------------------------------------------------
# CAMeL Tools leg (optional)
# ---------------------------------------------------------------------------


def try_camel_analyzer() -> tuple[Callable[[str], Prediction] | None, str]:
    """Try to build a CAMeL Tools analyzer.

    Returns (analyzer_fn, note). If camel_tools is missing or unusable, returns
    (None, skip-note) — the head-to-head degrades to a Ruh-only report, never
    to an invented comparison.
    """
    try:
        from camel_tools.morphology.analyzer import Analyzer
    except ImportError:
        return None, "skipped: camel_tools not installed (no fake comparison generated)"
    try:
        # Best-effort API shape; any failure degrades to skip, not to numbers.
        analyzer = Analyzer("msa")
        probe = analyzer.analyze("كتاب")
        if not probe:
            raise RuntimeError("empty probe analysis")
    except Exception as exc:  # noqa: BLE001 - any backend failure means skip
        return None, f"skipped: camel_tools present but unusable ({exc})"

    def _fn(word: str) -> Prediction:
        try:
            analyses = analyzer.analyze(word)
            if not analyses:
                return None
            best = analyses[0]
            root = str(best.get("root", ""))
            pattern = str(best.get("pattern", best.get("pos", "UNKNOWN")))
            return (root, pattern)
        except Exception:
            return None

    return _fn, "ok"


# ---------------------------------------------------------------------------
# Head-to-head runner
# ---------------------------------------------------------------------------


def run_morphology_eval(gold_path: str | Path, use_camel: bool = True) -> dict[str, Any]:
    """Run the head-to-head eval. Returns a JSON-serializable report dict."""
    gold = load_gold(gold_path)
    words = [item.word for item in gold]

    ruh_pred = _analyze_ruh(words)
    report: dict[str, Any] = {
        "status": "beta",
        "gold_path": str(gold_path),
        "ruh": score_predictions(ruh_pred, gold),
        "ruh_analyzer": "ArabicMorphAnalyzer (rule-based, stdlib-only; not a trained model)",
    }

    if use_camel:
        camel_fn, note = try_camel_analyzer()
        if camel_fn is None:
            report["camel"] = {"status": "skipped", "note": note}
        else:
            camel_pred = [camel_fn(w) for w in words]
            camel_scores = score_predictions(camel_pred, gold)
            camel_scores["status"] = "beta"
            camel_scores["note"] = note
            report["camel"] = camel_scores
    else:
        report["camel"] = {"status": "skipped", "note": "use_camel=False"}
    return report


def print_report(report: dict[str, Any]) -> None:
    """Print a human-readable summary of the eval report."""
    print("== Morphology eval (beta) ==")
    print(f"gold: {report['gold_path']}")
    for side in ("ruh", "camel"):
        leg = report[side]
        if leg.get("status") == "skipped":
            print(f"[{side}] SKIPPED — {leg['note']}")
            continue
        print(
            f"[{side}] n={leg['n_scored']}/{leg['n']} "
            f"root_acc={leg['root_accuracy']:.4f} "
            f"pattern_acc={leg['pattern_accuracy']:.4f} "
            f"exact_acc={leg['exact_accuracy']:.4f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ruh vs CAMeL morphology head-to-head (beta)")
    parser.add_argument("--gold", required=True, help="gold TSV or JSONL path")
    parser.add_argument("--no-camel", action="store_true", help="skip the CAMeL leg")
    parser.add_argument("--out", help="write JSON report to this path")
    args = parser.parse_args(argv)

    report = run_morphology_eval(args.gold, use_camel=not args.no_camel)
    print_report(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
