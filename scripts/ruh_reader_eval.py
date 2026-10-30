"""Measure the Ruh reader against Lughah on held-out seeds, for several seeds.

For each training seed: the reader is trained on the training groups of
Lughah's seeds (``tadbir.ruh_reader.build``), κ, γ and b are fitted on the
development groups, and three arms are read on the held-out groups (never
trained on by either model; Lughah is refitted without them):

- Lughah alone (naive Bayes, ``lughah.naive_posterior`` with the held-out fit),
- the reader alone (``P_R(l | x)``),
- the product of experts (``P_L · P_R^b``).

Printed: held-out bits per byte per language, accuracy (95% Wilson interval)
and log-loss per arm, on whole messages and on their first 2 and 3 words,
on short messages (< 40 bytes), by script (Latin: English and Roman
Hindi/Urdu; Arabic script: Arabic and Urdu), the gate's verdict, and the
latency of reading a 100-byte message on 2 threads in fp32 and int8.

    cd backend && python ../scripts/ruh_reader_eval.py --seeds 0 1 --json out.json
    # --install 0: keep seed 0's reader as the current one in $MIZAN_DATA_DIR
"""

from __future__ import annotations

import argparse
import json
import os
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


def latency(model, languages) -> dict:
    from tadbir.ruh_reader import net

    slots = list(range(len(languages)))
    return {
        "fp32": net.latency(model, slots),
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


def table(results: dict, languages) -> str:
    lines = []
    for seed, found in results.items():
        manifest = found["manifest"]
        lines.append(
            f"\n## seed {seed}: {manifest['parameters']:,} parameters, "
            f"{manifest['training']['steps']} steps, {manifest['training']['seconds']} s, "
            f"{manifest['training']['tokens']:,} tokens, dev bpb {manifest['training']['dev_bpb']}"
        )
        lines.append(f"fit: {json.dumps({k: round(v, 4) for k, v in manifest['fit'].items()})}")
        bpb = manifest["held_out_bpb"]
        lines.append(
            "held-out bits per byte: " + ", ".join(f"{k} {bpb[k]}" for k in languages if k in bpb)
        )
        lines.append(
            "| slice | n | Lughah acc [95%] | loss | reader acc [95%] | loss | combined acc [95%] | loss |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for name, arms in found["slices"].items():
            cells = []
            for arm in ("lughah", "reader", "combined"):
                m = arms[arm]
                cells += [
                    f"{m['accuracy']:.4f} [{m['wilson'][0]:.4f}, {m['wilson'][1]:.4f}]",
                    f"{m['log_loss']:.4f}",
                ]
            lines.append(f"| {name} | {arms['lughah']['n']} | " + " | ".join(cells) + " |")
        gate = manifest["gate"]
        lines.append(
            f"gate: adopted={manifest['adopted']} wins={gate['wins']} losses={gate['losses']} "
            f"e={gate['e_value']} (needed {gate['needed']}) P(not better)={gate['p_not_better']} "
            f"loss {gate['log_loss_before']} -> {gate['log_loss_after']}"
        )
        if "latency" in found:
            lines.append(
                f"latency (100 bytes, every language, 2 threads): {json.dumps(found['latency'])}"
            )
        if "int8" in found:
            lines.append(f"int8 on held-out: {json.dumps(found['int8'])}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--config", default="{}", help="JSON overrides of ruh_reader.CONFIG")
    parser.add_argument("--plan", default="{}", help="JSON overrides of ruh_reader.PLAN")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--json", type=Path, help="write every number here")
    parser.add_argument("--install", type=int, help="keep this seed's reader as the current one")
    parser.add_argument("--save", type=Path, help="keep every seed's reader (weights) here")
    args = parser.parse_args()
    os.environ.setdefault("MIZAN_TALIM", "off")  # the shipped seeds only

    from tadbir import ruh_reader

    results: dict = {}
    for seed in args.seeds:
        began = time.monotonic()
        built = ruh_reader.build(
            seed,
            config=json.loads(args.config),
            plan=json.loads(args.plan),
            threads=args.threads,
            log=lambda line: print(line, flush=True),
        )
        languages = built.manifest["languages"]
        fit = ruh_reader.Fit(**built.manifest["fit"])
        found = {
            "manifest": built.manifest,
            "slices": slices(built.held_out, fit, languages),
            "latency": latency(built.model, languages),
            "int8": int8_agreement(built.model, built.held_out, fit, languages),
            "wall_seconds": round(time.monotonic() - began, 1),
        }
        results[seed] = found
        print(table({seed: found}, languages), flush=True)
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
