#!/usr/bin/env python3
"""Tadrib phase 2: can MIZAN's own student learn a Lisan task from its teacher?
(docs/tadrib.md, "Phase 2"). The first task is ``plan_steps``: mapping a
message to MIZAN's actions.

  --lessons WORK      ask the teacher (Lisan.plan_steps, as MIZAN asks it) for
                      MASSIVE 1.1 utterances (en, hi, ur), keep what MIZAN's
                      checks pass -> WORK/lessons.jsonl (spending capped)
  --again WORK        ask the teacher a second time for the first 200 lessons
                      -> WORK/again.jsonl (the teacher's agreement with itself)
  --run WORK          the prequential stream: the student answers each lesson
                      before it learns it -> WORK/run.json (+ rows)

The teacher is the model production uses (``--model``, an OpenRouter id whose
licence is checked by ``tadrib.licence``); OPENROUTER_API_KEY must be set.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SALT = "tadrib-lisan-1"
LOCALES = {"en-US": "en", "hi-IN": "hi", "ur-PK": "ur"}
PER_LANGUAGE = 1700
AGAIN = 200
CAP_USD = 3.0
CONCURRENCY = 8
ERASE_OVER = 300  # lessons the erasure check runs over


def _order(key: str, purpose: str = "order") -> str:
    return hashlib.sha256(f"{SALT}:{purpose}:{key}".encode()).hexdigest()


# ── the teacher ──────────────────────────────────────────────────────────


class _Agent:
    """What Lisan needs of an agent: a provider and a model, and somewhere
    to count calls and tokens."""

    def __init__(self, provider, model: str):
        self.ai_client = provider
        self.ai_model = model
        self.input_tokens = 0
        self.output_tokens = 0
        self.served_by: set[str] = set()

    def _record_llm_call(self, response, latency_ms: float) -> None:
        usage = getattr(response, "usage", None) or {}
        if not isinstance(usage, dict):  # an SDK object rather than MIZAN's normalised dict
            usage = {
                "input": getattr(usage, "input_tokens", 0),
                "output": getattr(usage, "output_tokens", 0),
            }
        self.input_tokens += int(usage.get("input", 0) or 0)
        self.output_tokens += int(usage.get("output", 0) or 0)
        served = getattr(response, "model", None)
        if served:
            self.served_by.add(str(served))

    def _add_execution_time(self, key: str, started: float) -> float:
        return 0.0


def price_of(model: str) -> tuple[float, float]:
    """USD per input and per output token, as OpenRouter lists the model now."""
    import urllib.request

    with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60) as reply:
        listed = json.load(reply)["data"]
    for item in listed:
        if item["id"] == model:
            pricing = item["pricing"]
            return float(pricing["prompt"]), float(pricing["completion"])
    raise SystemExit(f"{model}: not listed by OpenRouter")


def utterances(massive_path: Path) -> list[tuple[str, str, str]]:
    """(source, language, text) of MASSIVE's train utterances in en, hi, ur,
    the first ``PER_LANGUAGE`` of each in SHA-256 order that is not about the
    deen as MIZAN reads it (``student.about_the_deen``: such a message is never
    a lesson, so the teacher is not asked)."""
    from tadbir.ruh_reader import corpus as C
    from tadbir.tadrib import student

    by_language: dict[str, list[tuple[str, str, str]]] = {}
    for line in C.massive(massive_path):
        locale = line.source.split(":")[1]
        if line.kind != "train" or locale not in LOCALES:
            continue
        by_language.setdefault(LOCALES[locale], []).append(
            (line.source, LOCALES[locale], line.text)
        )
    rows = []
    for found in by_language.values():
        taken = []
        for row in sorted(found, key=lambda row: _order(row[0])):
            if len(taken) >= PER_LANGUAGE:
                break
            if not student.about_the_deen(row[2]):
                taken.append(row)
        rows += taken
    return sorted(rows, key=lambda row: _order(row[0], "stream"))


async def ask_teacher(lisan, text: str) -> tuple[str, list[dict]]:
    """The teacher's reply and steps for one message, as Tadbir asks it."""
    from tadbir import amanah

    steps = await lisan.plan_steps(amanah.clean_message(text), "")
    reply = lisan.exchange.get("plan_steps", {}).get("reply", "")
    return reply, steps


