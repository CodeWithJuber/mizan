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


def short_slices(reads, fit, languages) -> dict:
    """The held-out short messages: overall, per language, MASSIVE and Roman."""
    from tadbir import ruh_reader

    chosen = {
        "all short": lambda r: True,
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


def short_check(reads, fit, languages) -> dict:
    """The gate's paired test on the short slice, against the held-out Lughah
    and against the shipped one (reported; the gate is the seeds')."""
    from tadbir import ruh_reader

    truths = [r.truth for r in reads]
    groups = [r.group for r in reads]
    rows = ruh_reader.arms(reads, fit)
    shipped = shipped_arms(reads, fit, languages)
    return {
        "held-out Lughah": ruh_reader.gate(truths, groups, rows["lughah"], rows["combined"]),
        "shipped Lughah": ruh_reader.gate(
            truths, groups, shipped["lughah (shipped)"], shipped["shipped × reader"]
        ),
    }


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
        if "latency" in found:
            lines.append(f"latency (every language, 2 threads): {json.dumps(found['latency'])}")
        if "int8" in found:
            lines.append(f"int8 on held-out: {json.dumps(found['int8'])}")
        if "peak_rss_mb" in found:
            lines.append(f"peak RSS of this process: {found['peak_rss_mb']} MB")
    return "\n".join(lines)


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
    args = parser.parse_args()
    os.environ.setdefault("MIZAN_TALIM", "off")  # the shipped seeds only

    from tadbir import ruh_reader
    from tadbir.ruh_reader import corpus as reader_corpus

    extra = None
    if args.corpus is not None:
        extra = reader_corpus.load(Path(args.corpus) if args.corpus else None)
        if extra is None:
            raise SystemExit("no corpus: build it with python -m tadbir.ruh_reader --corpus")
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
