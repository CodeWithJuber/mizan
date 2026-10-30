"""Qāmūs (قاموس): MIZAN's own cross-lingual lexicon.

A word written in one language is matched against text in another by the words
it translates to. MIZAN learns the lexicon itself from parallel sentences:
MASSIVE 1.1 (Amazon, CC BY 4.0) holds the same utterances in 52 languages,
aligned by id, and English is paired with Hindi (Devanagari), Urdu, Arabic and
Tamil (``data/qamus/LICENSES.md``). No word list is written by hand. A slot the
translator localised ("the time in London" became "the time in Delhi") is not
a translation, so its words are left out of the pair.

For each pair, IBM Model 1 is trained by EM in both directions. Each sentence's
source side has a NULL word, which produces the target words that no source
word produced (particles, case endings). With c(f, e) the expected number of
times e produced f:

    E step:  c(f, e) += t(f | e) / Σ_{e' in E ∪ NULL} t(f | e')   for each f in F, e in E ∪ NULL
    M step:  t(f | e) = c(f, e) / Σ_f' c(f', e)

EM stops at the iteration with the highest log-likelihood of the held-out
pairs (MASSIVE's validation split). The two directions are then multiplied, so
a pair is kept only when each word is what the other is most often written as:

    P(e | x) = t(e | x) · t(x | e) / Σ_e' t(e' | x) · t(x | e')

and likewise P(x | e). A translation is kept when its P is at least a cut-off
τ, chosen per direction as the one that maximises F1 against a held-out
dictionary: in MASSIVE's validation split, a slot (a date, a device, a
number) that occurs once on each side, was translated rather than localised,
and is one word on each side, pairs those two words. The test split's
dictionary measures precision@1. A word copied unchanged into the other side
(a name left in Latin letters) is matched as it is and not stored.

Names are written, not translated: a pair with a name on either side (a word
localisation swaps) is kept only when both words are entities and one sounds
like the other (``sounds_alike``, cut-off by ``youden``), so "mumbai" is never
read as "गोवा". Pieces of a word written apart ("پا کستا ن") are not words
(``pieces``). A pair counts when either direction's lexicon holds it.
``scripts/build_qamus.py`` builds the files and ``--check`` rebuilds them and
compares their SHA-256; ``scripts/qamus_eval.py`` measures ``about()`` with it
(``docs/qamus.md``).

``MIZAN_QAMUS``: ``on`` (default) or ``off``.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import cache
from pathlib import Path

from core.adaptive import tokenize, wilson_bounds

DATA = Path(__file__).parent / "data" / "qamus"
FORMAT = "mizan-qamus/1"
NULL = ""  # the empty word: no token is empty, so it never meets a real word
Table = dict[str, dict[str, float]]


def enabled() -> bool:
    return os.getenv("MIZAN_QAMUS", "on").strip().lower() != "off"


# ── reading words and scripts ─────────────────────────────────────────────


def tokens(text: str) -> list[str]:
    """The words of a text, in one Unicode form (NFC), lower-cased, without
    invisible format characters (Unicode category Cf: direction marks,
    joiners). Unicode's word boundaries ignore them inside a word, but ``\\w``
    stops at them: "جا‎ۓ" with a left-to-right mark inside was read as "جا"
    and "ۓ"."""
    words: list[str] = tokenize(_visible(text))
    return words


def _visible(text: str) -> str:
    normal = unicodedata.normalize("NFC", text or "")
    return "".join(char for char in normal if unicodedata.category(char) != "Cf")


def _key(word: str) -> str:
    """A word as the lexicon stores it."""
    return _visible(word).lower()


@cache
def _letter_script(char: str) -> str:
    try:
        return unicodedata.name(char).split(" ")[0]
    except ValueError:
        return ""


def script(word: str) -> str:
    """The script a word is written in: the first word of its first letter's
    Unicode name ("LATIN", "DEVANAGARI", "ARABIC", "TAMIL"), or "" for none."""
    for char in word:
        if char.isalpha():
            return _letter_script(char)
    return ""


def script_of(text: str) -> str:
    """The script most of a text's letters are written in."""
    counts = Counter(_letter_script(char) for char in text or "" if char.isalpha())
    return counts.most_common(1)[0][0] if counts else ""


def _ascii_digits(word: str) -> str:
    """A number written in another script's digits, in ASCII digits: a digit
    is the same number in every script (Unicode's decimal values)."""
    if word.isdecimal() and not word.isascii():
        return "".join(str(unicodedata.decimal(char)) for char in word)
    return ""


# ── learning: IBM Model 1 by EM ───────────────────────────────────────────


