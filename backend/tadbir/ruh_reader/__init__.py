"""Ruh reader (قارئ): MIZAN's own small language model, a second opinion on
which language a message is written in, trusted only once it is measured.

"And of His signs is the creation of the heavens and the earth and the
diversity of your languages and your colors" (30:22); "And We did not send any
messenger except [speaking] in the language of his people to state clearly for
them" (14:4); "O you who have believed, if there comes to you a disobedient
one with information, investigate" (49:6, Saheeh International). Lughah
(``tadbir.lughah``) tells the languages apart by counting letters; the reader
learns how each language goes on from one letter to the next, and its word is
taken only after it has been checked.

**The model** (``net``): a byte-level causal transformer of a few million
parameters (RMSNorm, rotary positions, SwiGLU, output tied to the embedding,
KV-cached decoding), conditioned on a language token. A message's words as
Lughah reads them (letters and marks, lower case, names and quoted Quran set
aside: ``lughah.own_words``) are the bytes ``x_1 … x_n``; the model gives

    log P(x | l) = Σ_{t=1..n} log p(x_t | l, x_<t)

for every language ``l`` in one batched forward pass. It is trained to end a
line too, but the end is not scored: a message may be cut short, and where a
training sentence ends says more about the corpus than about the language.

**The reader's posterior.** Bayes' rule with a uniform prior would be
P(l | x) ∝ P(x | l), but a language model's likelihoods are not calibrated:
their differences grow with the message's length and with how sure an
overfitted model is. As Tamyiz does for naive Bayes, the evidence is scaled
and divided by a power of the length:

    P_R(l | x) ∝ exp(min(1, κ · (n / ñ)^(−γ)) · log P(x | l)),

with ñ the training lines' median length in bytes. γ = 0 and κ = 1 is plain
Bayes; γ = 1 weighs every message as one median line's worth. κ ∈ (0, 1] and
γ ∈ [0, 1] minimise the log-loss on the development groups (``fit_reader``);
the exponent is never above 1, Bayes' own, because on messages the reader
never gets wrong the log-loss keeps falling as the exponent grows, and the
reader is given no more confidence than its likelihoods carry.

**Product of experts.** Lughah's posterior and the reader's are multiplied,
the reader's raised to one weight:

    P(l | x) ∝ P_L(l | x) · P_R(l | x)^b,   0 ≤ b ≤ 1,

b fitted on the development groups (golden-section search, as Iqtibas fits
its factor); b = 0 when the reader does not lower the log-loss, and b = 0 is
factor 1 for every language. b = 1 would count the reader as evidence
independent of Lughah's; both read the same words, so it is worth at most that.

**Short messages.** Whole seed sentences are easy (Lughah held out reads
every one right), while people write a few words. Each development and
held-out message is also read as its first 2 and first 3 words, in its group,
so the fit and the gate see the lengths people send.

**Held out, never trained on.** Each seed's group is the SHA-256 of its words
as read; one group in five (by that hash) is held out for good, one in eight
of the rest picks the checkpoint and fits κ, γ and b, and the reader trains on
what is left. Lughah is refitted without the held-out and development groups
for the comparison, so both are judged on words neither has seen.

**The gate** (``gate``): the reader's factor is used only when, on the
held-out groups, the combination beats Lughah alone on both counts:

- log-loss: a paired bootstrap over groups gives P(not better) below α;
- accuracy: over the messages where the two disagree in being right, the
  paired e-value (``core.adaptive.paired_e_value``) reaches k(k+1)/α for the
  k-th test of this reader (so all tests ever run spend at most α, Ville).

α = 0.05. A reader that fails it, or is missing, or was trained on another
corpus (its SHA-256 differs from the seeds'), changes nothing.

**Its own corpus** (``corpus``): Lughah's seeds stay Lughah's; the reader may
also learn from licence-clean text that is not theirs (Tatoeba sentences the
seeds do not use, MASSIVE 1.1's training utterances, Hinglish-1M rows), built
at train time into ``$MIZAN_DATA_DIR`` with every line checked: its own
script, not a seed's words in any split, not a held-out short message, once,
never scripture. Its held-out slice of short requests (MASSIVE test
utterances of 3 to 8 words, held-out Roman Hindi/Urdu rows) is read and
reported beside the seeds' held-out groups; the gate stays the seeds'.

**Scripture is never a target** (``scripture``): a line is not trained on when
Lughah reads any piece of it as quoted Quran, when it shares
``LEAST_SHARED`` consecutive words with the Uthmani sample in Lughah's seeds,
or, once Iqtibas has the Quran's texts, when the mushaf holds such a run of it
or a span of it is more likely a quote than ordinary speech.

**While MIZAN rests** (``rest``, called by Nawm): a person's own words that
they let MIZAN train on (``training: on``) and that a named reviewer accepted
(the learner store) are learned under the language both Lughah and the reader
read them in (never where they disagree), with a quarter of every batch replayed
from the seeds (25% replay held a 3.8M byte model's old languages where EWC did
not). The new version replaces the current one only when it is not worse on
the held-out seeds (Ta'lim's paired bootstrap), the previous one is kept for
rollback, and the gate is run again. Erasing a chat (Mahw) drops every version
that learned from its words (``forget``).

``MIZAN_RUH_READER``: ``off``; ``shadow`` (default: computed and logged beside
Lughah's decision, which it never changes); ``on`` (weighed in once the gate
passed). Weights and fit: ``$MIZAN_DATA_DIR/models/ruh_reader/``.

    cd backend && python -m tadbir.ruh_reader --train [--seed N]
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import json
import logging
import math
import os
import random
import shutil
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("mizan.ruh_reader")

MODES = ("off", "shadow", "on")
ALPHA = 0.05
HELD_OUT = 5  # one group in five is held out for good
DEV = 8  # one group in eight of the rest fits κ, γ, b and picks the checkpoint
REPLAY = 0.25  # share of every night batch replayed from the seeds
RESAMPLES = 2000
# Consecutive words a line must share with the Quran before it is a quote
# (the run Muhasaba reads as a quote of an ayah given with no reference).
LEAST_SHARED = 4
# b = 1 is the reader counted as independent evidence; it reads the same words
# as Lughah, so it is worth at most that.
B_RANGE = (0.0, 1.0)
PREFIXES = (2, 3)  # short messages: the first words of each held-out message
CONFIG = {"d_model": 256, "layers": 4, "heads": 4, "d_ff": 768, "context": 192, "dropout": 0.1}
PLAN = {"epochs": 12.0, "seconds": 1500.0, "batch": 32, "lr": 2e-3}
NIGHT = {"epochs": 3.0, "lr": 5e-4, "warmup": 10}
VERSIONS = ("current", "previous", "base")


def mode() -> str:
    value = os.getenv("MIZAN_RUH_READER", "shadow").strip().lower()
    return value if value in MODES else "shadow"


def has_torch() -> bool:
    return importlib.util.find_spec("torch") is not None


def home() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data")) / "models" / "ruh_reader"


# ── the words, their groups and the splits ───────────────────────────────


def reading(text: str) -> str:
    """Letters and marks, lower case: the words as Lughah reads them."""
    from core.tamyiz import letters

    return str(letters(text)).lower()


def group_of(text: str) -> str:
    return hashlib.sha256(reading(text).encode("utf-8")).hexdigest()


def part(group: str) -> str:
    """``held_out`` (one group in five, for good), ``dev`` or ``train``."""
    if int(group[:8], 16) % HELD_OUT == 0:
        return "held_out"
    return "dev" if int(group[8:16], 16) % DEV == 0 else "train"


def seeds() -> list[tuple[str, str]]:
    """Lughah's examples of the asker's languages (not the neutral names and quotes)."""
    from .. import lughah

    return [(text, label) for text, label in lughah.corpus() if label not in lughah.NEUTRAL]


def corpus_digest(rows: Sequence[tuple[str, str]]) -> str:
    from core.tamyiz_cache import digest

    return str(digest(list(rows)))


def text_digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


# ── scripture is never a training target ─────────────────────────────────


@cache
def _quote_shingles() -> frozenset[tuple[str, ...]]:
    """Runs of ``LEAST_SHARED`` words of the Uthmani sample in Lughah's seeds,
    folded as the Truth Gate reads Arabic across scripts."""
    from .. import lughah, muqabala

    found: set[tuple[str, ...]] = set()
    for line in (lughah.CORPUS / "quote.tsv").read_text(encoding="utf-8").splitlines():
        _source, _, text = line.partition("\t")
        words = [word.folded for word in muqabala.words(text)]
        found.update(
            tuple(words[i : i + LEAST_SHARED]) for i in range(len(words) - LEAST_SHARED + 1)
        )
    return frozenset(found)


def scripture(text: str, mushaf: bool = True) -> bool:
    """Whether the text holds the Quran's words, so it is never trained on.
    Without ``mushaf`` Iqtibas's texts are not asked (a line a corpus build
    already checked with them)."""
    from .. import iqtibas, lughah, muqabala

    if not text.strip():
        return False
    if lughah.quoted(text):
        return True
    folded = [word.folded for word in muqabala.words(text)]
    shingles = _quote_shingles()
    if any(
        tuple(folded[i : i + LEAST_SHARED]) in shingles
        for i in range(len(folded) - LEAST_SHARED + 1)
    ):
        return True
    quotes = iqtibas.ready() if mushaf else None
    if quotes is not None:
        if quotes.runs(folded, LEAST_SHARED):
            return True
        span = iqtibas.quoted(text, quotes)
        if span is not None and span.evidence > 0 and len(span.words) >= LEAST_SHARED:
            return True
    return False


def training_lines(
    rows: Iterable[tuple[str, str]], languages: Sequence[str], mushaf: bool = True
) -> tuple[list[tuple[str, int]], int]:
    """(words as read, language slot) for every row that is not scripture, and
    how many rows were set aside as scripture."""
    slot = {label: index for index, label in enumerate(languages)}
    kept: list[tuple[str, int]] = []
    dropped = 0
    for text, label in rows:
        if label not in slot:
            continue
        if scripture(text, mushaf):
            dropped += 1
            continue
        words = reading(text)
        if words:
            kept.append((words, slot[label]))
    return kept, dropped


# ── the posterior, the product of experts, and their fits ────────────────


def _log_softmax(row: Sequence[float]) -> list[float]:
    top = max(row)
    norm = top + math.log(sum(math.exp(value - top) for value in row))
    return [value - norm for value in row]


def reader_log_posterior(
    lm: Sequence[float], tokens: int, kappa: float, gamma: float, ref: float
) -> list[float]:
    """log P_R(l | x) for each language from log P(x | l). The exponent never
    exceeds 1: the reader claims at most what its own likelihoods say."""
    scale = min(1.0, kappa * (max(tokens, 1) / ref) ** (-gamma))
    return _log_softmax([scale * value for value in lm])


def combined_log_posterior(
    lughah: Sequence[float], reader: Sequence[float], b: float
) -> list[float]:
    """log of P_L(l | x) · P_R(l | x)^b, normalised."""
    return _log_softmax([a + b * r for a, r in zip(lughah, reader, strict=True)])


def log_loss(rows: Sequence[Sequence[float]], truths: Sequence[int]) -> float:
    """Mean −log P(truth) of normalised log posteriors."""
    return -sum(row[t] for row, t in zip(rows, truths, strict=True)) / max(1, len(truths))


def _golden(loss: Callable[[float], float], low: float, high: float) -> float:
    from core.tamyiz import _golden as golden

    return float(golden(loss, low, high))


def fit_reader(
    lm: Sequence[Sequence[float]], tokens: Sequence[int], truths: Sequence[int], ref: float
) -> tuple[float, float, float]:
    """κ ∈ (0, 1] and γ ∈ [0, 1] with the lowest log-loss (coordinate descent
    on log κ and γ, the ends of the ranges candidates too, as Tamyiz fits its
    weights). On messages the reader never gets wrong the log-loss falls
    without end as κ grows; Bayes' own exponent, 1, is the most it is given."""

    def loss(log_kappa: float, gamma: float) -> float:
        kappa = math.exp(log_kappa)
        rows = [
            reader_log_posterior(r, m, kappa, gamma, ref) for r, m in zip(lm, tokens, strict=True)
        ]
        return log_loss(rows, truths)

    log_kappa, gamma = 0.0, 0.0
    for _ in range(3):

        def along_kappa(x: float, g: float = gamma) -> float:
            return loss(x, g)

        log_kappa = min((_golden(along_kappa, math.log(1e-3), 0.0), 0.0), key=along_kappa)

        def along_gamma(g: float, x: float = log_kappa) -> float:
            return loss(x, g)

        # The search's ends are candidates too: γ = 0 is plain Bayes.
        gamma = min((0.0, _golden(along_gamma, 0.0, 1.0), 1.0), key=along_gamma)
    return math.exp(log_kappa), gamma, loss(log_kappa, gamma)


