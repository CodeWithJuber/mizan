#!/usr/bin/env python3
"""Tadrib's pre-registered measurement for the reader (docs/tadrib.md).

A stream of messages is replayed into the online reader and into the same
reader frozen; each message is scored by both before the online copy may
learn it (prequential: predict, then learn), exactly as in production: a
message is learned only where Lughah and the online reader agree, one in five
is held out, and the dataset's label is used only to score.

  --streams WORK   build WORK/dev.tsv and WORK/test.tsv (source, label, group, text)
  --reads WORK     the seeds' dev and held-out reads (Lughah refitted without them)
  --run WORK       one stream with one setting and seed -> WORK/runs/<name>.json
  --grid WORK      the dev grid (12 settings, in parallel) and the chosen setting
  --test WORK      the test stream with the chosen setting, seeds 0 and 1, judged

Run with MIZAN_DATA_DIR pointing at the data folder the reader was built in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SALT = "tadrib-reader-1"
GRID = [(k, lr, lam) for k in (1, 2) for lr in (1e-4, 3e-4, 1e-3) for lam in (0.0, 1.0)]
# The second test (docs/tadrib.md, "v2"): one step, smaller anchors, more seed replay.
GRID_V2 = [
    {"steps": 1, "lr": lr, "anchor": lam, "seeds": seeds}
    for lr in (1e-4, 3e-4)
    for lam in (0.03, 0.1, 0.3, 1.0)
    for seeds in (4, 8)
]
PER_LANGUAGE = {"dev": 300, "test": 800}
MORE_THAN = 8  # words: the gates' short slices took 3 to 8
PER_DOCUMENT = 3  # lines a never-read FineWeb-2 document gives at most
ERASE = 10  # one learned lesson in ten is erased for the exactness check
ALPHA = 0.05


def _order(key: str, purpose: str = "order") -> str:
    return hashlib.sha256(f"{SALT}:{purpose}:{key}".encode()).hexdigest()


def _stream(key: str) -> str:
    return "dev" if int(_order(key, "stream")[:16], 16) % 2 == 0 else "test"


def _rss_mb() -> float:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


# ── the streams ──────────────────────────────────────────────────────────


def build_streams(work: Path, old: Path, v2: Path, clinc_path: Path) -> dict:
    """dev.tsv and test.tsv as fixed in docs/tadrib.md."""
    from tadbir import lughah
    from tadbir.ruh_reader import corpus as C

    v1 = C.load(old)
    v2_corpus = C.load(v2)
    if v1 is None or v2_corpus is None:
        raise SystemExit("the v1 and v2 corpora are needed to know what was seen")
    seen_texts = [text for text, _label in lughah.corpus()]
    seen_texts += [text for text, _label in [*v1.train, *v1.written]]
    seen_texts += [text for text, _label in [*v2_corpus.train, *v2_corpus.written]]
    seen_texts += C._last_columns(old, C.OLD_SLICES)
    seen_texts += C._last_columns(v2, C.V2_SLICES)
    seen = {C._group(text) for text in seen_texts}
    near = C.Near(seen_texts, words=(3, 64))
    print(f"seen: {len(seen):,} texts' words", flush=True)
    rows: dict[str, list[tuple[str, str, str, str]]] = {"dev": [], "test": []}
    counts: dict[str, int] = {}

    def keep(stream: str, source: str, label: str, group: str, text: str, check: bool) -> None:
        if not C.own_script(text, label):
            counts["script"] = counts.get("script", 0) + 1
            return
        if check and (C._group(text) in seen or text in near):
            counts["seen or near"] = counts.get("seen or near", 0) + 1
            return
        rows[stream].append((source, label, group, text))

    # dev: MASSIVE dev rows of the calibration half (v1.1 fitted κ and b on them)
    for line in (old / "validation.tsv").read_text(encoding="utf-8").splitlines():
        source, label, group, half, text = line.split("\t", 4)
        if source.startswith("massive:") and half == "calibration":
            keep("dev", source, label, group, text, check=False)
    # test: MASSIVE test utterances of more than 8 words
    massive_path = (
        old / "sources" / "massive" / C.SOURCES[[s.name for s in C.SOURCES].index("massive")].file
    )
    for line in C.massive(massive_path):
        if line.kind == "test" and len(line.text.split()) > MORE_THAN:
            keep(
                "test",
                line.source,
                line.label,
                "massive:" + line.source.rsplit(":", 1)[1],
                line.text,
                True,
            )
    # test: English queries of more than 8 words (BANKING77, CLINC150)
    for name, split in (("banking77-train", "train"), ("banking77-test", "test")):
        source = C.V2_SOURCES[[s.name for s in C.V2_SOURCES].index(name)]
        for line in C.banking77(v2 / "sources" / name / source.file, split):
            if len(line.text.split()) > MORE_THAN:
                keep("test", line.source, "en", line.source, line.text, True)
    for line in C.clinc(clinc_path):
        if len(line.text.split()) > MORE_THAN:
            keep("test", line.source, "en", line.source, line.text, True)
    # Roman: lines of FineWeb-2 documents no build has read (not held out, outside the training share)
    # Half of each stream's candidates from each subset; twice the cap, so the
    # SHA-256 order (not the file's) picks which are kept.
    roman: dict[str, list[tuple[str, str, str, str]]] = {"dev": [], "test": []}
    for name in C.FINEWEB_LATIN:
        source = C.SOURCES[[s.name for s in C.SOURCES].index(name)]
        path = v2 / "sources" / name / source.file
        target = {stream: len(roman[stream]) + PER_LANGUAGE[stream] for stream in roman}
        for identifier, text in C.parquet_rows(path):
            if all(len(roman[s]) >= target[s] for s in roman):
                break
            key = f"{name}:{identifier}"
            if C.held_document(key) or C._kept(key, C.KEEP[name]):
                continue
            stream = _stream(key)
            if len(roman[stream]) >= target[stream]:
                continue
            for number, piece in enumerate(C.lines_of(text)[:PER_DOCUMENT]):
                piece = C._clean(piece)
                if len(piece.split()) < 3 or not C.roman_words(piece, C.V2_LEAST):
                    continue
                if not C.own_script(piece, "hi-latn") or C._group(piece) in seen or piece in near:
                    continue
                roman[stream].append((f"{key}:{number}", "hi-latn", f"{key}:{number}", piece))
        print(f"{name}: dev {len(roman['dev'])}, test {len(roman['test'])}", flush=True)
    for stream in rows:
        rows[stream] += roman[stream]
    written = {}
    for stream, found in rows.items():
        by_label: dict[str, list[tuple[str, str, str, str]]] = {}
        for row in sorted(found, key=lambda r: _order(r[0])):
            by_label.setdefault(row[1], [])
            if len(by_label[row[1]]) < PER_LANGUAGE[stream]:
                by_label[row[1]].append(row)
        chosen = sorted((r for rs in by_label.values() for r in rs), key=lambda r: _order(r[0]))
        body = "".join("\t".join(row) + "\n" for row in chosen)
        (work / f"{stream}.tsv").write_text(body, encoding="utf-8")
        written[stream] = {
            "n": len(chosen),
            "per_language": {label: len(items) for label, items in sorted(by_label.items())},
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
        }
    report = {"streams": written, "dropped": counts}
    (work / "streams.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def read_stream(work: Path, stream: str) -> list[tuple[str, str, str, str]]:
    rows = []
    for line in (work / f"{stream}.tsv").read_text(encoding="utf-8").splitlines():
        source, label, group, text = line.split("\t", 3)
        rows.append((source, label, group, text))
    return rows


# ── the reader as it was installed ───────────────────────────────────────


def reader_of(weights: Path, report: Path, seed: int):
    """(model, fit, languages) of a v2 reader: its weights and its development fit."""
    from tadbir import ruh_reader
    from tadbir.ruh_reader import net

    manifest = json.loads(report.read_text(encoding="utf-8"))[f"seed {seed}"]["manifest"]
    rows = ruh_reader.seeds()
    if manifest["corpus_sha256"] != ruh_reader.corpus_digest(rows):
        raise SystemExit("the seeds changed since this reader was built")
    model = net.load(weights)
    return model, ruh_reader.Fit(**manifest["fit"]), list(manifest["languages"])


def build_reads(work: Path) -> None:
    """The seeds' dev and held-out reads as the reader's build makes them."""
    from tadbir import ruh_reader as R

    rows = R.seeds()
    languages = list(dict.fromkeys(label for _text, label in rows))
    splits: dict[str, list[tuple[str, str]]] = {"train": [], "dev": [], "held_out": []}
    for row in rows:
        splits[R.part(R.group_of(row[0]))].append(row)
    fold = R.held_out_lughah(rows, True)
    dev = R.read_with_lughah(R.trainable(splits["dev"]), languages, fold)
    held = R.read_with_lughah(splits["held_out"], languages, fold)
    R._write_reads(work / "seed_reads.json", dev, held)


def seed_lines(languages: list[str]) -> list[tuple[str, int]]:
    from tadbir import ruh_reader as R

    rows = R.seeds()
    lines, _ = R.training_lines(
        R.trainable(row for row in rows if R.part(R.group_of(row[0])) == "train"), languages
    )
    return lines


# ── one stream ───────────────────────────────────────────────────────────


def run(
    work: Path,
    stream: str,
    seed: int,
    setting: dict,
    weights: Path,
    report: Path,
    erase: bool = False,
    limit: int = 0,
) -> dict:
    import torch

    from tadbir import lughah, tadrib
    from tadbir import ruh_reader as R
    from tadbir.ruh_reader import net
    from tadbir.tadrib import online as O

    torch.set_num_threads(1)
    slow, fit, languages = reader_of(weights, report, seed)
    slots = list(range(len(languages)))
    slot_of = {code: i for i, code in enumerate(languages)}
    rows = read_stream(work, stream)
    if limit:
        rows = rows[:limit]
    # Warm what every message reads anyway (Lughah, the scripture check, a
    # scoring pass), so the memory counted is the online learner's own.
    lughah.naive_posterior(rows[0][3])
    R.scripture(rows[0][3])
    net.score(slow, [R.reading(lughah.own_words(rows[0][3]))], slots)
    before = _rss_mb()
    learner = O.Online(slow, O.Setting(**setting), seed_lines(languages))
    frozen = learner.slow
    per: list[dict] = []
    timings: list[float] = []
    lessons: list[tuple[str, int, str]] = []
    held_texts: list[tuple[str, int]] = []
    for _source, label, group, text in rows:
        own = R.reading(lughah.own_words(text))
        if not own or label not in slot_of:
            continue
        truth = slot_of[label]
        began = time.perf_counter()
        scored, counts = net.score(frozen, [own], slots)
        reader_frozen = R.reader_log_posterior(scored[0], counts[0], fit.kappa, fit.gamma, fit.ref)
        scored, counts = net.score(learner.fast, [own], slots)
        reader_online = R.reader_log_posterior(scored[0], counts[0], fit.kappa, fit.gamma, fit.ref)
        found = lughah.naive_posterior(text)
        lug = [math.log(max(found.get(code, 0.0), 1e-300)) for code in languages]
        alone = R._argmax(lug)
        agreed = alone if R._argmax(reader_online) == alone else None
        digest = R.text_digest(text)
        held = tadrib.held_out(digest)
        learned = agreed is not None and not held and not R.scripture(text)
        if learned:
            learner.learn(own, agreed, digest)
            learner.serving_copy()  # the swap's cost
            lessons.append((own, agreed, digest))
            timings.append(time.perf_counter() - began)
        elif held and agreed is not None:
            held_texts.append((own, agreed))
        per.append(
            {
                "group": group,
                "label": label,
                "frozen": -reader_frozen[truth],
                "online": -reader_online[truth],
                "product_frozen": -R.combined_log_posterior(lug, reader_frozen, fit.b)[truth],
                "product_online": -R.combined_log_posterior(lug, reader_online, fit.b)[truth],
                "right_frozen": R._argmax(R.combined_log_posterior(lug, reader_frozen, fit.b))
                == truth,
                "right_online": R._argmax(R.combined_log_posterior(lug, reader_online, fit.b))
                == truth,
                "held": held,
                "learned": learned,
                "agreed_right": agreed == truth if agreed is not None else None,
            }
        )
    after = _rss_mb()
    out = summarise(per, timings)
    out.update(
        {
            "stream": stream,
            "seed": seed,
            "setting": setting,
            "lessons": len(lessons),
            "memory_mb": round(after - before, 1),
            "forgetting": forgetting(work, stream, frozen, learner.fast, fit, languages),
            "safety": safety(per),
        }
    )
    if erase:
        out["erasure"] = erasure(learner, lessons, held_texts, frozen, slots)
    return out


def summarise(per: list[dict], timings: list[float]) -> dict:
    from tadbir import ruh_reader as R

    differences = [row["online"] - row["frozen"] for row in per]
    groups = [row["group"] for row in per]
    n = max(1, len(per))
    ordered = sorted(timings)

    def mean(key: str, rows: list[dict] | None = None) -> float:
        rows = per if rows is None else rows
        return round(sum(row[key] for row in rows) / max(1, len(rows)), 6)

    held = [row for row in per if row["held"]]
    by_label: dict[str, dict] = {}
    for label in sorted({row["label"] for row in per}):
        rows = [row for row in per if row["label"] == label]
        by_label[label] = {
            "n": len(rows),
            "frozen": mean("frozen", rows),
            "online": mean("online", rows),
        }
    agreed = [row for row in per if row["agreed_right"] is not None]
    return {
        "n": len(per),
        "log_loss": {"frozen": mean("frozen"), "online": mean("online")},
        "p_not_better": R.p_not_better(differences, groups),
        "held_out": {
            "n": len(held),
            "frozen": mean("frozen", held),
            "online": mean("online", held),
        },
        "product": {
            "log_loss": {"frozen": mean("product_frozen"), "online": mean("product_online")},
            "accuracy": {
                "frozen": round(sum(row["right_frozen"] for row in per) / n, 6),
                "online": round(sum(row["right_online"] for row in per) / n, 6),
            },
        },
        "by_label": by_label,
        "lesson_labels_right": round(
            sum(bool(row["agreed_right"]) for row in agreed) / max(1, len(agreed)), 6
        ),
        "seconds_per_lesson": {
            "n": len(ordered),
            "median": round(ordered[len(ordered) // 2], 4) if ordered else None,
            "p95": round(ordered[int(len(ordered) * 0.95)], 4) if ordered else None,
        },
    }


def forgetting(work: Path, stream: str, frozen, fast, fit, languages) -> dict:
    """The seeds' reads (dev for the dev stream, held-out for the test stream):
    is the online reader at the end ``no_worse`` than the frozen one?"""
    import copy

    from tadbir import ruh_reader as R

    dev, held = R._read_reads(work / "seed_reads.json")
    reads = dev if stream == "dev" else held
    reads = [read for read in reads if read.kind == "whole"] if stream == "dev" else reads
    old = copy.deepcopy(reads)
    new = copy.deepcopy(reads)
    R.score_reads(frozen, old, languages)
    R.score_reads(fast, new, languages)
    truths = [read.truth for read in reads]
    before, after = R.arms(old, fit)["reader"], R.arms(new, fit)["reader"]
    verdict, risk, loss_old, loss_new = R.no_worse(before, after, truths)
    # v2's rule: no evidence that it got worse, in accuracy (Ta'lim's paired
    # bootstrap, as no_worse) or in log-loss (grouped paired bootstrap).
    rises = [-a[t] + b[t] for a, b, t in zip(after, before, truths, strict=True)]
    loss_risk = p_higher(rises, [read.group for read in reads])
    return {
        "reads": "dev" if stream == "dev" else "held_out",
        "n": len(reads),
        "no_worse": verdict,
        "p_worse": risk,
        "p_loss_higher": loss_risk,
        "no_evidence_worse": risk < 0.95 and loss_risk < 0.95,
        "log_loss": {"frozen": round(loss_old, 6), "online": round(loss_new, 6)},
    }


def p_higher(differences: list[float], groups: list[str], resamples: int = 2000) -> float:
    """P(mean difference > 0) under a paired bootstrap of whole groups
    (``ruh_reader.p_not_better`` counts ≥ 0, which an unchanged model meets)."""
    import random

    by_group: dict[str, list[float]] = {}
    for difference, group in zip(differences, groups, strict=True):
        by_group.setdefault(group, []).append(difference)
    sums = [(sum(values), len(values)) for values in by_group.values()]
    if not sums:
        return 0.0
    rng = random.Random(0)
    higher = 0
    for _ in range(resamples):
        total = count = 0.0
        for _ in range(len(sums)):
            value, n = sums[rng.randrange(len(sums))]
            total += value
            count += n
        higher += total / count > 0
    return higher / resamples


def safety(per: list[dict]) -> dict:
    """The live check on held-out lessons: would it have reset the fast copy?"""
    from core.adaptive import paired_e_value

    slow_better = fast_better = 0
    resets = 0
    for row in per:
        if not row["held"] or row["agreed_right"] is None:
            continue
        if row["frozen"] < row["online"]:
            slow_better += 1
        elif row["online"] < row["frozen"]:
            fast_better += 1
        if paired_e_value(slow_better, fast_better) >= 1 / ALPHA:
            resets += 1
            slow_better = fast_better = 0
    return {
        "slow_better": slow_better,
        "fast_better": fast_better,
        "e_value": round(paired_e_value(slow_better, fast_better), 4),
        "would_reset": resets,
    }


def erasure(learner, lessons, held_texts, frozen, slots) -> dict:
    """Bar 4: erase a fixed tenth of the learned lessons and rebuild; the
    rebuilt weights must equal a fresh run over the remaining lessons."""
    import torch

    from tadbir.ruh_reader import net
    from tadbir.tadrib import online as O

    erased = [item for item in lessons if int(_order(item[2], "erase")[:16], 16) % ERASE == 0]
    kept = [item for item in lessons if item not in erased]

    def per_byte(model, items) -> float:
        nats = tokens = 0.0
        for own, slot, *_ in items:
            scored, counts = net.score(model, [own], slots)
            nats -= scored[0][slot]
            tokens += counts[0]
        return nats / max(1.0, tokens)

    before = {
        "erased": per_byte(learner.fast, erased) - per_byte(frozen, erased),
        "never_learned": per_byte(learner.fast, held_texts) - per_byte(frozen, held_texts),
    }
    learner.replay(kept)
    rebuilt = learner.fast
    # A second learner that never saw the erased lessons, sharing nothing with
    # the first but the slow weights and the seed lines.
    other = O.Online.__new__(O.Online)
    other.slow, other.setting, other.seed_lines, other.fisher = (
        learner.slow,
        learner.setting,
        learner.seed_lines,
        learner.fisher,
    )
    other.reset()
    for own, slot, digest in kept:
        other.learn(own, slot, digest)
    same = all(
        torch.equal(a, b)
        for a, b in zip(
            rebuilt.state_dict().values(), other.fast.state_dict().values(), strict=True
        )
    )
    after = {
        "erased": per_byte(rebuilt, erased) - per_byte(frozen, erased),
        "never_learned": per_byte(rebuilt, held_texts) - per_byte(frozen, held_texts),
    }
    return {
        "erased": len(erased),
        "kept": len(kept),
        "bit_for_bit": same,
        "nats_per_byte_vs_frozen": {"before": before, "after": after},
    }


# ── the grid and the test ────────────────────────────────────────────────


def _name(stream: str, seed: int, setting: dict) -> str:
    name = f"{stream}-s{seed}-k{setting['steps']}-lr{setting['lr']:g}-a{setting['anchor']:g}"
    return name + (f"-r{setting['seeds']}" if "seeds" in setting else "")


def launch(
    work: Path, stream: str, seed: int, settings: list[dict], args, erase: bool
) -> list[dict]:
    """Each setting in its own process (1 torch thread), ``args.jobs`` at once."""
    (work / "runs").mkdir(exist_ok=True)
    pending = list(settings)
    running: list[tuple[subprocess.Popen, Path]] = []
    done = []
    while pending or running:
        while pending and len(running) < args.jobs:
            setting = pending.pop(0)
            out = work / "runs" / f"{_name(stream, seed, setting)}.json"
            if out.exists():
                done.append(json.loads(out.read_text()))
                continue
            command = [
                sys.executable,
                "-I",
                __file__,
                "--run",
                str(work),
                "--stream",
                stream,
                "--seed",
                str(seed),
                "--setting",
                json.dumps(setting),
                "--weights",
                args.weights.format(seed=seed),
                "--report",
                args.report.format(seed=seed),
                "--out",
                str(out),
            ] + (["--erase"] if erase else [])
            running.append(
                (subprocess.Popen(command, env={**os.environ, "OMP_NUM_THREADS": "1"}), out)
            )
        time.sleep(5)
        for process, out in list(running):
            if process.poll() is not None:
                running.remove((process, out))
                if process.returncode != 0 or not out.exists():
                    raise SystemExit(f"{out.name} failed ({process.returncode})")
                done.append(json.loads(out.read_text()))
                print(f"done {out.name}", flush=True)
    return done


def grid(work: Path, args) -> dict:
    settings = [{"steps": k, "lr": lr, "anchor": lam} for k, lr, lam in GRID]
    results = launch(work, "dev", 0, settings, args, erase=False)
    table = sorted(
        (
            {
                "setting": r["setting"],
                "log_loss_online": r["log_loss"]["online"],
                "log_loss_frozen": r["log_loss"]["frozen"],
                "no_worse": r["forgetting"]["no_worse"],
                "p95": r["seconds_per_lesson"]["p95"],
            }
            for r in results
        ),
        key=lambda row: row["log_loss_online"],
    )
    qualified = [row for row in table if row["no_worse"] and (row["p95"] or 0) <= 2.0]
    chosen = qualified[0]["setting"] if qualified else None
    found = {"table": table, "chosen": chosen}
    (work / "chosen.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    return found


def grid_v2(work: Path, args) -> dict:
    """The second test's grid: chosen by lowest dev prequential log-loss among
    the settings with no evidence of forgetting on the seeds' dev reads, p95 at
    most 2.0 s per lesson and at most 150 MB added."""
    results = launch(work, "dev", 0, GRID_V2, args, erase=False)
    table = sorted(
        (
            {
                "setting": r["setting"],
                "log_loss_online": r["log_loss"]["online"],
                "log_loss_frozen": r["log_loss"]["frozen"],
                "p_not_better": r["p_not_better"],
                "no_evidence_worse": r["forgetting"]["no_evidence_worse"],
                "seeds_log_loss": r["forgetting"]["log_loss"],
                "p95": r["seconds_per_lesson"]["p95"],
                "memory_mb": r["memory_mb"],
            }
            for r in results
        ),
        key=lambda row: row["log_loss_online"],
    )
    qualified = [
        row
        for row in table
        if row["no_evidence_worse"] and (row["p95"] or 0) <= 2.0 and row["memory_mb"] <= 150
    ]
    found = {"table": table, "chosen": qualified[0]["setting"] if qualified else None}
    (work / "chosen_v2.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    return found


def judge_v2(work: Path, args) -> dict:
    chosen = json.loads((work / "chosen_v2.json").read_text())["chosen"]
    if chosen is None:
        raise SystemExit("no setting qualified on the dev stream: the test stream is not run")
    results = {}
    for seed in (0, 1):
        results[seed] = launch(work, "test", seed, [chosen], args, erase=seed == 0)[0]
    main = results[0]
    bars = {
        "1 it learns": main["log_loss"]["online"] < main["log_loss"]["frozen"]
        and main["p_not_better"] < ALPHA,
        "2 it does not forget": main["forgetting"]["no_evidence_worse"],
        "3 fast enough": (main["seconds_per_lesson"]["p95"] or 0) <= 2.0
        and main["memory_mb"] <= 150,
        "4 forgetting is exact": main["erasure"]["bit_for_bit"],
    }
    verdict = {"chosen": chosen, "bars": bars, "passed": all(bars.values()), "seeds": results}
    (work / "verdict_v2.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    return verdict


def judge(work: Path, args) -> dict:
    chosen = json.loads((work / "chosen.json").read_text())["chosen"]
    if chosen is None:
        raise SystemExit("no setting qualified on the dev stream: the test stream is not run")
    results = {}
    for seed in (0, 1):
        results[seed] = launch(work, "test", seed, [chosen], args, erase=seed == 0)[0]
    main = results[0]
    bars = {
        "1 it learns": main["log_loss"]["online"] < main["log_loss"]["frozen"]
        and main["p_not_better"] < ALPHA,
        "2 it does not forget": main["forgetting"]["no_worse"],
        "3 fast enough": (main["seconds_per_lesson"]["p95"] or 0) <= 2.0
        and main["memory_mb"] <= 150,
        "4 forgetting is exact": main["erasure"]["bit_for_bit"],
    }
    verdict = {"chosen": chosen, "bars": bars, "passed": all(bars.values()), "seeds": results}
    (work / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--streams", type=Path)
    parser.add_argument("--old", type=Path, help="v1's corpus folder (validation.tsv, MASSIVE)")
    parser.add_argument("--v2", type=Path, help="v2's corpus folder (BANKING77, FineWeb-2)")
    parser.add_argument("--clinc", type=Path)
    parser.add_argument("--reads", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--grid", type=Path)
    parser.add_argument("--test", type=Path)
    parser.add_argument("--grid-v2", type=Path, dest="grid_v2")
    parser.add_argument("--test-v2", type=Path, dest="test_v2")
    parser.add_argument("--stream", default="dev")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--setting", default="{}")
    parser.add_argument("--weights", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--erase", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    if args.streams:
        print(json.dumps(build_streams(args.streams, args.old, args.v2, args.clinc), indent=1))
    elif args.reads:
        build_reads(args.reads)
    elif args.run:
        found = run(
            args.run,
            args.stream,
            args.seed,
            json.loads(args.setting),
            Path(args.weights),
            Path(args.report),
            args.erase,
            args.limit,
        )
        text = json.dumps(found, indent=1)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text)
    elif args.grid:
        print(json.dumps(grid(args.grid, args), indent=1))
    elif args.test:
        print(json.dumps(judge(args.test, args), indent=1))
    elif args.grid_v2:
        print(json.dumps(grid_v2(args.grid_v2, args), indent=1))
    elif args.test_v2:
        print(json.dumps(judge_v2(args.test_v2, args), indent=1))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
