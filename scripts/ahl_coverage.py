"""Measure how many of a teacher's claims Ahl al-Dhikr's sources settle.

Each question has a teacher answer and what a source would give for it, read
offline: the articles from a Wikipedia dump (``--wiki``: ``wikimedia/wikipedia``,
one language's parquet, CC BY-SA, downloaded once, never committed) or web
search results captured once (``--pools``: {question: [{title, url, snippet}]},
read with ``ahl_dhikr.web_from``). Claims are taken as ``consult`` takes them,
and each is judged by the real NLI model (``--nli`` names another pinned model
as ``repo@revision:weights:vocabulary``) under each arm:

- ``single``: every candidate premise is one source sentence (``judge`` before
  joint premises);
- ``joint``: also one premise made of the page's best sentences for the claim,
  joined in the page's order, when together they are about the claim
  (``ahl_dhikr.joint_premise``), each claim read with what it speaks of when
  it does not name it (``ahl_dhikr.contexts``, as ``consult`` gives it): what
  ``judge`` does now;
- ``window``: the pool also holds every two consecutive sentences, so "It is…"
  keeps its subject;
- ``joint+window``: both.

``--information gharib`` weighs words by their self-information in their own
language (``tadbir.gharib``) instead of the inverse document frequency in use
(``ahl_dhikr.WORDS``; measured and not adopted, ``docs/ahl-dhikr.md``).

Reported per arm: claims supported and contradicted with 95% Wilson intervals,
the questions Talaqqi would keep (``talaqqi.keep``'s rule), and every claim
whose verdict differs from ``single``, with the premise, for a hand audit.

    cd backend && MIZAN_DATA_DIR=... python ../scripts/ahl_coverage.py \\
        --answers answers.json --wiki simple.parquet --arms single,joint,window,joint+window

``answers.json`` is a list of {"question", "articles": [titles], "answer"}.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core.adaptive import bm25_scores, tokenize, wilson_bounds  # noqa: E402
from tadbir import ahl_dhikr, isnad, muhasaba, talaqqi  # noqa: E402
from tadbir.ahl_dhikr import (  # noqa: E402
    CANDIDATES,
    Finding,
    Passage,
    about,
    nli,
    sentences,
)


def claims_of(answer: str) -> list[str]:
    """The answer's claims, filtered as ``ahl_dhikr.consult`` filters them."""
    return [
        unit["text"]
        for unit in isnad.claims(answer)
        if unit.get("kind", "sentence") == "sentence"
        and len(tokenize(unit["text"])) >= 3
        and not muhasaba.computable(unit["text"])
    ]


def contexts_of(question: str, answer: str, claims: list[str]) -> list[str]:
    """Each claim's context as ``ahl_dhikr.consult`` gives it: what it speaks of
    when it does not name it, from the question and every sentence before it."""
    said = [
        unit["text"]
        for unit in isnad.claims(answer)
        if unit.get("kind", "sentence") == "sentence" and unit.get("text")
    ]
    found: dict[str, str] = {}
    for sentence, words in zip(said, ahl_dhikr.contexts(question, said), strict=True):
        found.setdefault(sentence, words)
    return [found.get(claim, "") for claim in claims]


def windows(pool: list[Passage]) -> list[Passage]:
    """Every two consecutive sentences of the same article, as one premise."""
    found = []
    for first, second in zip(pool, pool[1:], strict=False):
        if first.url == second.url:
            found.append(
                Passage(f"{first.text} {second.text}", first.title, first.url, first.source)
            )
    return found


async def judge_single(claims: list[str], pool: list[Passage]) -> list[Finding]:
    """``ahl_dhikr.judge`` as it was before the joint premise: every premise is
    one source sentence."""
    if not pool:
        return [Finding(claim, "unknown") for claim in claims]
    pairs: list[tuple[str, str]] = []
    owners: list[tuple[int, Passage]] = []
    texts = [passage.text for passage in pool]
    for index, claim in enumerate(claims):
        scores = bm25_scores(claim, texts)
        ranked = sorted(range(len(pool)), key=lambda i: -scores[i])
        related = [i for i in ranked if scores[i] > 0 and about(claim, texts[i])]
        for position in related[:CANDIDATES]:
            pairs.append((pool[position].text, claim))
            owners.append((index, pool[position]))
    readings = await nli(pairs) or []
    best: dict[int, tuple[float, str, Passage]] = {}
    for (index, passage), reading in zip(owners, readings, strict=True):
        decisive = max(reading["entailment"], reading["contradiction"])
        if index not in best or decisive > best[index][0]:
            best[index] = (decisive, max(reading, key=reading.__getitem__), passage)
    disputed = [index for index, (_, label, _) in best.items() if label == "contradiction"]
    reverse = await nli([(claims[index], best[index][2].text) for index in disputed]) or []
    for index, reading in zip(disputed, reverse, strict=False):
        if max(reading, key=reading.__getitem__) != "contradiction":
            best[index] = (best[index][0], "neutral", best[index][2])
    findings = []
    for index, claim in enumerate(claims):
        if index not in best or best[index][1] == "neutral":
            findings.append(Finding(claim, "unknown"))
            continue
        probability, label, passage = best[index]
        verdict = "supported" if label == "entailment" else "contradicted"
        findings.append(Finding(claim, verdict, probability, passage))
    return findings