def fit_b(
    lughah: Sequence[Sequence[float]], reader: Sequence[Sequence[float]], truths: Sequence[int]
) -> tuple[float, float, float]:
    """b ∈ [0, 1] with the lowest log-loss of the product; 0 unless it lowers
    it by more than the rounding of the loss itself (a mean of n terms, each
    rounded: n · ε · the loss), so a reader that adds nothing gets b = 0 on
    every platform. Returns (b, loss at b = 0, loss at b)."""

    def loss(b: float) -> float:
        return log_loss(
            [combined_log_posterior(a, r, b) for a, r in zip(lughah, reader, strict=True)], truths
        )

    before = loss(0.0)
    b = min((_golden(loss, *B_RANGE), B_RANGE[1]), key=loss)
    after = loss(b)
    rounding = len(truths) * sys.float_info.epsilon * max(before, 1.0)
    return (b, before, after) if before - after > rounding else (0.0, before, before)


# ── the gate ─────────────────────────────────────────────────────────────


def needed(test: int) -> float:
    """The e-value the ``test``-th test of a reader must reach: k(k+1)/α."""
    return test * (test + 1) / ALPHA


def _argmax(row: Sequence[float]) -> int:
    return max(range(len(row)), key=row.__getitem__)


def p_not_better(
    differences: Sequence[float], groups: Sequence[str], resamples: int = RESAMPLES
) -> float:
    """P(mean difference ≥ 0) under a paired bootstrap that resamples whole groups."""
    by_group: dict[str, list[float]] = {}
    for difference, group in zip(differences, groups, strict=True):
        by_group.setdefault(group, []).append(difference)
    sums = [(sum(values), len(values)) for values in by_group.values()]
    if not sums:
        return 1.0
    rng = random.Random(0)
    size = len(sums)
    worse = 0
    for _ in range(resamples):
        total = count = 0.0
        for _ in range(size):
            value, n = sums[rng.randrange(size)]
            total += value
            count += n
        if total / count >= 0:
            worse += 1
    return worse / resamples