def log_likelihood(table: Table, pairs: Sequence[tuple[Sequence[str], Sequence[str]]]) -> float:
    """log P(F | E) of the pairs under the model, over target words it knows.

    P(F | E) = Π_f (1 / (|E| + 1)) Σ_{e in E ∪ NULL} t(f | e); a target word the
    training pairs never held (no t(f | NULL)) is left out, so the same words
    are counted at every iteration."""
    known = table.get(NULL, {})
    total = 0.0
    for source, target in pairs:
        sources = (NULL, *source)
        for f in target:
            if f not in known:
                continue
            p = sum(table.get(e, {}).get(f, 0.0) for e in sources)
            if p > 0:
                total += math.log(p / len(sources))
    return total


def ibm1(
    pairs: Sequence[tuple[Sequence[str], Sequence[str]]],
    heldout: Sequence[tuple[Sequence[str], Sequence[str]]] = (),
    *,
    limit: int = 100,
) -> tuple[Table, list[float]]:
    """IBM Model 1 trained by EM: t(f | e), how often source word e (or NULL)
    is written as target word f. Returns the table and the log-likelihood after
    each iteration (the first is the uniform start).

    EM stops when the log-likelihood of ``heldout`` (of ``pairs`` when none is
    given) no longer increases, and the best table is returned. ``limit`` only
    bounds the run; the builder reports the iterations used."""
    vocabulary = {f for _source, target in pairs for f in target}
    uniform = 1.0 / max(1, len(vocabulary))
    table: Table = {}
    for source, target in pairs:
        for e in (NULL, *source):
            row = table.setdefault(e, {})
            for f in target:
                row[f] = uniform
    judged = heldout or pairs
    trace = [log_likelihood(table, judged)]
    for _ in range(limit):
        counts: Table = {e: dict.fromkeys(row, 0.0) for e, row in table.items()}
        totals = dict.fromkeys(table, 0.0)
        for source, target in pairs:
            sources = (NULL, *source)
            for f in target:
                z = sum(table[e][f] for e in sources)
                for e in sources:
                    share = table[e][f] / z
                    counts[e][f] += share
                    totals[e] += share
        fitted = {
            e: {f: count / totals[e] for f, count in row.items()}
            for e, row in counts.items()
            if totals[e] > 0
        }
        score = log_likelihood(fitted, judged)
        if score <= trace[-1]:
            break
        table = fitted
        trace.append(score)
    return table, trace


def symmetrise(there: Table, back: Table) -> Table:
    """P(b | a) ∝ t(b | a) · t(a | b) for each word a, from ``there`` = t(b | a)
    and ``back`` = t(a | b): a pair both directions agree on."""
    found: Table = {}
    for a, row in there.items():
        if a == NULL:
            continue
        scores = {b: p * back.get(b, {}).get(a, 0.0) for b, p in row.items()}
        total = sum(scores.values())
        if total > 0:
            found[a] = {b: score / total for b, score in scores.items() if score > 0}
    return found


def cutoff(shares: Table, gold: dict[str, set[str]]) -> tuple[float, float]:
    """The cut-off τ on P(b | a) that maximises F1 against a held-out
    dictionary, and that F1. Every translation of a dictionary word with
    P ≥ τ is a prediction; precision is the share of predictions the
    dictionary holds, recall the share of the dictionary's pairs predicted.
    Of equal F1, the highest τ (fewest translations) is taken."""
    predicted = sorted(
        ((p, b in gold[a]) for a in gold for b, p in shares.get(a, {}).items()),
        key=lambda item: -item[0],
    )
    relevant = sum(len(targets) for targets in gold.values())
    best = (0.0, 1.0)  # (F1, τ)
    hits = 0
    for index, (p, hit) in enumerate(predicted):
        hits += hit
        if index + 1 < len(predicted) and predicted[index + 1][0] == p:
            continue  # a cut-off keeps every translation of equal P
        precision, recall = hits / (index + 1), hits / relevant if relevant else 0.0
        f1 = 2 * precision * recall / (precision + recall) if hits else 0.0
        if f1 > best[0]:
            best = (f1, p)
    return best[1], best[0]


def lower_bounds(shares: Table, held: Mapping[str, int]) -> Table:
    """Each P(b | a) as the 95% Wilson lower bound of P·n in n, n the number of
    sentences that hold a: a pair seen in one sentence is not yet known, however
    sure that sentence makes it. Within a word the order is P's."""
    return {
        a: {b: wilson_bounds(p * held.get(a, 0), held.get(a, 0))[0] for b, p in row.items()}
        for a, row in shares.items()
    }


