"""Tahiyya (تحية): is a message a salam, and nothing else? (4:86)

When greeted, the Quran commands returning a better greeting or the same
(4:86). MIZAN returns a salam itself, with no model call, but only a message
that is a salam alone: a salam with a request, a returned salam ("Walaikum
assalam") or a question about the salam goes on as usual.

Qasd cannot tell these apart: it reads a message as a bag of letter n-grams
inside its words, so "Assalamualaikum", "Assalamualaikum, kaise ho?" and
"Walaikum assalam" share almost every feature (two pre-registered rounds,
docs/fahm.md "Salam (4:86)"). Tahiyya reads the whole message, in order:

- Three readers, each interpolated Witten–Bell character n-grams over whole
  messages, from a start mark to an end mark, so word order and anything said
  after the salam are evidence: F, salam formulas (``data/tahiyya/salam.tsv``);
  R, returned salams (``data/tahiyya/returned.tsv``), a speech act of their
  own whose "wa …" would otherwise read as part of a salam; O, ordinary speech
  (the Lughah corpora without quotes and names, Qasd's seeds and facet rows,
  and salams with a request and questions about the salam in
  ``data/tahiyya/other.tsv``).
- Each reader also reads the message's first word alone, a second view: the
  opening word is what marks a reply ("Walaikum …") apart from a salam
  ("Assalamualaikum …") when both go on with the same address or blessing.
- P(k | x) ∝ π_k · exp(a · log P_k(x) · (n/ñ)^−γ + b · log P_k(first word))
  over the three: Bayes, with π_k each reader's share of the messages people
  send (formulas, returned salams and the requests above), so a message with
  no evidence stays at the prior. Characters are not independent, so each
  view's evidence is tempered (a, b) and, as Tamyiz weighs a long message's
  text, the whole-message view is divided by (n/ñ)^γ (n the message's length,
  ñ the median); a, b and γ are fitted by leave-one-out log-loss, each row
  taken out of its own reader while it is read, and so are the two n-gram
  orders.
- A salam when P(F | x) > ½ (more probable than both others together); no
  word list, cue or threshold.

The fit is cached by the data's SHA-256 in ``core/data/tahiyya.json``; after
editing the data run ``cd backend && python -m tadbir.tahiyya --fit``.
``MIZAN_TAHIYYA=off`` turns the reader off.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import threading
import unicodedata
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent / "data" / "tahiyya"
FIT = Path(__file__).resolve().parents[1] / "core" / "data" / "tahiyya.json"
ORDERS = (3, 4, 5)
GAMMAS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
_BEGIN, _END = "\x02", "\x03"
# Qasd seeds that are a salam alone (labelled conversation before the salam rounds).
_BARE_SALAM_SEEDS = frozenset({"Assalamualaikum dost", "السلام عليكم يا صديقي"})


def enabled() -> bool:
    return os.getenv("MIZAN_TAHIYYA", "on").strip().lower() != "off"


def normalize(text: str) -> str:
    """Letters and marks, case folded; Arabic vowel marks and the tatweel are
    set aside (a vowelled salam is the same salam); the rest is one space."""
    kept = []
    for char in unicodedata.normalize("NFKC", text or "").casefold():
        if "ً" <= char <= "ٟ" or char in "ٰـ":
            continue
        kept.append(char if unicodedata.category(char)[0] in "LM" else " ")
    return " ".join("".join(kept).split())


class CharModel:
    """Interpolated Witten–Bell character n-grams over whole messages."""

    def __init__(self, order: int, texts: Sequence[str] = ()) -> None:
        self.order = order
        self.counts: dict[str, Counter[str]] = {}
        self.seen: Counter[str] = Counter()  # times each context is followed
        self.kinds: Counter[str] = Counter()  # distinct characters after each context
        self.alphabet: Counter[str] = Counter()
        for text in texts:
            self.add(text, 1)

    def _events(self, text: str) -> Iterator[tuple[str, str]]:
        padded = _BEGIN * (self.order - 1) + text + _END
        for index in range(self.order - 1, len(padded)):
            yield padded[index - self.order + 1 : index], padded[index]

    def add(self, text: str, sign: int) -> None:
        """Count a message in (sign 1) or out (sign -1)."""
        for history, char in self._events(text):
            self.alphabet[char] += sign
            for k in range(len(history) + 1):
                context = history[len(history) - k :]
                found = self.counts.setdefault(context, Counter())
                before = found[char]
                found[char] = before + sign
                self.seen[context] += sign
                if sign > 0 and before == 0:
                    self.kinds[context] += 1
                elif sign < 0 and before + sign == 0:
                    self.kinds[context] -= 1

    def _p(self, history: str, char: str, base: float) -> float:
        p = base
        for k in range(len(history) + 1):
            context = history[len(history) - k :]
            seen, kinds = self.seen.get(context, 0), self.kinds.get(context, 0)
            if seen + kinds <= 0:
                continue
            found = self.counts.get(context)
            p = ((found.get(char, 0) if found else 0) + kinds * p) / (seen + kinds)
        return p

    def logp(self, text: str, base: float) -> float:
        return sum(math.log(self._p(history, char, base)) for history, char in self._events(text))


def _rows(name: str) -> list[str]:
    return [
        line.strip()
        for line in (DATA / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


KINDS = ("salam", "returned", "other")


def corpora() -> dict[str, list[str]]:
    """Each reader's messages, normalized: salam formulas, returned salams, the
    messages people send that are neither (``other``), and the rest of ordinary
    speech (``speech``, read by O but not a message to MIZAN)."""
    from . import lughah, qasd

    formulas = [normalize(text) for text in _rows("salam.tsv")]
    returned = [normalize(text) for text in _rows("returned.tsv")]
    sent = [
        normalize(qasd._text(text))
        for _label, text in qasd._rows("intents.tsv")
        if text not in _BARE_SALAM_SEEDS
    ]
    sent += [normalize(qasd._text(text)) for _facet, _label, text in qasd._rows("facets.tsv")]
    sent += [normalize(text) for text in _rows("other.tsv")]
    speech = [normalize(text) for text, label in lughah.shipped() if label not in {"quote", "name"}]
    # A message that is a formula or a returned salam is that wherever else it
    # is a seed (the facets hold "Assalamualaikum" as not about the deen).
    known = set(formulas) | set(returned)
    return {
        "salam": [t for t in formulas if t],
        "returned": [t for t in returned if t and t not in set(formulas)],
        "other": [t for t in sent if t and t not in known],
        "speech": [t for t in speech if t and t not in known],
    }


def digest() -> str:
    found = corpora()
    blob = json.dumps([list(ORDERS), list(GAMMAS), found], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _first(text: str) -> str:
    return text.split(" ", 1)[0]


def _models(order: int, found: dict[str, list[str]]) -> dict[str, CharModel]:
    return {
        "salam": CharModel(order, found["salam"]),
        "returned": CharModel(order, found["returned"]),
        "other": CharModel(order, [*found["other"], *found["speech"]]),
    }


def _first_models(order: int, found: dict[str, list[str]]) -> dict[str, CharModel]:
    return {
        kind: CharModel(order, [_first(t) for t in model_texts])
        for kind, model_texts in (
            ("salam", found["salam"]),
            ("returned", found["returned"]),
            ("other", [*found["other"], *found["speech"]]),
        )
    }


def _base(*readers: dict[str, CharModel]) -> float:
    """One floor for every reader: an unseen character among those any knows."""
    letters: set[str] = set()
    for models in readers:
        for model in models.values():
            letters |= {char for char, n in model.alphabet.items() if n > 0}
    return 1.0 / (len(letters) + 1)


Row = tuple[str, dict[str, float], dict[str, float], int]


def _posterior(
    whole: dict[str, float], first: dict[str, float], length: int, fitted: dict
) -> dict[str, float]:
    """P(k | x) ∝ π_k · exp(a · log P_k(x) · (n/ñ)^−γ + b · log P_k(first word))."""
    scale = fitted["a"] * (max(1, length) / fitted["ref"]) ** (-fitted["gamma"])
    scores = {
        k: math.log(fitted["prior"][k]) + scale * whole[k] + fitted["b"] * first[k] for k in KINDS
    }
    top = max(scores.values())
    total = sum(math.exp(v - top) for v in scores.values())
    return {k: math.exp(v - top) / total for k, v in scores.items()}


def _held_out(order: int, first_order: int) -> list[Row]:
    """(true kind, log P of the message and of its first word under each reader,
    with the row taken out of its own reader, length)."""
    found = corpora()
    whole, opening = _models(order, found), _first_models(first_order, found)
    base = _base(whole, opening)
    rows = []
    for kind in KINDS:
        for text in found[kind]:
            whole[kind].add(text, -1)
            opening[kind].add(_first(text), -1)
            rows.append(
                (
                    kind,
                    {k: whole[k].logp(text, base) for k in KINDS},
                    {k: opening[k].logp(_first(text), base) for k in KINDS},
                    len(text) + 1,
                )
            )
            whole[kind].add(text, 1)
            opening[kind].add(_first(text), 1)
    return rows


def _fit_rows(rows: list[Row]) -> dict:
    """π from the counts; γ, a and b minimising the mean leave-one-out log-loss
    (a and b by alternating golden-section searches)."""
    from core.tamyiz import _golden

    counts = {k: sum(1 for row in rows if row[0] == k) for k in KINDS}
    prior = {k: counts[k] / len(rows) for k in KINDS}
    lengths = sorted(row[3] for row in rows)
    ref = float(lengths[len(lengths) // 2])

    def loss(a: float, b: float, gamma: float) -> float:
        fitted = {"a": a, "b": b, "gamma": gamma, "ref": ref, "prior": prior}
        total = 0.0
        for kind, whole, first, length in rows:
            total -= math.log(max(1e-300, _posterior(whole, first, length, fitted)[kind]))
        return total / len(rows)

    best: dict | None = None
    for gamma in GAMMAS:
        a, b = 0.2, 0.0
        for _ in range(3):
            a = _golden(lambda x, b=b, gamma=gamma: loss(x, b, gamma), 0.0, 1.0)
            b = _golden(lambda x, a=a, gamma=gamma: loss(a, x, gamma), 0.0, 1.0)
        found = {
            "a": a,
            "b": b,
            "gamma": gamma,
            "ref": ref,
            "prior": prior,
            "loo_loss": loss(a, b, gamma),
        }
        if best is None or found["loo_loss"] < best["loo_loss"]:
            best = found
    assert best is not None
    return best


def fit() -> dict:
    """The two orders, π, a, b and γ, chosen by leave-one-out log-loss."""
    best: dict | None = None
    for order in ORDERS:
        for first_order in ORDERS:
            rows = _held_out(order, first_order)
            fitted = _fit_rows(rows)
            said = [_posterior(w, f, n, fitted)["salam"] > 0.5 for _k, w, f, n in rows]

            def share(kind: str, said: list[bool] = said, rows: list[Row] = rows) -> float:
                xs = [s for s, row in zip(said, rows, strict=True) if row[0] == kind]
                return round(sum(xs) / max(1, len(xs)), 6)

            found = {
                "order": order,
                "first_order": first_order,
                **fitted,
                "loo_loss": round(fitted["loo_loss"], 6),
                "formulas_read": share("salam"),
                "returned_read_as_salam": share("returned"),
                "others_read_as_salam": share("other"),
            }
            logger.info("Tahiyya orders %d/%d: %s", order, first_order, found)
            if best is None or found["loo_loss"] < best["loo_loss"]:
                best = found
    assert best is not None
    best.update({"sha256": digest(), **{f"rows_{k}": len(v) for k, v in corpora().items()}})
    return best


class Reader:
    def __init__(self, fitted: dict) -> None:
        found = corpora()
        self.fitted = fitted
        self.whole = _models(int(fitted["order"]), found)
        self.opening = _first_models(int(fitted["first_order"]), found)
        self.base = _base(self.whole, self.opening)

    def posterior(self, message: str) -> float:
        text = normalize(message)
        if not text:
            return 0.0
        whole = {k: self.whole[k].logp(text, self.base) for k in KINDS}
        first = {k: self.opening[k].logp(_first(text), self.base) for k in KINDS}
        return _posterior(whole, first, len(text) + 1, self.fitted)["salam"]


_lock = threading.Lock()
_reader: Reader | None = None


def reader() -> Reader:
    global _reader
    with _lock:
        if _reader is None:
            fitted = None
            try:
                fitted = json.loads(FIT.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                fitted = None
            if not fitted or fitted.get("sha256") != digest():
                logger.warning("Tahiyya: the shipped fit is not of this data; refitting")
                fitted = fit()
            _reader = Reader(fitted)
        return _reader


def posterior(message: str) -> float:
    """P(the message is a salam and nothing else)."""
    return reader().posterior(message) if enabled() else 0.0


def reads_salam(message: str) -> bool:
    return posterior(message) > 0.5


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit Tahiyya and write core/data/tahiyya.json")
    parser.add_argument("--fit", action="store_true")
    args = parser.parse_args()
    if args.fit:
        logging.basicConfig(level=logging.INFO)
        found = fit()
        FIT.write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(found, indent=1))


if __name__ == "__main__":
    main()