def gate(
    truths: Sequence[int],
    groups: Sequence[str],
    before: Sequence[Sequence[float]],
    after: Sequence[Sequence[float]],
    test: int = 1,
) -> dict:
    """Whether ``after`` (log posteriors) beats ``before`` on these held-out
    messages in log-loss and in accuracy by more than chance. Messages of one
    group (a message and its first words) count together: a group is a win
    when ``after`` is right on more of them, a loss when on fewer."""
    differences = [-a[t] + b[t] for a, b, t in zip(after, before, truths, strict=True)]
    right_before = [_argmax(row) == t for row, t in zip(before, truths, strict=True)]
    right_after = [_argmax(row) == t for row, t in zip(after, truths, strict=True)]
    net: dict[str, int] = {}
    for group, was, now in zip(groups, right_before, right_after, strict=True):
        net[group] = net.get(group, 0) + int(now) - int(was)
    wins = sum(1 for change in net.values() if change > 0)
    losses = sum(1 for change in net.values() if change < 0)
    from core.adaptive import paired_e_value

    e_value = paired_e_value(wins, losses)
    risk = p_not_better(differences, groups)
    mean = sum(differences) / max(1, len(differences))
    adopted = mean < 0 and wins > losses and risk < ALPHA and e_value >= needed(test)
    return {
        "adopted": adopted,
        "n": len(truths),
        "groups": len(net),
        "log_loss_before": round(log_loss(before, truths), 6),
        "log_loss_after": round(log_loss(after, truths), 6),
        "p_not_better": risk,
        "wins": wins,
        "losses": losses,
        "e_value": round(e_value, 4),
        "needed": needed(test),
        "test": test,
        "accuracy_before": round(sum(right_before) / max(1, len(truths)), 6),
        "accuracy_after": round(sum(right_after) / max(1, len(truths)), 6),
    }


# ── reading messages with a trained reader ───────────────────────────────


@dataclass
class Fit:
    kappa: float = 1.0
    gamma: float = 0.0
    ref: float = 1.0
    b: float = 0.0

    def to_dict(self) -> dict:
        return {"kappa": self.kappa, "gamma": self.gamma, "ref": self.ref, "b": self.b}


@dataclass
class Read:
    """One message read by both experts."""

    text: str
    truth: int
    group: str
    own: str
    lughah: list[float]  # log P_L(l | x)
    lm: list[float] = field(default_factory=list)  # log P(x | l), nats
    tokens: int = 0
    kind: str = "whole"  # the whole message, or its first k words ("2w", "3w")

    def reader(self, fit: Fit) -> list[float]:
        if not self.own:
            return [-math.log(len(self.lughah))] * len(self.lughah)
        return reader_log_posterior(self.lm, self.tokens, fit.kappa, fit.gamma, fit.ref)

    def combined(self, fit: Fit) -> list[float]:
        return combined_log_posterior(self.lughah, self.reader(fit), fit.b)