def collect(work: Path, massive_path: Path, model: str, limit: int = 0) -> dict:
    """Ask the teacher for every utterance; keep the steps MIZAN's checks pass."""
    from providers import create_provider
    from tadbir.lisan import Lisan
    from tadbir.tadrib import licence, student

    if not licence.allowed(model):
        raise SystemExit(f"{model}: no licence on record that allows training on its output")
    price = price_of(model)
    rows = utterances(massive_path)
    if limit:
        rows = rows[:limit]
    out = work / "lessons.jsonl"
    done = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            done[item["source"]] = item
    spent = sum(item.get("usd", 0.0) for item in done.values())
    provider = create_provider("openrouter", model)

    async def one(source: str, language: str, text: str, gate: asyncio.Semaphore) -> dict | None:
        nonlocal spent
        async with gate:
            if spent >= CAP_USD:
                return None
            agent = _Agent(provider, model)
            lisan = Lisan(agent)
            try:
                reply, steps = await ask_teacher(lisan, text)
            except Exception as exc:  # noqa: BLE001 - a failed call is recorded, not retried
                return {"source": source, "language": language, "text": text, "error": str(exc)}
            usd = agent.input_tokens * price[0] + agent.output_tokens * price[1]
            spent += usd
            target = student.target(steps, text, language)
            return {
                "source": source,
                "language": language,
                "text": text,
                "reply": reply,
                "steps": steps,
                "target": target,
                "served_by": sorted(agent.served_by),
                "usd": usd,
            }

    async def main() -> None:
        gate = asyncio.Semaphore(CONCURRENCY)
        pending = [row for row in rows if row[0] not in done]
        with out.open("a", encoding="utf-8") as handle:
            for begin in range(0, len(pending), 64):
                results = await asyncio.gather(
                    *(one(*row, gate) for row in pending[begin : begin + 64])
                )
                for item in results:
                    if item is not None:
                        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                        done[item["source"]] = item
                handle.flush()
                print(f"{len(done)} asked, ${spent:.3f}", flush=True)
                if spent >= CAP_USD:
                    print("spending cap reached", flush=True)
                    return

    asyncio.run(main())
    kept = [item for item in done.values() if item.get("target")]
    return {
        "asked": len(done),
        "errors": sum("error" in item for item in done.values()),
        "lessons": len(kept),
        "by_language": {
            language: sum(item["language"] == language for item in kept)
            for language in LOCALES.values()
        },
        "usd": round(spent, 4),
    }


