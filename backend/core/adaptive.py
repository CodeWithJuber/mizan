"""
Mizan Adaptive (ميزان — the Balance) — evidence-weighing estimators
====================================================================

"And the heaven He raised and imposed the balance, that you not transgress
within the balance. And establish weight in justice and do not make
deficient the balance." — Quran 55:7-9

Small, dependency-free estimators that replace fixed thresholds and magic
constants with quantities learned from observed outcomes:

- ``BetaEstimator``: Beta-Bernoulli posterior of a success rate, with optional
  exponential forgetting, Wilson bounds and Thompson sampling. Certainty
  grows with evidence, so a decision needs both a good rate *and* enough
  observations — "sample size" is implicit in the bound, not a fixed count.
- ``EWStats``: exponentially weighted mean/variance with z-scores, for
  thresholds that adapt to an agent's own baseline.
- ``actr_activation``: ACT-R base-level activation ln(Σ t_j^-d) — memory
  strength from the timing of every past access (spacing and repetition,
  i.e. dhikr strengthens remembrance), instead of one fixed half-life.
- ``bm25_scores``: query relevance with inverse-document-frequency weights.
- ``softmax`` with an explicit temperature and ``entropy``.

``AdaptiveStateStore`` persists named estimator states in SQLite so learning
survives restarts.
"""

from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

_WORD = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Lower-cased word tokens (Unicode-aware; no substring matching)."""
    return [token.lower() for token in _WORD.findall(text or "")]


# ───── Proportions ─────


def wilson_bounds(successes: float, trials: float, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (works for small n)."""
    if trials <= 0:
        return 0.0, 1.0
    p = min(1.0, max(0.0, successes / trials))
    denominator = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    margin = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return (
        max(0.0, (centre - margin) / denominator),
        min(1.0, (centre + margin) / denominator),
    )


@dataclass
class BetaEstimator:
    """Posterior of a success probability, Beta(alpha, beta).

    ``forgetting`` (γ ≤ 1) shrinks old evidence toward the prior on each
    update so the estimate tracks change; γ = 1 keeps all evidence.
    """

    alpha: float = 1.0
    beta: float = 1.0
    forgetting: float = 1.0
    prior_alpha: float = 1.0
    prior_beta: float = 1.0

    def update(self, outcome: bool | float, weight: float = 1.0) -> BetaEstimator:
        value = min(1.0, max(0.0, float(outcome)))
        if self.forgetting < 1.0:
            self.alpha = self.prior_alpha + (self.alpha - self.prior_alpha) * self.forgetting
            self.beta = self.prior_beta + (self.beta - self.prior_beta) * self.forgetting
        self.alpha += weight * value
        self.beta += weight * (1.0 - value)
        return self

    @property
    def evidence(self) -> float:
        return max(0.0, self.alpha + self.beta - self.prior_alpha - self.prior_beta)

    @property
    def successes(self) -> float:
        return max(0.0, self.alpha - self.prior_alpha)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        total = self.alpha + self.beta
        return self.alpha * self.beta / (total * total * (total + 1))

    def lower_bound(self, z: float = 1.96) -> float:
        """Conservative rate: Wilson lower bound on the observed evidence."""
        return wilson_bounds(self.successes, self.evidence, z)[0]

    def upper_bound(self, z: float = 1.96) -> float:
        return wilson_bounds(self.successes, self.evidence, z)[1]

    def probability_at_least(self, rate: float) -> float:
        """Posterior probability that the true rate is at least ``rate``."""
        return 1.0 - regularized_beta(min(max(rate, 0.0), 1.0), self.alpha, self.beta)

    def sample(self, rng: random.Random | None = None) -> float:
        """Thompson sample from the posterior."""
        return (rng or random).betavariate(max(self.alpha, 1e-6), max(self.beta, 1e-6))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None, **defaults: Any) -> BetaEstimator:
        values = {**defaults, **(data or {})}
        fields = {"alpha", "beta", "forgetting", "prior_alpha", "prior_beta"}
        return cls(**{k: float(v) for k, v in values.items() if k in fields})


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularized incomplete beta (Lentz's method)."""
    tiny, eps = 1e-300, 3e-14
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def regularized_beta(x: float, a: float, b: float) -> float:
    """I_x(a, b): the Beta(a, b) cumulative distribution function at x."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def log_beta(a: float, b: float) -> float:
    """ln B(a, b)."""
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def paired_e_value(wins: int, losses: int, prior: float = 1.0) -> float:
    """Evidence that the first of two versions is better, safe under any stopping.

    Over the pairs where the two versions disagree, one wins with probability q.
    If neither is better, q = ½ whatever their common success rate, so the
    mixture likelihood ratio

        E = ∫_{q>½} Π (q/½)^win ((1−q)/½)^loss dπ(q)
          = 2^n · 2 · B(wins + a, losses + a) / B(a, a) · P(q > ½ | data),

    with π = Beta(a, a) restricted to q > ½, is a test supermartingale under
    "the first is not better" (q ≤ ½). Ville's inequality then bounds the chance
    that E ever reaches 1/α by α, however often it is checked.
    """
    n = wins + losses
    if n == 0:
        return 1.0
    tail = 1.0 - regularized_beta(0.5, wins + prior, losses + prior)
    if tail <= 0.0:
        return 0.0
    log_e = (
        n * math.log(2.0)
        + math.log(2.0)
        + log_beta(wins + prior, losses + prior)
        - log_beta(prior, prior)
        + math.log(tail)
    )
    return math.exp(min(log_e, 700.0))


def thompson_choice(
    options: Sequence[str], posteriors: dict[str, BetaEstimator], rng: random.Random | None = None
) -> str:
    """Pick the option whose posterior sample is highest (explore/exploit balance)."""
    if not options:
        raise ValueError("no options to choose from")
    return max(options, key=lambda key: posteriors.get(key, BetaEstimator()).sample(rng))


# ───── Exponentially weighted statistics ─────


@dataclass
class EWStats:
    """Exponentially weighted mean and variance (West, 1979)."""

    smoothing: float = 0.1
    mean: float = 0.0
    variance: float = 0.0
    count: int = 0

    def update(self, value: float) -> EWStats:
        value = float(value)
        if self.count == 0:
            self.mean, self.variance = value, 0.0
        else:
            delta = value - self.mean
            self.mean += self.smoothing * delta
            self.variance = (1 - self.smoothing) * (self.variance + self.smoothing * delta * delta)
        self.count += 1
        return self

    @property
    def std(self) -> float:
        return math.sqrt(max(self.variance, 0.0))

    def z(self, value: float) -> float:
        """Standard score of ``value`` against the running baseline (0 until warmed up)."""
        if self.count < 3 or self.std < 1e-9:
            return 0.0
        return (float(value) - self.mean) / self.std

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None, **defaults: Any) -> EWStats:
        values = {**defaults, **(data or {})}
        return cls(
            smoothing=float(values.get("smoothing", 0.1)),
            mean=float(values.get("mean", 0.0)),
            variance=float(values.get("variance", 0.0)),
            count=int(values.get("count", 0)),
        )


# ───── Memory activation (ACT-R) ─────


def actr_activation(ages_seconds: Iterable[float], decay: float = 0.5) -> float:
    """Base-level activation B = ln(Σ t_j^-d) over the ages of past accesses.

    Every access contributes, recent ones most; spaced repetition keeps a
    memory active far longer than one recent touch. Ages are floored at 1s.
    """
    total = sum(max(1.0, float(age)) ** -decay for age in ages_seconds)
    return math.log(total) if total > 0 else float("-inf")


def activation_weight(activation: float, threshold: float = -6.0, noise: float = 0.5) -> float:
    """Retrieval probability 1 / (1 + e^-(B - τ)/s) for an activation B."""
    if activation == float("-inf"):
        return 0.0
    return 1.0 / (1.0 + math.exp(-(activation - threshold) / noise))


def approximate_ages(age_seconds: float, accesses: int, created_age_seconds: float) -> list[float]:
    """Spread ``accesses`` evenly between creation and the last access."""
    accesses = max(1, int(accesses))
    first, last = max(created_age_seconds, age_seconds), age_seconds
    if accesses == 1:
        return [last]
    step = (first - last) / (accesses - 1)
    return [last + step * index for index in range(accesses)]


# ───── Relevance (BM25) ─────


def bm25_scores(
    query: str | Sequence[str],
    documents: Sequence[str | Sequence[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Okapi BM25 score of each document for the query."""
    query_terms = tokenize(query) if isinstance(query, str) else list(query)
    docs = [tokenize(doc) if isinstance(doc, str) else list(doc) for doc in documents]
    if not docs or not query_terms:
        return [0.0] * len(docs)
    average = sum(len(doc) for doc in docs) / len(docs) or 1.0
    frequencies = Counter(term for doc in docs for term in set(doc))
    count = len(docs)
    scores = []
    for doc in docs:
        terms = Counter(doc)
        score = 0.0
        for term in set(query_terms):
            tf = terms.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (count - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / average))
        scores.append(score)
    return scores