def variants(text: str, prefixes: Sequence[int] = PREFIXES) -> list[tuple[str, str]]:
    """The message, and its first k words for each k it is longer than: the
    short messages people send, cut from messages whose language is known."""
    words = text.split()
    return [("whole", text)] + [(f"{k}w", " ".join(words[:k])) for k in prefixes if len(words) > k]


def read_with_lughah(
    rows: Sequence[tuple[str, str]],
    languages: Sequence[str],
    using: Any = None,
    prefixes: Sequence[int] = PREFIXES,
) -> list[Read]:
    """Each (text, label) and its first words as Lughah reads them (``using``:
    a fit of Lughah that never saw these rows): the user's own words and
    log P_L(l | x). A message and its first words share the message's group."""
    from .. import lughah

    slot = {label: index for index, label in enumerate(languages)}
    found = []
    for whole, label in rows:
        group = group_of(whole)
        for kind, text in variants(whole, prefixes):
            posterior = lughah.naive_posterior(text, using=using)
            found.append(
                Read(
                    text=text,
                    truth=slot[label],
                    group=group,
                    own=reading(lughah.own_words(text, using)),
                    lughah=[math.log(max(posterior.get(code, 0.0), 1e-300)) for code in languages],
                    kind=kind,
                )
            )
    return found


def score_reads(model: Any, reads: Sequence[Read], languages: Sequence[str]) -> None:
    """log P(x | l) for every read and language, in batched forward passes."""
    from . import net

    texts = [read.own for read in reads if read.own]
    scored, counts = net.score(model, texts, list(range(len(languages))))
    iterator = iter(zip(scored, counts, strict=True))
    for read in reads:
        if read.own:
            read.lm, read.tokens = next(iterator)


def bits_per_byte(reads: Sequence[Read], languages: Sequence[str]) -> dict[str, float]:
    """Held-out bits per byte of whole messages, per true language."""
    nats: dict[str, float] = {}
    tokens: dict[str, int] = {}
    for read in reads:
        if read.own and read.kind == "whole":
            code = languages[read.truth]
            nats[code] = nats.get(code, 0.0) - read.lm[read.truth]
            tokens[code] = tokens.get(code, 0) + read.tokens
    return {code: round(nats[code] / tokens[code] / math.log(2), 4) for code in nats}


def arms(reads: Sequence[Read], fit: Fit) -> dict[str, list[list[float]]]:
    return {
        "lughah": [read.lughah for read in reads],
        "reader": [read.reader(fit) for read in reads],
        "combined": [read.combined(fit) for read in reads],
    }


def fit_on(reads: Sequence[Read], ref: float) -> Fit:
    """κ and γ for the reader alone, then b for the product, on these reads."""
    scored = [read for read in reads if read.own]
    kappa, gamma, _loss = fit_reader(
        [read.lm for read in scored],
        [read.tokens for read in scored],
        [r.truth for r in scored],
        ref,
    )
    fit = Fit(kappa=kappa, gamma=gamma, ref=ref)
    b, _before, _after = fit_b(
        [read.lughah for read in reads],
        [read.reader(fit) for read in reads],
        [r.truth for r in reads],
    )
    fit.b = b
    return fit


# ── building a reader from the seeds ─────────────────────────────────────


@dataclass
class Built:
    model: Any
    manifest: dict
    dev: list[Read]
    held_out: list[Read]
    lughah: Any  # the fit of Lughah that never saw dev or held-out
    short: list[Read] = field(default_factory=list)  # the corpus's held-out short messages


def held_out_lughah(rows: Sequence[tuple[str, str]], calibrate: bool = True) -> Any:
    """Lughah refitted (α, weights and γ by its own leave-one-out) on the
    training groups and the neutral classes only. Without ``calibrate`` it
    keeps the shipped fit's α, weights and γ (a quick check, not a measurement)."""
    from core.tamyiz import Tamyiz

    from .. import lughah

    neutral = [(text, label) for text, label in lughah.corpus() if label in lughah.NEUTRAL]
    train = [row for row in rows if part(group_of(row[0])) == "train"]
    model = Tamyiz(lughah._features).fit([*train, *neutral], calibrate=calibrate)
    if not calibrate:
        shipped = lughah.model()
        model.alpha, model.weights, model.gamma = shipped.alpha, shipped.weights, shipped.gamma
    return model


def _corpus_lines(
    found: Any, languages: Sequence[str], guarded: set[str]
) -> tuple[list[tuple[str, int]], dict]:
    """The corpus's training lines (a ``corpus.Corpus``), checked again here:
    a line whose words are a development or held-out seed's, or a held-out
    short message's, is dropped, and scripture is set aside (Iqtibas's texts
    asked again only when the corpus was built without them)."""
    short = {group_of(text) for text, _label, _group in found.short}
    fresh = [
        (text, label)
        for text, label in found.train
        if group_of(text) not in guarded and group_of(text) not in short
    ]
    checked = bool((found.manifest.get("scripture") or {}).get("iqtibas"))
    lines, dropped = training_lines(fresh, languages, mushaf=not checked)
    per_language: dict[str, int] = {}
    for _words, slot in lines:
        per_language[languages[slot]] = per_language.get(languages[slot], 0) + 1
    return lines, {
        "train_sha256": found.manifest["train"]["sha256"],
        "short_sha256": found.manifest["short"]["sha256"],
        "lines": len(lines),
        "bytes": sum(len(words.encode("utf-8")) for words, _slot in lines),
        "per_language": per_language,
        "held_out_dropped": len(found.train) - len(fresh),
        "scripture_set_aside": dropped,
        "sources": [
            {key: item.get(key) for key in ("name", "licence", "sha256", "pinned")}
            for item in found.manifest.get("sources", [])
        ],
    }


