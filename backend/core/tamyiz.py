"""Tamyiz (تمييز, discernment): telling things apart by weighing evidence.

A naive Bayes classifier over hashed features (character n-grams, words,
evidence tokens), small enough to run on every message and to learn from
every verified outcome. Nothing in it is a hand-set threshold:

- **Model.** For each class ``c``:
  ``score(c) = w_prior · log P(c) + w_text · Σ_text n_f log P(f|c) + w_evidence · Σ_evidence n_f log P(f|c)``
  with ``P(c) = (N_c + 1) / (N + K)`` (Laplace) and
  ``P(f | c) = (n_cf + α) / (n_c + α·V)`` (Dirichlet smoothing), and
  ``P(c | x) = softmax(score)``.
- **Two groups of evidence, each with its own weight.** A message's letters
  give hundreds of overlapping n-grams, which plain naive Bayes counts as if
  they were independent, while what a parser found (``e:…``) or the context
  (``c:…``) is one token. Giving each group its own weight is weighted naive
  Bayes: ``w_text`` corrects the over-counting of n-grams and ``w_evidence``
  says how much a parser finding is worth. ``w_prior`` says how much the
  number of examples per class should count (seed sets are not real
  frequencies, so the data decides).
- **Fitted, not chosen.** ``α``, ``w_prior``, ``w_text`` and ``w_evidence`` are fitted by
  exact leave-one-out log-loss: every example is scored by the model trained
  on all the others, and the values that predict the held-out examples best
  are kept.
- **Decision.** The answer is the most probable class (MAP), which minimises
  the expected number of mistakes. "Not this" is a class of its own with its
  own examples, so no cut-off decides when to act.
- **Learning.** ``learn`` adds a verified example to the counts at once.
  ``Overlay`` keeps one person's examples apart from the shared model and is
  added to it only for that person.

Features are hashed into ``2**BITS`` buckets (CRC-32), so memory is fixed no
matter how much is learned. Pure Python; no third-party dependency.
"""

from __future__ import annotations

import math
import unicodedata
import zlib
from array import array
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

BITS = 18
_MASK = (1 << BITS) - 1
ALPHAS = (0.01, 0.03, 0.1, 0.3, 1.0)
EVIDENCE = ("e:", "c:")  # parser findings and context, weighed as their own group
_EVIDENCE_BUCKETS: set[int] = set()


def bucket(feature: str) -> int:
    return zlib.crc32(feature.encode("utf-8")) & _MASK


def letters(text: str) -> str:
    """Letters and combining marks only (vowel marks are evidence too); the rest is a space."""
    kept = []
    for char in unicodedata.normalize("NFC", text or ""):
        category = unicodedata.category(char)
        kept.append(char if category[0] in "LM" else " ")
    return " ".join("".join(kept).split())


def char_ngrams(text: str, orders: Sequence[int] = (1, 2, 3, 4, 5)) -> Counter[str]:
    """Character n-grams inside each word, with word boundaries marked."""
    grams: Counter[str] = Counter()
    for word in text.lower().split():
        padded = f"␠{word}␠"
        for n in orders:
            if n > len(padded):
                continue
            for start in range(len(padded) - n + 1):
                grams[padded[start : start + n]] += 1
    return grams


def hashed(features: Counter[str] | Iterable[str]) -> dict[int, float]:
    counts = features if isinstance(features, Counter) else Counter(features)
    vector: dict[int, float] = {}
    for feature, count in counts.items():
        index = bucket(feature)
        if feature.startswith(EVIDENCE):
            _EVIDENCE_BUCKETS.add(index)
        vector[index] = vector.get(index, 0.0) + float(count)
    return vector