def keep(
    shares: Table, tau: float, by: Table | None = None, digits: int = 3
) -> dict[str, list[list]]:
    """Each word's translations whose score (``by``, else P) is at least the
    cut-off, with their P, most probable first."""
    scores = by if by is not None else shares
    kept: dict[str, list[list]] = {}
    for a in sorted(shares):
        row = sorted(
            ((b, p) for b, p in shares[a].items() if scores.get(a, {}).get(b, 0.0) >= tau),
            key=lambda item: (-item[1], item[0]),
        )
        if row:
            kept[a] = [[b, round(p, digits)] for b, p in row]
    return kept


def precision_at_1(lexicon: dict[str, list[list]], gold: dict[str, set[str]]) -> dict:
    """Of the dictionary's words the lexicon holds, how many have the right
    translation first; and how many of its words it holds at all."""
    held = [word for word in gold if lexicon.get(word)]
    correct = sum(1 for word in held if lexicon[word][0][0] in gold[word])
    return {"words": len(gold), "held": len(held), "correct": correct}


# ── names: a name is written, not translated ──────────────────────────────
#
# A name is carried into another script by its sounds ("john", "जॉन"), so a
# pair of names is a translation only when one is a transliteration of the
# other. A pair learned from a sentence in which the translator put another
# name in its place ("the time in London", "दिल्ली में समय") is not one.


def skeleton(romanised: str) -> str:
    """A romanised word's consonants, each run written once: transliteration
    keeps a name's consonants and changes its vowels ("jon", "john" → "jn")."""
    letters = "".join(char for char in romanised.lower() if "a" <= char <= "z")
    found: list[str] = []
    for char in letters:
        if char not in "aeiou" and (not found or found[-1] != char):
            found.append(char)
    return "".join(found)


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance: insertions, deletions and substitutions."""
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def sounds_alike(a: str, b: str) -> float:
    """How alike two romanised words sound: 1 − the edit distance of their
    consonant skeletons over the longer skeleton's length."""
    x, y = skeleton(a), skeleton(b)
    if not x or not y:
        return float(x == y)
    return 1.0 - edit_distance(x, y) / max(len(x), len(y))


def youden(positives: Sequence[float], negatives: Sequence[float]) -> tuple[float, float]:
    """A cut-off σ on a score by Youden's J = TPR − FPR, and its J.

    When some "positives" are in truth drawn like the negatives (a slot marked
    as translated that held another name), TPR = π·T + (1 − π)·FPR, so
    J = π·(T − FPR): its best σ does not move with the share π, as F1's does.

    With a few dozen pairs J is flat near its best, so the σ taken is the
    highest whose J is within one standard error of the best J (the
    one-standard-error rule): the strictest cut-off the data cannot tell from
    the best, since keeping an unrelated name costs more than losing a name."""
    n_pos, n_neg = max(1, len(positives)), max(1, len(negatives))
    curve = []
    for sigma in sorted(set(positives) | set(negatives)):
        tpr = sum(score >= sigma for score in positives) / n_pos
        fpr = sum(score >= sigma for score in negatives) / n_neg
        curve.append((sigma, tpr, fpr))
    if not curve:
        return 1.0, 0.0
    _sigma, tpr, fpr = max(curve, key=lambda point: (point[1] - point[2], point[0]))
    error = math.sqrt(tpr * (1 - tpr) / n_pos + fpr * (1 - fpr) / n_neg)
    sigma, tpr, fpr = max(
        (point for point in curve if point[1] - point[2] >= tpr - fpr - error),
        key=lambda point: point[0],
    )
    return sigma, tpr - fpr


# ── pieces: a token that is part of a word ────────────────────────────────


def pieces(sentences: Iterable[Sequence[str]]) -> set[str]:
    """Tokens that are pieces of a word written apart ("پا کستا ن" for
    "پاکستان", "what 's" for "whats"), not words of their own.

    A run of adjacent tokens is joinable when, written together, it is a token
    the corpus holds. A token is a piece when the corpus holds the whole word
    it is most often part of more often than it holds the token standing alone
    (outside every joinable run): "کستا" never stands alone, while "कौन" (who)
    stands alone more often than "कौनसा" is written closed."""
    sentences = [list(sentence) for sentence in sentences]
    vocabulary = Counter(word for sentence in sentences for word in sentence)
    longest = max((len(word) for word in vocabulary), default=0)
    alone: Counter = Counter()
    wholes: dict[str, Counter] = {}
    for sentence in sentences:
        inside: dict[int, str] = {}
        for start in range(len(sentence)):
            joined = sentence[start]
            for end in range(start + 1, len(sentence)):
                joined += sentence[end]
                if len(joined) > longest:
                    break
                if joined in vocabulary:
                    for position in range(start, end + 1):
                        if len(joined) > len(inside.get(position, "")):
                            inside[position] = joined
        for position, word in enumerate(sentence):
            if position in inside:
                wholes.setdefault(word, Counter())[inside[position]] += 1
            else:
                alone[word] += 1
    found = set()
    for word, parts_of in wholes.items():
        whole = parts_of.most_common(1)[0][0]
        if vocabulary[whole] > alone[word]:
            found.add(word)
    return found