def trained_key(
    seed: int,
    config: dict,
    plan: dict,
    lines: Sequence[tuple[str, int]],
    dev_lines: Sequence[tuple[str, int]],
) -> str:
    """What a training run depends on: its seed, settings and lines."""
    digest = hashlib.sha256()
    digest.update(json.dumps([seed, config, plan], sort_keys=True).encode("utf-8"))
    for name, items in (("train", lines), ("dev", dev_lines)):
        digest.update(name.encode("utf-8"))
        for text, slot in items:
            digest.update(f"{slot}\t{text}\n".encode())
    return digest.hexdigest()


def _trained_files(folder: Path, seed: int) -> tuple[Path, Path]:
    return folder / f"reader-seed{seed}.trained.pt", folder / f"seed{seed}.trained"


def keep_trained(folder: Path, seed: int, key: str, model: Any, report: dict) -> None:
    """The weights first, then the marker: a marker always names weights on disk."""
    from . import net

    weights, marker = _trained_files(folder, seed)
    net.save(model, weights)
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "seed": seed,
                "key": key,
                "weights": weights.name,
                "sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "report": report,
                "kept": datetime.now(UTC).isoformat(),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    temporary.replace(marker)


def load_trained(folder: Path, seed: int, key: str, model: Any) -> dict | None:
    """The training report of weights kept for this seed and key, loaded into
    ``model``; None when there are none, or they belong to another run."""
    import torch

    weights, marker = _trained_files(folder, seed)
    try:
        found = json.loads(marker.read_text(encoding="utf-8"))
        data = weights.read_bytes()
    except (OSError, ValueError):
        return None
    if found.get("key") != key or found.get("sha256") != hashlib.sha256(data).hexdigest():
        return None
    saved = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict(saved["state"])
    model.eval()
    report = found.get("report")
    return report if isinstance(report, dict) else None