@dataclass
class Overlay:
    """One owner's learned examples, added to the shared counts for that owner only."""

    docs: dict[str, float] = field(default_factory=dict)
    totals: dict[str, float] = field(default_factory=dict)
    counts: dict[str, dict[int, float]] = field(default_factory=dict)

    def add(self, label: str, vector: dict[int, float], weight: float = 1.0) -> None:
        self.docs[label] = self.docs.get(label, 0.0) + weight
        table = self.counts.setdefault(label, {})
        for index, count in vector.items():
            table[index] = table.get(index, 0.0) + count * weight
            self.totals[label] = self.totals.get(label, 0.0) + count * weight

    def to_dict(self) -> dict:
        return {
            "docs": self.docs,
            "totals": self.totals,
            "counts": {
                label: {str(k): v for k, v in t.items()} for label, t in self.counts.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> Overlay:
        data = data or {}
        return cls(
            docs={str(k): float(v) for k, v in (data.get("docs") or {}).items()},
            totals={str(k): float(v) for k, v in (data.get("totals") or {}).items()},
            counts={
                str(label): {int(k): float(v) for k, v in (table or {}).items()}
                for label, table in (data.get("counts") or {}).items()
            },
        )


Parts = tuple[float, float, float]  # (log prior, text log-likelihood, evidence log-likelihood)


class Tamyiz:
    """Weighted naive Bayes over hashed features, fitted by leave-one-out."""

    def __init__(self, featurize: Callable[[str], Counter[str]]):
        self.featurize = featurize
        self.labels: list[str] = []
        self.docs: dict[str, float] = {}
        self.totals: dict[str, float] = {}
        self.counts: dict[str, array] = {}
        self.used = array("b", bytes(1 << BITS))
        self.vocabulary = 0
        self.alpha = 0.1
        self.weights = (1.0, 1.0, 1.0)  # (w_prior, w_text, w_evidence)
        self.loo_loss: float | None = None
        self.loo_accuracy: float | None = None

    # ── counts ──────────────────────────────────────────────────────────
    def vector(self, text: str) -> dict[int, float]:
        return hashed(self.featurize(text))

    def _ensure(self, label: str) -> None:
        if label not in self.counts:
            self.labels.append(label)
            self.counts[label] = array("f", bytes(4 << BITS))
            self.docs[label] = 0.0
            self.totals[label] = 0.0

    def add(self, label: str, vector: dict[int, float], weight: float = 1.0) -> None:
        self._ensure(label)
        table = self.counts[label]
        for index, count in vector.items():
            table[index] += count * weight
            if not self.used[index]:
                self.used[index] = 1
                self.vocabulary += 1
        self.docs[label] += weight
        self.totals[label] += sum(vector.values()) * weight

    def learn(self, text: str, label: str, weight: float = 1.0) -> None:
        self.add(label, self.vector(text), weight)

    # ── scoring ─────────────────────────────────────────────────────────
    def parts(
        self, vector: dict[int, float], overlay: Overlay | None = None, alpha: float | None = None
    ) -> dict[str, Parts]:
        alpha = self.alpha if alpha is None else alpha
        extra_docs = overlay.docs if overlay else {}
        extra_totals = overlay.totals if overlay else {}
        extra_counts = overlay.counts if overlay else {}
        labels = list(dict.fromkeys([*self.labels, *extra_docs]))
        documents = sum(self.docs.get(c, 0.0) + extra_docs.get(c, 0.0) for c in labels)
        size = max(1, self.vocabulary)
        known = [index for index in vector if self.used[index]] if self.vocabulary else []
        found: dict[str, Parts] = {}
        for label in labels:
            table = self.counts.get(label)
            own = extra_counts.get(label, {})
            total = self.totals.get(label, 0.0) + extra_totals.get(label, 0.0)
            denominator = math.log(total + alpha * size)
            prior = math.log(
                (self.docs.get(label, 0.0) + extra_docs.get(label, 0.0) + 1.0)
                / (documents + len(labels))
            )
            text = evidence = 0.0
            for index in known:
                count = (table[index] if table is not None else 0.0) + own.get(index, 0.0)
                term = vector[index] * (math.log(count + alpha) - denominator)
                if index in _EVIDENCE_BUCKETS:
                    evidence += term
                else:
                    text += term
            found[label] = (prior, text, evidence)
        return found

    def posterior(self, text: str, overlay: Overlay | None = None) -> dict[str, float]:
        return self.posterior_of(self.vector(text), overlay)

    def posterior_of(
        self, vector: dict[int, float], overlay: Overlay | None = None
    ) -> dict[str, float]:
        return _softmax(_combine(self.parts(vector, overlay), self.weights))

    def predict(self, text: str, overlay: Overlay | None = None) -> tuple[str, float]:
        posterior = self.posterior(text, overlay)
        label = max(posterior, key=posterior.__getitem__)
        return label, posterior[label]

    # ── fitting ─────────────────────────────────────────────────────────
    def fit(
        self, examples: Sequence[tuple[str, ...]], calibrate: bool = True, sample: int = 1500
    ) -> Tamyiz:
        """Count every example; then fit α and the weights by exact leave-one-out
        on up to ``sample`` of them (every k-th example, so the estimate is the same
        on every run).

        An example may carry a group name as a third field: examples of one group
        (one sentence in several contexts) are held out together, so a copy of the
        held-out example never stays in training."""
        rows = [(row[1], self.vector(row[0]), row[2] if len(row) > 2 else None) for row in examples]
        groups: dict[object, tuple[dict[int, float], float]] = {}
        for label, vector, group in rows:
            self.add(label, vector)
            if group is not None:
                summed, size = groups.get(group, ({}, 0.0))
                for index, count in vector.items():
                    summed[index] = summed.get(index, 0.0) + count
                groups[group] = (summed, size + 1)
        held_out = [
            (label, vector, *(groups[group] if group is not None else (vector, 1.0)))
            for label, vector, group in rows
        ]
        if calibrate and len(held_out) >= 2 * max(1, len(self.labels)):
            step = max(1, math.ceil(len(held_out) / sample))
            self.alpha, self.weights, self.loo_loss, self.loo_accuracy = _calibrate(
                self, held_out[::step]
            )
        return self

    def state(self) -> dict:
        return {
            "alpha": self.alpha,
            "weights": list(self.weights),
            "loo_loss": self.loo_loss,
            "loo_accuracy": self.loo_accuracy,
            "examples": sum(self.docs.values()),
            "labels": len(self.labels),
            "vocabulary": self.vocabulary,
        }


def _combine(parts: dict[str, Parts], weights: tuple[float, ...]) -> dict[str, float]:
    w_prior, w_text, w_evidence = weights
    return {
        label: w_prior * prior + w_text * text + w_evidence * evidence
        for label, (prior, text, evidence) in parts.items()
    }


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    top = max(scores.values())
    weights = {label: math.exp(score - top) for label, score in scores.items()}
    total = sum(weights.values())
    return {label: weight / total for label, weight in weights.items()}


HeldOut = tuple[str, dict[int, float], dict[int, float], float]  # truth, vector, removed, docs


def _loo_parts(
    model: Tamyiz, held_out: list[HeldOut], alpha: float
) -> list[tuple[str, dict[str, Parts]]]:
    """Each example's score parts under the model trained without it (and without
    the rest of its group)."""
    labels = model.labels
    size = max(1, model.vocabulary)
    logs = {label: math.log(model.totals[label] + alpha * size) for label in labels}
    held: list[tuple[str, dict[str, Parts]]] = []
    for truth, vector, removed, removed_docs in held_out:
        length = sum(removed.values())
        found: dict[str, Parts] = {}
        for label in labels:
            table = model.counts[label]
            own = label == truth
            # The prior's denominator is the same for every class, so it cancels.
            prior = math.log(
                model.docs[label] - removed_docs + 1.0 if own else model.docs[label] + 1.0
            )
            denominator = (
                math.log(model.totals[label] - length + alpha * size) if own else logs[label]
            )
            text = evidence = 0.0
            for index, count in vector.items():
                seen = max(table[index] - removed.get(index, 0.0), 0.0) if own else table[index]
                term = count * (math.log(seen + alpha) - denominator)
                if index in _EVIDENCE_BUCKETS:
                    evidence += term
                else:
                    text += term
            found[label] = (prior, text, evidence)
        held.append((truth, found))
    return held


def _loss(held: list[tuple[str, dict[str, Parts]]], weights: tuple[float, ...]) -> float:
    total = 0.0
    for truth, parts in held:
        scores = _combine(parts, weights)
        top = max(scores.values())
        normaliser = top + math.log(sum(math.exp(s - top) for s in scores.values()))
        total -= scores[truth] - normaliser
    return total / max(1, len(held))


def _golden(loss: Callable[[float], float], low: float, high: float) -> float:
    """The minimum of a one-dimensional loss on [low, high] (golden-section search)."""
    ratio = (math.sqrt(5) - 1) / 2
    a, b = high - ratio * (high - low), low + ratio * (high - low)
    fa, fb = loss(a), loss(b)
    for _ in range(32):
        if fa < fb:
            high, b, fb = b, a, fa
            a = high - ratio * (high - low)
            fa = loss(a)
        else:
            low, a, fa = a, b, fb
            b = low + ratio * (high - low)
            fb = loss(b)
    return (a + b) / 2


def _best_weights(
    held: list[tuple[str, dict[str, Parts]]],
) -> tuple[tuple[float, float, float], float]:
    """Coordinate descent on the log weights for the lowest LOO log-loss."""
    low, high = math.log(1e-3), math.log(50.0)
    point = [0.0, 0.0, 0.0]

    def at(index: int, value: float) -> tuple[float, ...]:
        trial = list(point)
        trial[index] = value
        return tuple(math.exp(x) for x in trial)

    for _ in range(4):
        for index in range(3):

            def along(x: float, i: int = index) -> float:
                return _loss(held, at(i, x))

            point[index] = _golden(along, low, high)
    weights = (math.exp(point[0]), math.exp(point[1]), math.exp(point[2]))
    return weights, _loss(held, weights)


def _calibrate(
    model: Tamyiz, vectors: list[HeldOut]
) -> tuple[float, tuple[float, float, float], float, float]:
    best: tuple[float, tuple[float, float, float], float, float] | None = None
    for alpha in ALPHAS:
        held = _loo_parts(model, vectors, alpha)
        weights, loss = _best_weights(held)
        if best is None or loss < best[2]:
            correct = sum(
                1
                for truth, parts in held
                if max(_combine(parts, weights).items(), key=lambda item: item[1])[0] == truth
            )
            best = (alpha, weights, loss, correct / max(1, len(held)))
    assert best is not None
    return best