def again(work: Path, model: str) -> dict:
    """The teacher asked a second time for the first ``AGAIN`` lessons: how often
    it agrees with itself (``student.agree``), the bar a student must reach."""
    from providers import create_provider
    from tadbir.lisan import Lisan
    from tadbir.tadrib import student

    price = price_of(model)
    provider = create_provider("openrouter", model)
    lessons = [
        json.loads(line)
        for line in (work / "lessons.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    lessons = [item for item in lessons if item.get("target")][:AGAIN]

    async def one(item: dict, gate: asyncio.Semaphore) -> dict:
        async with gate:
            agent = _Agent(provider, model)
            try:
                reply, steps = await ask_teacher(Lisan(agent), item["text"])
            except Exception as exc:  # noqa: BLE001
                return {"source": item["source"], "error": str(exc)}
            second = student.target(steps, item["text"], item["language"])
            return {
                "source": item["source"],
                "language": item["language"],
                "target": second,
                "agree": student.agree(second, item["target"], item["text"], item["language"]),
                "usd": agent.input_tokens * price[0] + agent.output_tokens * price[1],
            }

    async def main() -> list[dict]:
        gate = asyncio.Semaphore(CONCURRENCY)
        return await asyncio.gather(*(one(item, gate) for item in lessons))

    found = asyncio.run(main())
    (work / "again.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in found), encoding="utf-8"
    )
    answered = [item for item in found if "agree" in item]
    by_language = {}
    for language in LOCALES.values():
        part = [item["agree"] for item in answered if item["language"] == language]
        by_language[language] = {"n": len(part), "agree": sum(part) / max(1, len(part))}
    report = {
        "n": len(answered),
        "agree": sum(item["agree"] for item in answered) / max(1, len(answered)),
        "by_language": by_language,
        "usd": round(sum(item.get("usd", 0.0) for item in found), 4),
    }
    (work / "again.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


# ── the student ──────────────────────────────────────────────────────────


def run(work: Path, weights: Path, setting: dict, erase: bool = False, limit: int = 0) -> dict:
    """The prequential stream: for each lesson in order the student answers
    first (scored against the teacher, ``student.agree``), then learns it."""
    import torch

    from core.adaptive import BettingEProcess
    from tadbir.ruh_reader import net
    from tadbir.tadrib import student

    torch.set_num_threads(int(os.getenv("OMP_NUM_THREADS", "2")))
    lessons = [
        json.loads(line)
        for line in (work / "lessons.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    lessons = [item for item in lessons if item.get("target")]
    if limit:
        lessons = lessons[:limit]
    bar = json.loads((work / "again.json").read_text(encoding="utf-8"))
    p0 = {language: part["agree"] for language, part in bar["by_language"].items()}
    learner = student.Student(net.load(weights), student.Setting(**setting))
    tests = {language: BettingEProcess(p0[language]) for language in p0}
    promoted: dict[str, int | None] = {language: None for language in p0}
    rows = []
    answer_seconds, learn_seconds = [], []
    for index, item in enumerate(lessons):
        began = time.perf_counter()
        said, mean_logp = learner.answer(item["text"])
        answer_seconds.append(time.perf_counter() - began)
        agreed = student.agree(said, item["target"], item["text"], item["language"])
        test = tests[item["language"]]
        test.update(1.0 if agreed else 0.0)
        if promoted[item["language"]] is None and test.value >= 20:
            promoted[item["language"]] = index
        began = time.perf_counter()
        learner.learn(item["text"], item["target"], student.digest_of(item["source"]))
        learn_seconds.append(time.perf_counter() - began)
        rows.append(
            {
                "index": index,
                "language": item["language"],
                "agree": agreed,
                "valid": said is not None and student.valid(said, item["text"], item["language"]),
                "mean_logp": mean_logp,
                "e": test.value,
            }
        )
        if index % 200 == 0:
            print(index, {k: round(t.value, 2) for k, t in tests.items()}, flush=True)
    (work / "run.rows.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    def share(part: list[dict]) -> float:
        return round(sum(row["agree"] for row in part) / max(1, len(part)), 4)

    third = max(1, len(rows) // 3)
    ordered_a = sorted(answer_seconds)
    ordered_l = sorted(learn_seconds)
    report = {
        "n": len(rows),
        "p0": p0,
        "agree": {"first third": share(rows[:third]), "last third": share(rows[-third:])},
        "by_language": {
            language: {
                "n": sum(row["language"] == language for row in rows),
                "last third": share([row for row in rows[-third:] if row["language"] == language]),
                "e": round(tests[language].value, 3),
                "promoted_at": promoted[language],
            }
            for language in p0
        },
        "seconds": {
            "answer_p95": round(ordered_a[int(len(ordered_a) * 0.95)], 3),
            "learn_p95": round(ordered_l[int(len(ordered_l) * 0.95)], 3),
        },
    }
    if erase:
        report["erasure"] = erasure(weights, setting, lessons[:ERASE_OVER])
    (work / "run.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def erasure(weights: Path, setting: dict, lessons: list[dict]) -> dict:
    """A student that learned these lessons, then forgot one in ten (rebuilt
    without them), equals, bit for bit, one that never learned them."""
    from tadbir.ruh_reader import net
    from tadbir.tadrib import student

    items = [(item["text"], item["target"], student.digest_of(item["source"])) for item in lessons]
    erased = [item for item in items if int(_order(item[2], "erase")[:16], 16) % 10 == 0]
    kept = [item for item in items if item not in erased]
    learned = student.Student(net.load(weights), student.Setting(**setting))
    learned.rebuild(items)
    learned.rebuild(kept)
    never = student.Student(net.load(weights), student.Setting(**setting))
    for message, answer, digest in kept:
        never.learn(message, answer, digest)
    return {
        "lessons": len(items),
        "erased": len(erased),
        "bit_for_bit": student.same_weights(learned.model, never.model),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--lessons", type=Path)
    parser.add_argument("--again", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--massive", type=Path)
    parser.add_argument("--model", default="deepseek/deepseek-chat-v3-0324")
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--setting", default="{}")
    parser.add_argument("--erase", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.lessons:
        print(json.dumps(collect(args.lessons, args.massive, args.model, args.limit), indent=1))
    elif args.again:
        print(json.dumps(again(args.again, args.model), indent=1))
    elif args.run:
        found = run(args.run, args.weights, json.loads(args.setting), args.erase, args.limit)
        print(json.dumps(found, indent=1))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
