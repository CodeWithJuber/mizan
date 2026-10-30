"""Measure Qāmūs where MIZAN uses it: ``ahl_dhikr.about(claim, sentence)``.

Does ``about()`` accept a claim written in Hindi or Urdu (and Arabic, Tamil)
for the English sentence that says it, and refuse English sentences that do
not? Two held-out sets, neither used to build the lexicon:

- FLORES-101 devtest (CC BY-SA 4.0): 1,012 English sentences from Wikinews,
  Wikijunior and Wikivoyage, with professional translations. Encyclopedic
  sentences, read here as the facts a source states, and their translations
  as the claims an answer makes. Unrelated means from another article.
- MASSIVE's test split (CC BY 4.0), whose train split built the lexicon. Only
  utterances with no localised slot are used: the others say something else.
  Unrelated means of another intent (MASSIVE holds many near-identical
  requests of one intent, which are about the same thing).

For each claim:

- accepted: ``about(claim, its English sentence)``, with Qāmūs and without;
- false accepts, random: ``about(claim, s)`` for ``--negatives`` unrelated
  English sentences drawn at random (seeded);
- false accepts, hard: the three unrelated English sentences sharing the most
  with the claim and its Qāmūs bridge by BM25, which a cross-lingual search
  would return first;
- reference ("English claim"): the same random and hard sentences read against
  the claim's own English sentence by the existing same-language rule;
- reached: whether its English sentence scores above 0 by BM25 against the
  claim as ``judge()`` ranks sentences now (the claim's own words), and
  against the claim with its bridge; ``judge()`` reads only sentences with a
  score above 0, so "accepted through judge" counts claims accepted and
  reached by the claim's own words.

Rates are given with 95% Wilson intervals. Data is downloaded into ``--data``,
a new folder outside the repository; run with ``python -I``:

    python -I scripts/qamus_eval.py --data /tmp/qamus_eval --massive /tmp/qamus_data
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_qamus  # noqa: E402

from core.adaptive import bm25_scores, tokenize, wilson_bounds  # noqa: E402
from tadbir import ahl_dhikr, qamus  # noqa: E402

FLORES = "gsarti/flores_101"
FLORES_REVISION = "1a45e707ea4b5ea3d6c71341f18bfca6a6e356a3"  # refs/convert/parquet
FLORES_CODES = {"en": "eng", "hi": "hin", "ur": "urd", "ar": "ara", "ta": "tam"}
HARD = 3  # as many sentences as judge() reads per claim (ahl_dhikr.CANDIDATES)


def flores(data: Path, language: str) -> tuple[list[str], list[str]]:
    """The devtest sentences in id order, and the article each comes from."""
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        FLORES,
        f"{FLORES_CODES[language]}/devtest/0000.parquet",
        repo_type="dataset",
        revision=FLORES_REVISION,
        local_dir=str(data / "flores"),
    )
    table = pq.read_table(path, columns=["id", "URL", "sentence"])
    rows = sorted(table.to_pylist(), key=lambda row: row["id"])
    return [str(row["sentence"]) for row in rows], [str(row["URL"]) for row in rows]


def massive(data: Path, language: str) -> tuple[list[str], list[str], list[str]]:
    """English and other test utterances with no localised slot, in id order,
    and the intent of each."""
    locale = build_qamus.LOCALES[language]
    english = build_qamus.read(build_qamus.fetch(data, build_qamus.ENGLISH)["test"])
    other = build_qamus.read(build_qamus.fetch(data, locale)["test"])
    kept = [
        i
        for i in sorted(set(english) & set(other), key=int)
        if not any(
            "localization" in how for hows in build_qamus.methods(other[i]).values() for how in hows
        )
    ]
    return (
        [english[i]["utt"] for i in kept],
        [other[i]["utt"] for i in kept],
        [str(english[i]["intent"]) for i in kept],
    )


def about(claim: str, sentence: str, *, bridged: bool) -> bool:
    os.environ["MIZAN_QAMUS"] = "on" if bridged else "off"
    return ahl_dhikr.about(claim, sentence)


def rate(hits: int, total: int) -> dict:
    low, high = wilson_bounds(hits, total)
    return {
        "hits": hits,
        "n": total,
        "rate": round(hits / total, 4) if total else 0.0,
        "wilson95": [round(low, 4), round(high, 4)],
    }


def measure(
    english: list[str], claims: list[str], groups: list[str], negatives: int, seed: int
) -> dict:
    """``groups[i]`` is what sentence i is about (its article, its intent):
    sentences of another group are the unrelated ones."""
    rng = random.Random(seed)
    documents = [tokenize(sentence) for sentence in english]
    found = {
        "pairs": len(claims),
        "accepted": {"qamus": 0, "without": 0},
        "random": {"qamus": [0, 0], "without": [0, 0], "english": [0, 0]},
        "hard": {"qamus": [0, 0], "without": [0, 0], "english": [0, 0]},
        "reached": {"claim": 0, "bridged": 0},
        "through_judge": {"qamus": 0, "without": 0},
    }
    for index, claim in enumerate(claims):
        own = tokenize(claim)
        reached = bm25_scores(own, documents)[index] > 0
        found["reached"]["claim"] += reached
        for mode, bridged in (("qamus", True), ("without", False)):
            accepted = about(claim, english[index], bridged=bridged)
            found["accepted"][mode] += accepted
            found["through_judge"][mode] += accepted and reached
        os.environ["MIZAN_QAMUS"] = "on"
        bridge = qamus.bridge(claim, "en")
        scores = bm25_scores(own + bridge, documents)
        found["reached"]["bridged"] += scores[index] > 0
        others = [i for i in range(len(english)) if groups[i] != groups[index]]
        hard = sorted((i for i in others if scores[i] > 0), key=lambda i: -scores[i])[:HARD]
        drawn = rng.sample(others, min(negatives, len(others)))
        readers = (
            ("qamus", claim, True),
            ("without", claim, False),
            ("english", english[index], True),
        )
        for mode, said, bridged in readers:
            for kind, chosen in (("random", drawn), ("hard", hard)):
                found[kind][mode][0] += sum(
                    about(said, english[i], bridged=bridged) for i in chosen
                )
                found[kind][mode][1] += len(chosen)
    pairs = found["pairs"]
    return {
        "pairs": pairs,
        "accepted": {mode: rate(hits, pairs) for mode, hits in found["accepted"].items()},
        "false_accept_random": {mode: rate(*counts) for mode, counts in found["random"].items()},
        "false_accept_hard": {mode: rate(*counts) for mode, counts in found["hard"].items()},
        "reached_by_bm25": {mode: rate(hits, pairs) for mode, hits in found["reached"].items()},
        "accepted_through_judge": {
            mode: rate(hits, pairs) for mode, hits in found["through_judge"].items()
        },
    }


def show(name: str, result: dict) -> None:
    def cell(entry: dict) -> str:
        low, high = entry["wilson95"]
        return f"{entry['rate']:.3f} [{low:.3f}, {high:.3f}] ({entry['hits']}/{entry['n']})"

    print(f"{name}: {result['pairs']} claims")
    for key in ("accepted", "accepted_through_judge", "false_accept_random", "false_accept_hard"):
        row = result[key]
        line = f"  {key:<20} Qamus {cell(row['qamus'])}   without {cell(row['without'])}"
        if "english" in row:
            line += f"   English claim {cell(row['english'])}"
        print(line)
    reached = result["reached_by_bm25"]
    print(
        f"  {'reached_by_bm25':<20} claim {cell(reached['claim'])}   bridged {cell(reached['bridged'])}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="a folder outside the repository for FLORES")
    parser.add_argument(
        "--massive", required=True, help="the folder build_qamus.py downloaded into"
    )
    parser.add_argument("--languages", default="hi,ur,ar,ta")
    parser.add_argument(
        "--negatives", type=int, default=20, help="random unrelated sentences per claim"
    )
    parser.add_argument("--seed", type=int, default=16043)
    parser.add_argument("--json", default="", help="also write the results here")
    args = parser.parse_args()
    data, sentences = Path(args.data).resolve(), Path(args.massive).resolve()
    for folder in (data, sentences):
        if ROOT in folder.parents or folder == ROOT:
            parser.error("data folders must be outside the repository")
    results: dict[str, dict] = {}
    english, articles = flores(data, "en")
    for language in [item.strip() for item in args.languages.split(",") if item.strip()]:
        name = f"flores {language}>en"
        claims, _ = flores(data, language)
        results[name] = measure(english, claims, articles, args.negatives, args.seed)
        show(name, results[name])
        name = f"massive {language}>en"
        results[name] = measure(*massive(sentences, language), args.negatives, args.seed)
        show(name, results[name])
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