# ── using the shipped lexicon ─────────────────────────────────────────────


Entry = tuple[tuple[str, float], ...]


@cache
def _load() -> tuple[dict[tuple[str, str], dict[str, Entry]], dict[str, str]]:
    """Every shipped direction's lexicon, and the script each language is written in."""
    lexicons: dict[tuple[str, str], dict[str, Entry]] = {}
    scripts: dict[str, str] = {}
    for path in sorted(DATA.glob("*.json.gz")):
        data = json.loads(gzip.decompress(path.read_bytes()))
        if data.get("format") != FORMAT:
            continue
        scripts.update(data.get("scripts") or {})
        for direction, entries in (data.get("lexicon") or {}).items():
            source, _, target = direction.partition(">")
            lexicons[(source, target)] = {
                word: tuple((str(b), float(p)) for b, p in row) for word, row in entries.items()
            }
    return lexicons, scripts


@cache
def _reverse() -> dict[tuple[str, str], dict[str, tuple[str, ...]]]:
    """For each direction s>t, the s-words each t-word is a translation of."""
    found: dict[tuple[str, str], dict[str, list[str]]] = {}
    for (source, target), entries in _load()[0].items():
        index = found.setdefault((source, target), {})
        for word, row in entries.items():
            for translation, _p in row:
                index.setdefault(translation, []).append(word)
    return {key: {k: tuple(v) for k, v in index.items()} for key, index in found.items()}


def languages() -> dict[str, str]:
    """Each language the lexicon reads, with its script."""
    return dict(_load()[1])


def translations(word: str, source_lang: str, target_lang: str) -> list[tuple[str, float]]:
    """A word's translations from one language into another, most probable
    first, each with P(translation | word); [] when the lexicon does not hold it."""
    key = _key(word)
    return list(_load()[0].get((source_lang, target_lang), {}).get(key, ()))


def reads(text: str) -> list[str]:
    """The languages the lexicon reads that are written in the text's script."""
    written = script_of(text)
    return [language for language, kind in languages().items() if kind == written]


def translate(word: str, target_lang: str) -> list[str]:
    """A word's translations into a language written in another script, from
    every language written in the word's script (an Arabic-script word may be
    Arabic or Urdu). A word in the target's own script has none.

    A pair counts when either direction's lexicon holds it: "दिल्ली" is read as
    "delhi" because the English lexicon gives "delhi" → "दिल्ली", though the
    Hindi one, cut where its own held-out dictionary put it, does not hold it.
    Both directions come from one symmetrised score and passed the same name
    and piece checks."""
    lexicons, scripts = _load()
    written = script(word)
    if not written or written == scripts.get(target_lang):
        return [_ascii_digits(word)] if _ascii_digits(word) else []
    key = _key(word)
    found: list[str] = []
    for source, kind in scripts.items():
        if kind == written:
            found += [b for b, _p in lexicons.get((source, target_lang), {}).get(key, ())]
            found += _reverse().get((target_lang, source), {}).get(key, ())
    return list(dict.fromkeys(found))


def bridge(text: str, target_lang: str) -> list[str]:
    """The target-language words the text's words translate to, in the text's
    order, each once. Words already in the target's script are not repeated."""
    if not enabled():
        return []
    found: list[str] = []
    for word in tokens(text):
        found += translate(word, target_lang)
    return list(dict.fromkeys(found))


def found_in(
    words: Iterable[str], text: str, counts: Callable[[str], bool] | None = None
) -> set[str]:
    """The words, written in another script than the text, one of whose
    translations into the text's language is a word of the text. ``counts``,
    when given, says which translations are evidence at all (a translation such
    as "the" is in nearly every English sentence).

    A word of the text stands for one of the words at most, the first it
    translates (give the weightiest first), as a word found as it is stands
    for itself: "براہ کرم" are two words for one "please"."""
    if not enabled():
        return set()
    targets = reads(text)
    if not targets:
        return set()
    unused = {word for word in tokens(text) if counts is None or counts(word)}
    found = set()
    for word in words:
        match = next(
            (t for target in targets for t in translate(word, target) if t in unused), None
        )
        if match is not None:
            unused.discard(match)
            found.add(word)
    return found