def articles(path: Path, titles: set[str]) -> dict[str, str]:
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["title", "text"])
    found = {}
    for title, text in zip(
        table.column("title").to_pylist(), table.column("text").to_pylist(), strict=True
    ):
        if title in titles:
            found[title] = text
    return found


def keeps(question: str, findings: list[Finding]) -> bool:
    """Whether Talaqqi would keep the answer (``talaqqi.keep``'s rule)."""
    supported = [f for f in findings if f.verdict == "supported" and f.passage is not None]
    if not supported or any(f.verdict == "contradicted" for f in findings):
        return False
    return talaqqi.about(question, talaqqi.lesson(findings))


def share(hits: int, total: int) -> str:
    low, high = wilson_bounds(hits, total)
    return f"{hits}/{total} = {hits / max(1, total):.3f} [{low:.3f}, {high:.3f}]"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", type=Path, required=True)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--wiki", type=Path)
    sources.add_argument("--pools", type=Path)
    parser.add_argument("--nli", help="repo@revision:weights:vocabulary")
    parser.add_argument("--arms", default="single,joint,window,joint+window")
    parser.add_argument(
        "--information",
        choices=("lughah", "gharib"),
        default=ahl_dhikr.WORDS,
        help="the word information about() weighs by (ahl_dhikr.WORDS)",
    )
    parser.add_argument("--out", type=Path)
    options = parser.parse_args()
    ahl_dhikr.WORDS = options.information
    if options.nli:
        named, weights, vocabulary = options.nli.split(":")
        ahl_dhikr.REPO, ahl_dhikr.REVISION = named.split("@")
        ahl_dhikr.WEIGHTS, ahl_dhikr.VOCABULARY = weights, vocabulary

    items = json.loads(options.answers.read_text(encoding="utf-8"))
    texts: dict[str, str] = {}
    pools: dict[str, list] = {}
    if options.wiki:
        wanted = {title for item in items for title in item["articles"]}
        texts = articles(options.wiki, wanted)
        missing = sorted(wanted - set(texts))
        if missing:
            print("articles not in the dump:", ", ".join(missing))
    else:
        pools = json.loads(options.pools.read_text(encoding="utf-8"))

    if await nli([("The sky is blue.", "The sky is blue.")]) is None:
        raise SystemExit("The NLI model could not run; set MIZAN_DATA_DIR to where it is.")
    arms = [arm.strip() for arm in options.arms.split(",") if arm.strip()]
    verdicts: dict[str, list[list[Finding]]] = {arm: [] for arm in arms}
    for item in items:
        passages = (
            [
                Passage(
                    texts[title][:30000],
                    title,
                    "https://simple.wikipedia.org/wiki/" + title.replace(" ", "_"),
                    "wikipedia",
                )
                for title in item["articles"]
                if title in texts
            ]
            if options.wiki
            else ahl_dhikr.web_from({"results": pools.get(item["question"], [])})
        )
        claims = claims_of(item["answer"])
        context = contexts_of(item["question"], item["answer"], claims)
        single = sentences(passages)
        for arm in arms:
            pool = single + windows(single) if "window" in arm else single
            if "joint" in arm:
                verdicts[arm].append(await ahl_dhikr.judge(claims, pool, context))
            else:
                verdicts[arm].append(await judge_single(claims, pool))

    report: dict[str, dict] = {}
    print(f"\n{len(items)} questions")
    for arm in arms:
        found = [finding for findings in verdicts[arm] for finding in findings]
        supported = sum(1 for f in found if f.verdict == "supported")
        contradicted = sum(1 for f in found if f.verdict == "contradicted")
        kept = sum(
            1
            for item, findings in zip(items, verdicts[arm], strict=True)
            if keeps(item["question"], findings)
        )
        report[arm] = {
            "claims": len(found),
            "supported": supported,
            "contradicted": contradicted,
            "kept": kept,
        }
        print(
            f"{arm:>13}: supported {share(supported, len(found))}; "
            f"contradicted {share(contradicted, len(found))}; "
            f"Talaqqi keeps {share(kept, len(items))}"
        )

    changed: list[dict] = []
    if "single" in arms:
        for arm in arms:
            if arm == "single":
                continue
            for item, before, after in zip(items, verdicts["single"], verdicts[arm], strict=True):
                for old, new in zip(before, after, strict=True):
                    if old.verdict != new.verdict:
                        changed.append(
                            {
                                "arm": arm,
                                "question": item["question"],
                                "claim": new.claim,
                                "before": old.verdict,
                                "after": new.verdict,
                                "p": round(new.probability, 3),
                                "premise": new.passage.text if new.passage else "",
                            }
                        )
        print(f"\n{len(changed)} verdicts differ from single (audit each):")
        for row in changed:
            print(
                f"\n[{row['arm']}] {row['before']} -> {row['after']} (p {row['p']})\n"
                f"  claim:   {row['claim']}\n  premise: {row['premise'][:500]}"
            )
    if options.out:
        found = {
            arm: [
                {
                    "question": item["question"],
                    "findings": [
                        {**finding.to_dict(), "premise": finding.passage.text}
                        if finding.passage
                        else finding.to_dict()
                        for finding in findings
                    ],
                }
                for item, findings in zip(items, verdicts[arm], strict=True)
            ]
            for arm in arms
        }
        options.out.write_text(
            json.dumps(
                {"arms": report, "changed": changed, "findings": found},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    ahl_dhikr.logger.disabled = True
    asyncio.run(main())