def normalise(scores: Sequence[float]) -> list[float]:
    top = max(scores, default=0.0)
    return [score / top if top > 0 else 0.0 for score in scores]


# ───── Distributions ─────


def softmax(values: Sequence[float], temperature: float = 1.0) -> list[float]:
    if not values:
        return []
    t = max(float(temperature), 1e-6)
    top = max(values)
    exps = [math.exp((v - top) / t) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


def entropy(probabilities: Sequence[float]) -> float:
    return -sum(p * math.log(p) for p in probabilities if p > 0)


def logistic(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


# ───── Persistence ─────


class AdaptiveStateStore:
    """Named JSON states (estimators, statistics) in one SQLite table."""

    _lock = threading.Lock()

    def __init__(self, db_path: str | None):
        self.db_path = db_path
        self._memory: dict[str, dict] = {}
        if db_path:
            with self._connect() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS adaptive_state ("
                    "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=5)

    def get(self, key: str) -> dict | None:
        if not self.db_path:
            return self._memory.get(key)
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT value FROM adaptive_state WHERE key = ?", (key,)
                ).fetchone()
        except sqlite3.Error:
            return self._memory.get(key)
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict) -> None:
        from memory import stateless

        if not stateless.learns():
            return  # an evaluation, or a user who turned learning off (memory/stateless.py)
        self._memory[key] = value
        if not self.db_path:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO adaptive_state VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE "
                    "SET value = excluded.value, updated_at = excluded.updated_at",
                    (key, json.dumps(value), datetime.now(UTC).isoformat()),
                )
        except sqlite3.Error:
            pass  # in-memory copy still serves this process

    def beta(self, key: str, **defaults: Any) -> BetaEstimator:
        return BetaEstimator.from_dict(self.get(key), **defaults)

    def stats(self, key: str, **defaults: Any) -> EWStats:
        return EWStats.from_dict(self.get(key), **defaults)
