"""Measure the Ruh reader against Lughah on held-out seeds, for several seeds.

For each training seed: the reader is trained on the training groups of
Lughah's seeds (``tadbir.ruh_reader.build``; with ``--corpus``, also on the
reader's own corpus, ``tadbir.ruh_reader.corpus``), κ, γ and b are fitted on
the development groups, and three arms are read on the held-out groups (never
trained on by either model; Lughah is refitted without them):

- Lughah alone (naive Bayes, ``lughah.naive_posterior`` with the held-out fit),
- the reader alone (``P_R(l | x)``),
- the product of experts (``P_L · P_R^b``).

Printed: held-out bits per byte per language, accuracy (95% Wilson interval)
and log-loss per arm, on whole messages and on their first 2 and 3 words,
on short messages (< 40 bytes), by script (Latin: English and Roman
Hindi/Urdu; Arabic script: Arabic and Urdu), the gate's verdict, and the
latency of reading a 100-byte message on 2 threads in fp32 and int8.

With ``--corpus`` the corpus's held-out short messages (MASSIVE test
utterances of 3 to 8 words in en, hi, ur, ar, and held-out Roman Hindi/Urdu
rows) are a further slice, overall and per language, with two more arms:
the shipped Lughah (fitted on every seed; it never saw these messages either)
and the shipped Lughah times the reader. The same paired test the gate uses
is run on them and reported; it never decides.

With ``--validation`` (and ``--corpus``; v1.1): the corpus's validation
slices (``corpus.build_validation``: MASSIVE's ``dev`` partition and fresh
Roman Hindi/Urdu rows, split in halves by SHA-256) are read too; κ and b are
calibrated on the calibration half (γ and ñ held at the development fit) and
the gate is run on the gate half as the ``--test``-th test of this reader
(default: its tests + 1). Every other slice is reported under that fit.

With ``--fresh`` too (test 3): the calibration half's Roman rows count only
where Qamus reads a Hindi or Urdu word in them (``corpus.roman_words``), and
the gate is run on the fresh slices instead (``corpus.build_fresh``: CLINC150
English requests and never-read Roman rows the rule holds, none seen or near
a seen text); v1.1's calibration, the rows the rule left out and v1.1's gate
half are reported under it.

``--evaluate DIR`` reads an existing reader (``current.pt`` and
``current.json`` in DIR, with the fit it was installed with) on the same
slices, without training: the reader trained on the seeds alone, measured on
the new slice.

    cd backend && python ../scripts/ruh_reader_eval.py --seeds 0 1 --json out.json
    # --corpus: train on the reader's corpus too ($MIZAN_DATA_DIR/corpora/ruh_reader)
    # --install 0: keep seed 0's reader as the current one in $MIZAN_DATA_DIR
    # --save DIR: each seed's weights are written to DIR as soon as it is trained
    #   (reader-seedN.trained.pt, then the marker seedN.trained), before it is read;
    #   the same command run again after a stop finds them and only reads
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

SHORT = 40  # bytes: the short-message slice


def _metrics(reads, rows) -> dict:
    from core.adaptive import wilson_bounds
    from tadbir import ruh_reader

    truths = [read.truth for read in reads]
    right = sum(1 for row, t in zip(rows, truths, strict=True) if ruh_reader._argmax(row) == t)
    low, high = wilson_bounds(right, len(truths))
    return {
        "n": len(truths),
        "accuracy": round(right / max(1, len(truths)), 4),
        "wilson": [round(low, 4), round(high, 4)],
        "log_loss": round(ruh_reader.log_loss(rows, truths), 4),
    }


def slices(reads, fit, languages) -> dict:
    from tadbir import ruh_reader

    chosen = {
        "all": lambda r: True,
        "whole": lambda r: r.kind == "whole",
        "first 3 words": lambda r: r.kind == "3w",
        "first 2 words": lambda r: r.kind == "2w",
        f"< {SHORT} bytes": lambda r: len(r.text.encode("utf-8")) < SHORT,
        "Latin script (en, hi-latn)": lambda r: languages[r.truth] in {"en", "hi-latn"},
        "en": lambda r: languages[r.truth] == "en",
        "hi-latn": lambda r: languages[r.truth] == "hi-latn",
        f"hi-latn < {SHORT} bytes": lambda r: (
            languages[r.truth] == "hi-latn" and len(r.text.encode("utf-8")) < SHORT
        ),
        "Arabic script (ar, ur)": lambda r: languages[r.truth] in {"ar", "ur"},
        "ur": lambda r: languages[r.truth] == "ur",
    }
    found = {}
    for name, keep in chosen.items():
        picked = [read for read in reads if keep(read)]
        if not picked:
            continue
        found[name] = {
            arm: _metrics(picked, rows) for arm, rows in ruh_reader.arms(picked, fit).items()
        }
    return found


def shipped_arms(reads, fit, languages) -> dict[str, list[list[float]]]:
    """Lughah as it ships (fitted on every seed) and its product with the reader."""
    import math

    from tadbir import lughah, ruh_reader

    shipped = []
    for read in reads:
        posterior = lughah.naive_posterior(read.text)
        shipped.append([math.log(max(posterior.get(code, 0.0), 1e-300)) for code in languages])
    return {
        "lughah (shipped)": shipped,
        "shipped × reader": [
            ruh_reader.combined_log_posterior(row, read.reader(fit), fit.b)
            for row, read in zip(shipped, reads, strict=True)
        ],
    }


def short_slices(reads, fit, languages, everything: str = "all short") -> dict:
    """The held-out short messages: overall, per language, MASSIVE and Roman."""
    from tadbir import ruh_reader

    chosen = {
        everything: lambda r: True,
        "MASSIVE (en, hi, ur, ar)": lambda r: r.group.startswith("massive:"),
        **{code: (lambda r, code=code: languages[r.truth] == code) for code in languages},
    }
    shipped = shipped_arms(reads, fit, languages)
    found = {}
    for name, keep in chosen.items():
        index = [i for i, read in enumerate(reads) if keep(read)]
        if not index:
            continue
        picked = [reads[i] for i in index]
        rows = ruh_reader.arms(picked, fit)
        rows.update({arm: [values[i] for i in index] for arm, values in shipped.items()})
        found[name] = {arm: _metrics(picked, values) for arm, values in rows.items()}
    return found


def short_check(reads, fit, languages, test: int = 1) -> dict:
    """The gate's paired test on the short slice, against the held-out Lughah
    and against the shipped one (reported; the gate is the seeds')."""
    from tadbir import ruh_reader

    truths = [r.truth for r in reads]
    groups = [r.group for r in reads]
    rows = ruh_reader.arms(reads, fit)
    shipped = shipped_arms(reads, fit, languages)
    return {
        "held-out Lughah": ruh_reader.gate(truths, groups, rows["lughah"], rows["combined"], test),
        "shipped Lughah": ruh_reader.gate(
            truths, groups, shipped["lughah (shipped)"], shipped["shipped × reader"], test
        ),
    }


def validation_reads(built, rows, languages) -> dict:
    """The validation halves read by the held-out Lughah and scored by the reader."""
    from tadbir import ruh_reader

    halves = {}
    for name in ("calibration", "gate"):
        chosen = [row for row in rows if row[3] == name and row[1] in languages]
        reads = ruh_reader.read_with_lughah(
            [(text, label) for text, label, _group, _half in chosen], languages, built.lughah, ()
        )
        for read, (_text, _label, group, _half) in zip(reads, chosen, strict=True):
            read.group = group  # a MASSIVE request in every language is one group
        halves[name] = reads
    ruh_reader.score_reads(built.model, halves["calibration"] + halves["gate"], languages)
    return halves


def paired(reads, fit, test: int) -> dict:
    """The gate's test of the product against the held-out Lughah on these reads."""
    from tadbir import ruh_reader

    rows = ruh_reader.arms(reads, fit)
    return ruh_reader.gate(
        [r.truth for r in reads], [r.group for r in reads], rows["lughah"], rows["combined"], test
    )


def validate(built, halves, languages, test: int | None = None) -> dict:
    """v1.1: κ and b calibrated on the calibration half (γ and ñ held at the
    development fit), the gate run on the gate half as the ``test``-th test of
    this reader (by default the manifest's tests + 1, as a night counts), and
    every other slice reported under the calibrated fit, never deciding."""
    from collections import Counter

    from tadbir import ruh_reader

    before = ruh_reader.Fit(**built.manifest["fit"])
    fit = ruh_reader.fit_on(halves["calibration"], before.ref, gamma=before.gamma)
    k = test if test is not None else int(built.manifest.get("tests") or 1) + 1
    gated = halves["gate"]
    verdict = paired(gated, fit, k)
    parts = {
        "MASSIVE (en, hi, ur, ar)": [r for r in gated if r.group.startswith("massive:")],
        "English, not MASSIVE": [
            r for r in gated if languages[r.truth] == "en" and not r.group.startswith("massive:")
        ],
        "Roman Hindi/Urdu": [r for r in gated if languages[r.truth] == "hi-latn"],
    }
    return {
        "name": "v1.1: calibrated on the calibration half, gated on the gate half",
        "test": k,
        "development_fit": before.to_dict(),
        "fit": fit.to_dict(),
        "sizes": {
            name: dict(Counter(languages[r.truth] for r in reads)) for name, reads in halves.items()
        },
        "groups": {name: len({r.group for r in reads}) for name, reads in halves.items()},
        "gate": verdict,
        "adopted": verdict["adopted"] and fit.b > 0,
        "gate_slices": short_slices(gated, fit, languages, "gate half"),
        "gate_parts": {name: paired(reads, fit, k) for name, reads in parts.items() if reads},
        "gate_shipped": short_check(gated, fit, languages, k)["shipped Lughah"],
        "gate_errors": errors(gated, fit, languages),
        "gate_bpb": ruh_reader.bits_per_byte(gated, languages),
        "gate_development_fit": {
            "slices": short_slices(gated, before, languages, "gate half"),
            "check": paired(gated, before, k),
        },
        "calibration_slices": short_slices(
            halves["calibration"], fit, languages, "calibration half (in sample)"
        ),
        "held_out_seeds": {
            "slices": slices(built.held_out, fit, languages),
            "check": paired(built.held_out, fit, k),
        },
        "short_v1": {
            "slices": short_slices(built.short, fit, languages),
            "check": short_check(built.short, fit, languages, k),
            "errors": errors(built.short, fit, languages),
        },
    }


def fresh_reads(built, rows, languages) -> dict:
    """Test 3's fresh slices by part (``gate``, ``rule``), read by the held-out
    Lughah and scored by the reader."""
    from tadbir import ruh_reader

    found = {}
    for name in ("gate", "rule"):
        chosen = [row for row in rows if row[3] == name and row[1] in languages]
        reads = ruh_reader.read_with_lughah(
            [(text, label) for text, label, _group, _part in chosen], languages, built.lughah, ()
        )
        for read, (_text, _label, group, _part) in zip(reads, chosen, strict=True):
            read.group = group
        found[name] = reads
    ruh_reader.score_reads(built.model, found["gate"] + found["rule"], languages)
    return found


def test3(built, halves, fresh, languages, test: int | None = None) -> dict:
    """Test 3: κ and b calibrated on v1.1's calibration half with its Roman
    rows kept only where Qamus reads a Hindi or Urdu word (``roman_words``),
    the gate run on the fresh slice (CLINC150 English and never-read Roman
    rows the rule holds) as the ``test``-th test; v1.1's calibration (no
    rule), the Roman rows the rule left out and v1.1's gate half reported."""
    from tadbir import ruh_reader
    from tadbir.ruh_reader import corpus

    roman = languages.index("hi-latn")
    calibration = [
        r for r in halves["calibration"] if r.truth != roman or corpus.roman_words(r.text)
    ]
    found = validate(built, {"calibration": calibration, "gate": fresh["gate"]}, languages, test)
    found["name"] = "test 3: calibrated with the Roman rule, gated on fresh messages"
    found["calibration_left_out_by_rule"] = len(halves["calibration"]) - len(calibration)
    k = found["test"]
    fit = ruh_reader.Fit(**found["fit"])
    before = ruh_reader.Fit(**built.manifest["fit"])
    unfiltered = ruh_reader.fit_on(halves["calibration"], before.ref, gamma=before.gamma)
    found["gate_v11_fit"] = {
        "fit": unfiltered.to_dict(),
        "slices": short_slices(fresh["gate"], unfiltered, languages, "gate slice"),
        "check": paired(fresh["gate"], unfiltered, k),
    }
    if fresh["rule"]:
        found["left_out_by_rule"] = {
            "slices": short_slices(fresh["rule"], fit, languages, "left out by the rule"),
            "errors": errors(fresh["rule"], fit, languages),
        }
    found["v11_gate_half"] = {
        "slices": short_slices(halves["gate"], fit, languages, "v1.1 gate half"),
        "check": paired(halves["gate"], fit, k),
    }
    return found


def latency(model, languages) -> dict:
    from tadbir.ruh_reader import net

    slots = list(range(len(languages)))
    return {
        "fp32": net.latency(model, slots),
        "fp32 (24 bytes)": net.latency(model, slots, size=24),
        "int8": net.latency(net.quantized(model), slots),
    }


def int8_agreement(model, reads, fit, languages) -> dict:
    """The held-out arms again with the int8 model."""
    import copy

    from tadbir import ruh_reader
    from tadbir.ruh_reader import net

    copied = copy.deepcopy(reads)
    ruh_reader.score_reads(net.quantized(model), copied, languages)
    same = sum(
        1
        for a, b in zip(reads, copied, strict=True)
        if ruh_reader._argmax(a.reader(fit)) == ruh_reader._argmax(b.reader(fit))
    )
    return {
        "reader_decisions_same": round(same / max(1, len(reads)), 4),
        "reader": _metrics(copied, [r.reader(fit) for r in copied]),
        "combined": _metrics(copied, [r.combined(fit) for r in copied]),
    }


def _table(rows: dict, arms_shown) -> list[str]:
    lines = ["| slice | n | " + " | ".join(f"{arm} acc [95%] | loss" for arm in arms_shown) + " |"]
    lines.append("|---|---|" + "---|---|" * len(arms_shown))
    for name, arms in rows.items():
        cells = []
        for arm in arms_shown:
            m = arms[arm]
            cells += [
                f"{m['accuracy']:.4f} [{m['wilson'][0]:.4f}, {m['wilson'][1]:.4f}]",
                f"{m['log_loss']:.4f}",
            ]
        lines.append(f"| {name} | {arms['lughah']['n']} | " + " | ".join(cells) + " |")
    return lines


def table(results: dict, languages) -> str:
    lines = []
    for seed, found in results.items():
        manifest = found["manifest"]
        training = manifest.get("training") or {}
        lines.append(
            f"\n## {seed}: {manifest['parameters']:,} parameters, "
            f"{training.get('steps')} steps, {training.get('seconds')} s, "
            f"{training.get('tokens') or 0:,} tokens, dev bpb {training.get('dev_bpb')}"
        )
        if manifest.get("corpus"):
            extra = manifest["corpus"]
            lines.append(
                f"corpus: {extra['lines']:,} lines, {extra['bytes']:,} bytes "
                f"{json.dumps(extra['per_language'])}; scripture set aside "
                f"{extra['scripture_set_aside']}, held-out duplicates {extra['held_out_dropped']}"
            )
        lines.append(f"fit: {json.dumps({k: round(v, 4) for k, v in manifest['fit'].items()})}")
        bpb = manifest["held_out_bpb"]
        lines.append(
            "held-out bits per byte: " + ", ".join(f"{k} {bpb[k]}" for k in languages if k in bpb)
        )
        lines += _table(found["slices"], ("lughah", "reader", "combined"))
        gate = manifest["gate"]
        lines.append(
            f"gate: adopted={manifest['adopted']} wins={gate['wins']} losses={gate['losses']} "
            f"e={gate['e_value']} (needed {gate['needed']}) P(not better)={gate['p_not_better']} "
            f"loss {gate['log_loss_before']} -> {gate['log_loss_after']}"
        )
        for arm, counted in (found.get("errors") or {}).items():
            lines.append(f"mistakes on held-out, {arm}: {json.dumps(counted)}")
        if found.get("short"):
            short_bpb = found.get("short_bpb") or {}
            lines.append(
                "\nheld-out short messages, bits per byte: "
                + ", ".join(f"{k} {short_bpb[k]}" for k in languages if k in short_bpb)
            )
            lines += _table(
                found["short"],
                ("lughah", "reader", "combined", "lughah (shipped)", "shipped × reader"),
            )
            for name, check in found["short_check"].items():
                lines.append(
                    f"paired test on short ({name}, reported only): wins={check['wins']} "
                    f"losses={check['losses']} e={check['e_value']} "
                    f"P(not better)={check['p_not_better']} "
                    f"loss {check['log_loss_before']} -> {check['log_loss_after']}"
                )
            for arm, counted in (found.get("short_errors") or {}).items():
                lines.append(f"mistakes on short, {arm}: {json.dumps(counted)}")
        if found.get("validation"):
            lines += validation_table(found["validation"])
        if "latency" in found:
            lines.append(f"latency (every language, 2 threads): {json.dumps(found['latency'])}")
        if "int8" in found:
            lines.append(f"int8 on held-out: {json.dumps(found['int8'])}")
        if "peak_rss_mb" in found:
            lines.append(f"peak RSS of this process: {found['peak_rss_mb']} MB")
    return "\n".join(lines)


def _check_line(name: str, check: dict) -> str:
    return (
        f"{name}: adopted={check['adopted']} wins={check['wins']} losses={check['losses']} "
        f"e={check['e_value']} (needed {check['needed']}) P(not better)={check['p_not_better']} "
        f"loss {check['log_loss_before']} -> {check['log_loss_after']} "
        f"acc {check['accuracy_before']} -> {check['accuracy_after']} "
        f"(n {check['n']}, {check['groups']} groups)"
    )


def validation_table(found: dict) -> list[str]:
    shown = ("lughah", "reader", "combined", "lughah (shipped)", "shipped × reader")
    lines = [
        f"\n### {found.get('name', 'v1.1')} (test {found['test']})",
        f"sizes: {json.dumps(found['sizes'])}; groups {json.dumps(found['groups'])}",
        "development fit: "
        + json.dumps({k: round(v, 4) for k, v in found["development_fit"].items()}),
        "calibrated fit: " + json.dumps({k: round(v, 4) for k, v in found["fit"].items()}),
        _check_line("GATE", found["gate"]) + f"; b > 0: {found['fit']['b'] > 0}",
        f"adopted: {found['adopted']}",
    ]
    lines += _table(found["gate_slices"], shown)
    for name, check in found["gate_parts"].items():
        lines.append(_check_line(f"gate half, {name} (reported)", check))
    lines.append(_check_line("gate half, shipped Lughah (reported)", found["gate_shipped"]))
    lines.append(f"gate half bits per byte: {json.dumps(found['gate_bpb'])}")
    for arm, counted in found["gate_errors"].items():
        lines.append(f"mistakes on the gate half, {arm}: {json.dumps(counted)}")
    lines.append("\ngate half under the development fit (reported):")
    lines += _table(found["gate_development_fit"]["slices"], shown)
    lines.append(
        _check_line("development fit on the gate half", found["gate_development_fit"]["check"])
    )
    lines.append("\ncalibration half (in sample):")
    lines += _table(found["calibration_slices"], shown)
    lines.append("\nseeds' held-out groups under the calibrated fit (reported):")
    lines += _table(found["held_out_seeds"]["slices"], ("lughah", "reader", "combined"))
    lines.append(_check_line("seeds' held-out groups", found["held_out_seeds"]["check"]))
    lines.append("\nv1's short messages under the calibrated fit (reported):")
    lines += _table(found["short_v1"]["slices"], shown)
    for name, check in found["short_v1"]["check"].items():
        lines.append(_check_line(f"v1 short, {name}", check))
    for arm, counted in found["short_v1"]["errors"].items():
        lines.append(f"mistakes on v1 short, {arm}: {json.dumps(counted)}")
    if "gate_v11_fit" in found:  # test 3
        extra = found["gate_v11_fit"]
        lines.append(
            "\ngate slice under v1.1's calibration (no rule), fit "
            + json.dumps({k: round(v, 4) for k, v in extra["fit"].items()})
        )
        lines += _table(extra["slices"], shown)
        lines.append(_check_line("v1.1's calibration on the gate slice", extra["check"]))
        lines.append(
            f"calibration rows left out by the rule: {found['calibration_left_out_by_rule']}"
        )
        if "left_out_by_rule" in found:
            lines.append("\nRoman rows the rule left out (reported):")
            lines += _table(found["left_out_by_rule"]["slices"], shown)
            for arm, counted in found["left_out_by_rule"]["errors"].items():
                lines.append(f"mistakes on rows the rule left out, {arm}: {json.dumps(counted)}")
        lines.append("\nv1.1's gate half under the new fit (reported):")
        lines += _table(found["v11_gate_half"]["slices"], shown)
        lines.append(_check_line("v1.1's gate half", found["v11_gate_half"]["check"]))
    return lines


def measure_short(found: dict, short, fit, languages) -> None:
    from tadbir import ruh_reader

    if not short:
        return
    found["short"] = short_slices(short, fit, languages)
    found["short_bpb"] = ruh_reader.bits_per_byte(short, languages)
    found["short_check"] = short_check(short, fit, languages)
    found["short_errors"] = errors(short, fit, languages)


def errors(reads, fit, languages, shipped: bool = True) -> dict:
    """Each arm's mistakes as 'truth -> read' counts (with ``shipped``, also the
    shipped Lughah's arms: only for messages it never saw)."""
    from collections import Counter

    from tadbir import ruh_reader

    rows = ruh_reader.arms(reads, fit)
    if shipped:
        rows.update(shipped_arms(reads, fit, languages))
    found = {}
    for arm, values in rows.items():
        counted = Counter(
            f"{languages[read.truth]} -> {languages[ruh_reader._argmax(row)]}"
            for read, row in zip(reads, values, strict=True)
            if ruh_reader._argmax(row) != read.truth
        )
        found[arm] = dict(counted.most_common())
    return found


def evaluate(folder: Path, extra) -> dict:
    """An installed reader (its weights and fit) on the held-out slices."""
    from tadbir import ruh_reader
    from tadbir.ruh_reader import net

    manifest = json.loads((folder / "current.json").read_text(encoding="utf-8"))
    model = net.load(folder / "current.pt")
    languages = list(manifest["languages"])
    rows = ruh_reader.seeds()
    if manifest.get("corpus_sha256") != ruh_reader.corpus_digest(rows):
        raise SystemExit("this reader was trained on other seeds")
    fold = ruh_reader.held_out_lughah(rows)
    held_rows = [row for row in rows if ruh_reader.part(ruh_reader.group_of(row[0])) == "held_out"]
    held = ruh_reader.read_with_lughah(held_rows, languages, fold)
    short = []
    if extra is not None:
        chosen = [item for item in extra.short if item[1] in languages]
        short = ruh_reader.read_with_lughah(
            [(t, lab) for t, lab, _g in chosen], languages, fold, ()
        )
        for read, (_t, _l, group) in zip(short, chosen, strict=True):
            read.group = group
    ruh_reader.score_reads(model, held + short, languages)
    fit = ruh_reader.Fit(**manifest["fit"])
    found = {
        "manifest": manifest,
        "slices": slices(held, fit, languages),
        "held_out_bpb": ruh_reader.bits_per_byte(held, languages),
        "errors": errors(held, fit, languages, shipped=False),
    }
    measure_short(found, short, fit, languages)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--config", default="{}", help="JSON overrides of ruh_reader.CONFIG")
    parser.add_argument("--plan", default="{}", help="JSON overrides of ruh_reader.PLAN")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--corpus", nargs="?", const="", default=None, help="train on the corpus")
    parser.add_argument("--evaluate", type=Path, help="measure an installed reader, no training")
    parser.add_argument("--json", type=Path, help="write every number here")
    parser.add_argument("--install", type=int, help="keep this seed's reader as the current one")
    parser.add_argument(
        "--save",
        type=Path,
        help="keep every seed's reader (weights) here, the moment it is trained; "
        "a re-run finds them and only reads",
    )
    parser.add_argument(
        "--validation",
        action="store_true",
        help="v1.1: calibrate κ and b on the calibration half of the corpus's validation "
        "slices and gate on the gate half (needs --corpus)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="test 3: calibrate on the calibration half with the Roman rule and gate on the "
        "fresh slices (needs --corpus and --validation)",
    )
    parser.add_argument(
        "--test", type=int, help="the k-th test of this reader (default: its tests + 1)"
    )
    args = parser.parse_args()
    os.environ.setdefault("MIZAN_TALIM", "off")  # the shipped seeds only

    from tadbir import ruh_reader
    from tadbir.ruh_reader import corpus as reader_corpus

    extra = None
    held_back = None
    if args.corpus is not None:
        extra = reader_corpus.load(Path(args.corpus) if args.corpus else None)
        if extra is None:
            raise SystemExit("no corpus: build it with python -m tadbir.ruh_reader --corpus")
    if args.validation:
        held_back = reader_corpus.load_validation(Path(args.corpus) if args.corpus else None)
        if extra is None or held_back is None:
            raise SystemExit(
                "no validation slices: build them with python -m tadbir.ruh_reader --validation"
            )
    fresh_rows = None
    if args.fresh:
        fresh_rows = reader_corpus.load_fresh(Path(args.corpus) if args.corpus else None)
        if held_back is None or fresh_rows is None:
            raise SystemExit(
                "no fresh slices: build them with python -m tadbir.ruh_reader --fresh "
                "(and run with --validation)"
            )
    if args.evaluate:
        found = evaluate(args.evaluate, extra)
        found["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
        print(table({str(args.evaluate): found}, found["manifest"]["languages"]), flush=True)
        if args.json:
            args.json.write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")
        return
    results: dict = {}
    for seed in args.seeds:
        began = time.monotonic()
        built = ruh_reader.build(
            seed,
            config=json.loads(args.config),
            plan=json.loads(args.plan),
            corpus=extra,
            threads=args.threads,
            log=lambda line: print(line, flush=True),
            trained=args.save,  # weights kept the moment training ends; found again on a re-run
        )
        languages = built.manifest["languages"]
        fit = ruh_reader.Fit(**built.manifest["fit"])
        found = {
            "manifest": built.manifest,
            "slices": slices(built.held_out, fit, languages),
            "errors": errors(built.held_out, fit, languages, shipped=False),
        }
        measure_short(found, built.short, fit, languages)
        if held_back is not None:
            halves = validation_reads(built, held_back, languages)
            if fresh_rows is not None:
                fresh = fresh_reads(built, fresh_rows, languages)
                found["validation"] = test3(built, halves, fresh, languages, args.test)
            else:
                found["validation"] = validate(built, halves, languages, args.test)
        found["latency"] = latency(built.model, languages)
        found["int8"] = int8_agreement(built.model, built.held_out, fit, languages)
        found["wall_seconds"] = round(time.monotonic() - began, 1)
        found["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
        results[f"seed {seed}"] = found
        print(table({f"seed {seed}": found}, languages), flush=True)
        if args.save:
            from tadbir.ruh_reader import net

            net.save(built.model, args.save / f"reader-seed{seed}.pt")
        if args.json:  # written after every seed, so a stopped run keeps what it measured
            args.json.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
        if args.install == seed:
            ruh_reader.install(built)
            print(f"installed seed {seed} in {ruh_reader.home()}")


if __name__ == "__main__":
    main()