def build(
    seed: int = 0,
    *,
    config: dict | None = None,
    plan: dict | None = None,
    rows: Sequence[tuple[str, str]] | None = None,
    corpus: Any = None,
    threads: int = 2,
    log: Callable[[str], None] = logger.info,
    loss_hook: Callable | None = None,
    calibrate: bool = True,
    trained: Path | None = None,
) -> Built:
    """Train a reader on the training groups of the seeds (and on the lines of
    ``corpus``, a ``corpus.Corpus``, when given), fit κ, γ and b on the
    development groups, and judge it against Lughah on the held-out ones (and,
    reported but never deciding, on the corpus's held-out short messages).

    With ``trained`` (a folder), the weights are written there the moment
    training ends (``reader-seed{N}.trained.pt``, then the marker
    ``seed{N}.trained`` with the training report), before anything is read;
    a later build of the same seed, settings and lines finds them and does
    not train again, so a stopped run costs only the reading."""
    import torch

    from .. import iqtibas
    from . import net

    rows = list(rows if rows is not None else seeds())
    languages = list(dict.fromkeys(label for _text, label in rows))
    if len(languages) > net.SLOTS:
        raise ValueError(f"The reader has {net.SLOTS} language slots")
    splits: dict[str, list[tuple[str, str]]] = {"train": [], "dev": [], "held_out": []}
    for row in rows:
        splits[part(group_of(row[0]))].append(row)
    if iqtibas.enabled() and iqtibas.ready() is None:
        iqtibas.load()  # the Quran's texts, when on disk: the full scripture check
    lines, dropped = training_lines(splits["train"], languages)
    dev_lines, _ = training_lines(splits["dev"], languages)
    extra: dict | None = None
    if corpus is not None:
        guarded = {group_of(text) for text, _label in [*splits["dev"], *splits["held_out"]]}
        more, extra = _corpus_lines(corpus, languages, guarded)
        lines = [*lines, *more]
    log(
        f"reader: {len(lines)} training lines ({dropped} seeds set aside as scripture"
        + (f", {extra['lines']} from the corpus" if extra else "")
        + f"), {len(splits['dev'])} dev, {len(splits['held_out'])} held out"
    )
    began = time.monotonic()
    fold = held_out_lughah(rows, calibrate)
    log(f"reader: Lughah refitted without dev and held-out in {time.monotonic() - began:.1f}s")
    torch.manual_seed(seed)
    model = net.Reader(net.Config(**{**CONFIG, **(config or {})}))
    settings = {**PLAN, **(plan or {})}
    key = trained_key(seed, model.config.to_dict(), settings, lines, dev_lines)
    report = load_trained(trained, seed, key, model) if trained is not None else None
    if report is not None:
        log(
            f"reader: seed {seed} already trained ({report['steps']} steps in "
            f"{report['seconds']}s, dev {report['dev_bpb']}), read from {trained}"
        )
    else:
        report = net.train(
            model,
            lines,
            net.Plan(seed=seed, threads=threads, **settings),
            dev=dev_lines,
            loss_hook=loss_hook,
        )
        log(
            f"reader: trained {report['steps']} steps in {report['seconds']}s, "
            f"dev {report['dev_bpb']}"
        )
        if trained is not None:
            keep_trained(trained, seed, key, model, report)
            log(f"reader: seed {seed}'s weights kept in {trained} before reading")
    dev = read_with_lughah(splits["dev"], languages, fold)
    held = read_with_lughah(splits["held_out"], languages, fold)
    short: list[Read] = []
    if corpus is not None:
        chosen = [item for item in corpus.short if item[1] in languages]
        short = read_with_lughah([(t, label) for t, label, _g in chosen], languages, fold, ())
        for read, (_text, _label, group) in zip(short, chosen, strict=True):
            read.group = group  # a MASSIVE request in every language is one group
    score_reads(model, dev + held + short, languages)
    ref = float(
        sorted(len(net.encode(text, model.config.context)) for text, _ in lines)[len(lines) // 2]
    )
    fit = fit_on(dev, ref)
    verdict = gate(
        [r.truth for r in held],
        [r.group for r in held],
        arms(held, fit)["lughah"],
        arms(held, fit)["combined"],
    )
    manifest = {
        "version": 1,
        "created": datetime.now(UTC).isoformat(),
        "corpus_sha256": corpus_digest(rows),
        "languages": languages,
        "config": model.config.to_dict(),
        "parameters": model.parameters_count(),
        "seed": seed,
        "plan": settings,
        "training": {k: v for k, v in report.items() if k != "history"},
        "history": report.get("history", []),
        "scripture_set_aside": dropped,
        "scripture_mushaf": iqtibas.ready() is not None,
        "split": {name: len(items) for name, items in splits.items()},
        "corpus": extra,
        "fit": fit.to_dict(),
        "held_out_bpb": bits_per_byte(held, languages),
        "gate": verdict,
        "adopted": verdict["adopted"] and fit.b > 0,
        "tests": 1,
        "learned": [],
        "parent": None,
    }
    if short:
        # Reported, never deciding: the gate is the seeds' held-out groups.
        manifest["short"] = {
            "n": len(short),
            "bpb": bits_per_byte(short, languages),
            "check": gate(
                [r.truth for r in short],
                [r.group for r in short],
                arms(short, fit)["lughah"],
                arms(short, fit)["combined"],
            ),
        }
    return Built(model, manifest, dev, held, fold, short)


# ── versions on disk ─────────────────────────────────────────────────────


def _files(name: str) -> tuple[Path, Path, Path]:
    folder = home()
    return folder / f"{name}.pt", folder / f"{name}.json", folder / f"{name}.reads.json"


def _write_reads(path: Path, dev: Sequence[Read], held: Sequence[Read]) -> None:
    """The dev and held-out messages as Lughah read them (they do not change
    while the corpus does not), so a night re-scores only the reader."""

    def plain(reads: Sequence[Read]) -> list[dict]:
        return [
            {
                "text": r.text,
                "truth": r.truth,
                "group": r.group,
                "own": r.own,
                "lughah": r.lughah,
                "kind": r.kind,
            }
            for r in reads
        ]

    path.write_text(json.dumps({"dev": plain(dev), "held_out": plain(held)}), encoding="utf-8")


def _read_reads(path: Path) -> tuple[list[Read], list[Read]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Read(**item) for item in data["dev"]], [Read(**item) for item in data["held_out"]]


def save(built: Built, name: str = "current") -> None:
    from . import net

    weights, manifest, reads = _files(name)
    weights.parent.mkdir(parents=True, exist_ok=True)
    net.save(built.model, weights)
    _write_reads(reads, built.dev, built.held_out)
    manifest.write_text(json.dumps(built.manifest, indent=1), encoding="utf-8")
    reset()


def install(built: Built) -> None:
    """A reader built from the seeds becomes the base and the current version."""
    for name in ("current", "previous"):
        for path in _files(name):
            path.unlink(missing_ok=True)
    save(built, "base")
    save(built, "current")


def manifest(name: str = "current") -> dict | None:
    try:
        data = json.loads(_files(name)[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _copy(source: str, target: str) -> None:
    for frm, to in zip(_files(source), _files(target), strict=True):
        if frm.exists():
            shutil.copyfile(frm, to)


def _remove(name: str) -> None:
    for path in _files(name):
        path.unlink(missing_ok=True)


def rollback() -> bool:
    """The previous version becomes the current one again."""
    if manifest("previous") is None:
        return False
    _copy("previous", "current")
    _remove("previous")
    reset()
    return True


def forget(texts: Iterable[str]) -> int:
    """Drop every version that learned from any of these texts (Mahw): the
    newest version that did not becomes the current one. Returns how many
    versions were dropped."""
    digests = {text_digest(text) for text in texts if text and text.strip()}
    if not digests:
        return 0
    dropped = 0
    for name in ("current", "previous"):
        found = manifest(name)
        if found is not None and digests & set(found.get("learned") or []):
            _remove(name)
            dropped += 1
    if dropped and manifest("current") is None:
        if manifest("previous") is not None:
            _copy("previous", "current")
            _remove("previous")
        elif manifest("base") is not None:
            _copy("base", "current")
    if dropped:
        reset()
    return dropped


# ── the reader at run time ───────────────────────────────────────────────


@dataclass
class Loaded:
    model: Any
    manifest: dict
    fit: Fit
    languages: tuple[str, ...]
    cache: dict[str, list[float]] = field(default_factory=dict)

    @property
    def adopted(self) -> bool:
        return bool(self.manifest.get("adopted")) and self.fit.b > 0

    def posterior(self, own: str) -> list[float]:
        """log P_R(l | words) for each of the reader's languages."""
        words = reading(own)
        found = self.cache.get(words)
        if found is None:
            from . import net

            scored, counts = net.score(self.model, [words], list(range(len(self.languages))))
            found = reader_log_posterior(
                scored[0], counts[0], self.fit.kappa, self.fit.gamma, self.fit.ref
            )
            if len(self.cache) > 1024:
                self.cache.clear()
            self.cache[words] = found
        return found


_lock = threading.Lock()
_loaded: Loaded | None = None
_loading = False
_refused: tuple[float, int] | None = None  # the version file a load turned down
_shadow = {"read": 0, "agreed": 0, "would_change": 0, "reader_differs": 0}


def reset() -> None:
    """Forget the loaded reader (a new version was written, or the seeds changed)."""
    global _loaded, _refused
    with _lock:
        _loaded = None
        _refused = None


def _stamp() -> tuple[float, int] | None:
    try:
        found = _files("current")[1].stat()
    except OSError:
        return None
    return found.st_mtime, found.st_size


def load() -> Loaded | None:
    """The current version, when its corpus is the seeds' and torch is here.
    A version turned down is not read again until its file changes."""
    global _loaded, _loading, _refused
    stamp = _stamp()
    try:
        found = manifest("current")
        if found is None or not has_torch():
            _refused = stamp
            return None
        rows = seeds()
        languages = tuple(dict.fromkeys(label for _text, label in rows))
        if (
            found.get("corpus_sha256") != corpus_digest(rows)
            or tuple(found.get("languages") or ()) != languages
        ):
            logger.info("Ruh reader: trained on another corpus; not used until retrained")
            _refused = stamp
            return None
        import torch

        from . import net

        torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
        model = net.load(_files("current")[0])
        fit = Fit(**found["fit"])
        loaded = Loaded(model, found, fit, languages)
        with _lock:
            _loaded = loaded
        return loaded
    except Exception as exc:  # noqa: BLE001 - a broken reader is no reader
        logger.warning("Ruh reader unavailable: %s", exc)
        _refused = stamp
        return None
    finally:
        _loading = False


def available() -> Loaded | None:
    """The loaded reader, or None while it is read in the background (the
    message in hand is read without it), off, or absent."""
    global _loading
    if _loaded is not None or mode() == "off":
        return _loaded if mode() != "off" else None
    stamp = _stamp()
    if stamp is None or stamp == _refused:
        return None
    with _lock:
        if _loading:
            return None
        _loading = True
    threading.Thread(target=load, name="ruh-reader-load", daemon=True).start()
    return None


def weigh(found: dict[str, float], own: str) -> dict[str, float]:
    """Lughah's posterior with the reader's opinion multiplied in, when the
    reader is on and passed its gate; otherwise Lughah's posterior unchanged
    (in shadow the reader's verdict is computed and logged)."""
    if mode() == "off" or not found or not own.strip():
        return found
    loaded = available()
    if loaded is None or set(found) != set(loaded.languages):
        return found
    try:
        reader = loaded.posterior(own)
    except Exception as exc:  # noqa: BLE001 - the reader never stops a message
        logger.warning("Ruh reader failed: %s", exc)
        return found
    lughah = [math.log(max(found[code], 1e-300)) for code in loaded.languages]
    mixed = combined_log_posterior(lughah, reader, loaded.fit.b)
    alone, joint = _argmax(lughah), _argmax(mixed)
    _shadow["read"] += 1
    _shadow["agreed"] += int(_argmax(reader) == alone)
    _shadow["reader_differs"] += int(_argmax(reader) != alone)
    _shadow["would_change"] += int(joint != alone)
    if joint != alone:
        logger.info(
            "Ruh reader (%s): Lughah reads %s, with the reader %s",
            mode(),
            loaded.languages[alone],
            loaded.languages[joint],
        )
    if mode() == "on" and loaded.adopted:
        return {code: math.exp(value) for code, value in zip(loaded.languages, mixed, strict=True)}
    return found


def status() -> dict:
    """What the current reader is, how it was judged, and what shadow saw."""
    found = manifest("current")
    return {
        "mode": mode(),
        "torch": has_torch(),
        "present": found is not None,
        "adopted": bool(found and found.get("adopted")),
        "gate": (found or {}).get("gate"),
        "fit": (found or {}).get("fit"),
        "parameters": (found or {}).get("parameters"),
        "learned": len((found or {}).get("learned") or []),
        "previous": manifest("previous") is not None,
        "shadow": dict(_shadow),
    }


# ── learning while MIZAN rests ───────────────────────────────────────────


def reviewed_words(owner: str) -> list[str]:
    """The person's own messages that a named reviewer accepted, as captured
    (only under ``training: on``) in their learner store, review hash intact."""
    from learner.review_contract import content_hash
    from memory.mahw import private_dir

    path = private_dir(owner) / "learner.sqlite3"
    if not path.exists():
        return []
    conn = sqlite3.connect(path, timeout=10)
    try:
        rows = conn.execute(
            "SELECT prompt, response, provider, model, reviewed_content_hash FROM interactions "
            "WHERE review_status = 'accepted' ORDER BY id"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [row[0] for row in rows if row[4] == content_hash(*row[:4]) and row[0].strip()]


def agreed_language(text: str, model: Any, fit: Fit, languages: Sequence[str]) -> int | None:
    """The language slot Lughah and the reader both read the text in, or None."""
    from .. import lughah
    from . import net

    alone = lughah.naive_posterior(text)
    if set(alone) != set(languages):
        return None
    first = _argmax([alone[code] for code in languages])
    own = reading(lughah.own_words(text))
    scored, counts = net.score(model, [own], list(range(len(languages))))
    second = _argmax(reader_log_posterior(scored[0], counts[0], fit.kappa, fit.gamma, fit.ref))
    return first if first == second else None


def no_worse(
    old: Sequence[Sequence[float]], new: Sequence[Sequence[float]], truths: Sequence[int]
) -> tuple[bool, float, float, float]:
    """Whether a new version may replace the current one: on the held-out
    seeds its log-loss is not higher and Ta'lim's paired bootstrap does not
    find it less accurate (P(worse) below ``talim.REFUSE_AT``). Returns
    (verdict, P(worse), current log-loss, new log-loss)."""
    from ..talim import REFUSE_AT, p_worse

    right_old = [_argmax(row) == t for row, t in zip(old, truths, strict=True)]
    right_new = [_argmax(row) == t for row, t in zip(new, truths, strict=True)]
    risk = p_worse(right_old, right_new)
    loss_old, loss_new = log_loss(old, truths), log_loss(new, truths)
    return risk < REFUSE_AT and loss_new <= loss_old, risk, loss_old, loss_new


def learn(
    texts: Sequence[str],
    *,
    seconds: float,
    stop: Callable[[], bool] = lambda: False,
    seed: int = 0,
    threads: int = 2,
) -> dict:
    """Continue training the current reader on these texts (consented and
    verified), with a quarter of every batch replayed from the seeds; the new
    version replaces the current one only when it is not worse on the
    held-out seeds. Never under ``learning: off``, without ``training: on``,
    or in an evaluation."""
    from memory import stateless

    if not stateless.learns() or not stateless.trains() or stateless.barred_from_training():
        return {"status": "no consent", "learned": 0}
    if not has_torch():
        return {"status": "no torch", "learned": 0}
    current = manifest("current")
    if current is None:
        return {"status": "no reader", "learned": 0}
    rows = seeds()
    if current.get("corpus_sha256") != corpus_digest(rows):
        return {"status": "stale", "learned": 0}
    began = time.monotonic()
    from .. import lughah
    from . import net

    model = net.load(_files("current")[0])
    fit = Fit(**current["fit"])
    languages = list(current["languages"])
    learned = set(current.get("learned") or [])
    counted = {"scripture": 0, "disagreed": 0, "seen": 0}
    new: list[tuple[str, int]] = []
    digests: list[str] = []
    for text in texts:
        digest = text_digest(text)
        if digest in learned or digest in digests:
            counted["seen"] += 1
            continue
        if scripture(text):
            counted["scripture"] += 1
            continue
        own = reading(lughah.own_words(text))
        if not own:
            continue
        slot = agreed_language(text, model, fit, languages)
        if slot is None:
            counted["disagreed"] += 1  # learned only where both read the same language
            continue
        new.append((own, slot))
        digests.append(digest)
    report: dict[str, Any] = {"status": "nothing new", "learned": 0, **counted}
    if not new:
        return report
    dev, held = _read_reads(_files("current")[2])
    seed_lines, _ = training_lines(
        [row for row in rows if part(group_of(row[0])) == "train"], languages
    )
    dev_lines = [(r.own, r.truth) for r in dev if r.own and r.kind == "whole"]
    challenger = copy.deepcopy(model)
    left = seconds - (time.monotonic() - began)
    plan = net.Plan(
        seconds=max(0.0, left * 0.6),
        epochs=NIGHT["epochs"],
        lr=NIGHT["lr"],
        warmup=int(NIGHT["warmup"]),
        replay=REPLAY,
        seed=seed,
        threads=threads,
    )
    trained = net.train(challenger, new, plan, dev=dev_lines, replay_lines=seed_lines, stop=stop)
    if stop() or trained["steps"] == 0:
        return {**report, "status": "stopped"}
    score_reads(model, dev + held, languages)
    old_held = arms(held, fit)
    challenger_dev = copy.deepcopy(dev)
    challenger_held = copy.deepcopy(held)
    score_reads(challenger, challenger_dev + challenger_held, languages)
    new_fit = fit_on(challenger_dev, fit.ref)
    new_held = arms(challenger_held, new_fit)
    truths = [r.truth for r in held]
    promoted, risk, loss_old, loss_new = no_worse(old_held["reader"], new_held["reader"], truths)
    test = int(current.get("tests") or 1) + 1
    verdict = gate(truths, [r.group for r in held], new_held["lughah"], new_held["combined"], test)
    report.update(
        status="promoted" if promoted else "kept",
        learned=len(new) if promoted else 0,
        steps=trained["steps"],
        seconds=round(time.monotonic() - began, 2),
        p_worse=risk,
        held_out_loss={"current": round(loss_old, 6), "challenger": round(loss_new, 6)},
        gate=verdict,
    )
    if promoted:
        manifest_new = {
            **current,
            "created": datetime.now(UTC).isoformat(),
            "fit": new_fit.to_dict(),
            "held_out_bpb": bits_per_byte(challenger_held, languages),
            "gate": verdict,
            "adopted": verdict["adopted"] and new_fit.b > 0,
            "tests": test,
            "learned": sorted(learned | set(digests)),
            "parent": current.get("created"),
            "night": {k: v for k, v in report.items() if k != "gate"},
        }
        _copy("current", "previous")
        save(Built(challenger, manifest_new, dev, held, None), "current")
    return report


async def rest(
    owner: str,
    *,
    deadline: float | None = None,
    idle: Callable[[], bool] = lambda: True,
) -> dict:
    """Nawm's part: the person's reviewed words learned while no request
    runs, within the night's time, under their own choices. Skipped when the
    reader is off or absent."""
    if mode() == "off":
        return {"status": "off"}
    from memory import stateless

    if not stateless.learns() or not stateless.trains():
        return {"status": "no consent"}
    if not has_torch() or manifest("current") is None or not idle():
        return {"status": "skipped"}
    seconds = None if deadline is None else deadline - time.monotonic()
    if seconds is not None and seconds <= 0:
        return {"status": "skipped"}
    texts = await asyncio.to_thread(reviewed_words, owner)
    if not texts:
        return {"status": "nothing new"}

    def stop() -> bool:
        return not idle() or (deadline is not None and time.monotonic() > deadline)

    budget = seconds if seconds is not None else 300.0
    return await asyncio.to_thread(learn, texts, seconds=budget, stop=stop)


def main() -> None:
    import argparse

    from . import corpus as reader_corpus

    parser = argparse.ArgumentParser(description="Train MIZAN's own language reader on the seeds")
    parser.add_argument("--corpus", action="store_true", help="download and build its corpus")
    parser.add_argument("--bytes-per-language", type=int, default=reader_corpus.BYTES_PER_LANGUAGE)
    parser.add_argument("--workers", type=int, default=1, help="processes for the scripture check")
    parser.add_argument("--train", action="store_true", help="train and install as current")
    parser.add_argument("--seeds-only", action="store_true", help="train without the corpus")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # signed download links stay out
    if args.corpus:
        found = reader_corpus.build(
            bytes_per_language=args.bytes_per_language, workers=args.workers, log=print
        )
        print(json.dumps({k: found[k] for k in ("train", "short", "kept", "dropped")}, indent=1))
    if not args.train:
        if not args.corpus:
            print(json.dumps(status(), indent=1))
        return
    extra = None if args.seeds_only else reader_corpus.load()
    built = build(args.seed, corpus=extra, threads=args.threads, log=print)
    install(built)
    shown = {k: v for k, v in built.manifest.items() if k not in {"history", "learned"}}
    print(json.dumps(shown, indent=1))


if __name__ == "__main__":
    main()
