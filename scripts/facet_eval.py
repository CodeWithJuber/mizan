#!/usr/bin/env python3
"""Qasd's deen and ruling facets on everyday Hindi/Urdu requests (docs/fahm.md).

The facets read ordinary Hindi and Urdu requests (weather, alarms, music) as
about the deen: their Devanagari and Arabic-script seeds were mostly
religious, so the script itself became evidence. This adds everyday requests
people wrote (MASSIVE 1.1 train, CC BY 4.0) as ``no`` rows and measures, for
each facet and each count N per language:

- Ta'lim's check on the known seeds (leave-one-out, P(worse) < 0.95);
- false positives on everyday requests MASSIVE holds out (``dev`` to choose N,
  ``test`` reported once);
- recall on Qasd's own Quran and hadith request seeds (all about the deen;
  never facet seeds).

  python scripts/facet_eval.py --massive amazon-massive-dataset-1.1.tar.gz          # measure
  python scripts/facet_eval.py --massive ... --write 40     # write the deen rows
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

LOCALES = {"en-US": "en", "hi-IN": "hi", "ur-PK": "ur"}
# MASSIVE intents whose requests are about devices and daily errands (its
# intent names, read as data): calendars, news, questions and conversation are
# left out, since they may be about the deen.
EVERYDAY = (
    "alarm_",
    "audio_",
    "iot_",
    "music_",
    "play_",
    "takeaway_",
    "transport_",
    "weather_",
    "lists_",
    "email_",
    "cooking_",
    "datetime_",
)
# MASSIVE intents whose requests are everyday questions (facts, definitions,
# recipes, suggestions): the forms worship questions share ("… kya hai?")
QUESTIONS = ("qa_", "cooking_", "recommendation_")
COUNTS = (20, 40, 80)
FACETS = ("deen", "ruling")
# Qasd intents whose seeds are requests about the Quran or hadith
DEEN_INTENTS = (
    "quran",
    "quran_search",
    "quran_question",
    "quran_explain",
    "quran_count",
    "hadith",
    "hadith_explain",
)
# Qasd intents whose seeds are requests for MIZAN's own actions, never about
# the deen (conversation, memory and prayer times are left out: they may be)
ACTION_INTENTS = (
    "compute",
    "build_and_run",
    "build_project",
    "edit_project",
    "web_search",
    "web_read",
    "silsila",
    "silsila_follow",
    "run_code",
    "run_file",
    "run_follow",
    "project_task",
    "capabilities",
    "waqt",
    "watch",
    "hf_hub",
    "browse",
    "use_tool",
    "qiyas",
)
SALT = "facet-everyday-1"
SEEDS = ROOT / "backend" / "tadbir" / "data" / "qasd" / "facets.tsv"
WRITTEN = ROOT / "scripts" / "data" / "facet_deen_written.tsv"
HELD_OUT = ROOT / "scripts" / "data" / "facet_deen_heldout.tsv"


def _tsv(path: Path) -> list[list[str]]:
    return [
        line.split("\t")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def written() -> list[tuple[str, str]]:
    """(script, text) of the worship and belief questions written for the facet."""
    return [(script, text) for script, text in _tsv(WRITTEN)]


def held_out() -> list[tuple[str, str, str]]:
    """(label, script, text) of the held-out questions, never seeds."""
    return [(label, script, text) for label, script, text in _tsv(HELD_OUT)]


def _order(key: str) -> str:
    return hashlib.sha256(f"{SALT}:{key}".encode()).hexdigest()


def everyday(
    path: Path, kinds: tuple[str, ...] = EVERYDAY
) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """partition -> language -> [(id, text)] of everyday requests, SHA-256 ordered."""
    found: dict[str, dict[str, list[tuple[str, str]]]] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            locale = Path(member.name).stem
            if not member.isfile() or locale not in LOCALES or not member.name.endswith(".jsonl"):
                continue
            handle = archive.extractfile(member)
            assert handle is not None
            for row in io.TextIOWrapper(handle, encoding="utf-8"):
                item = json.loads(row)
                if not str(item["intent"]).startswith(kinds):
                    continue
                part = found.setdefault(str(item["partition"]), {})
                key = f"{locale}:{item['id']}"
                text = " ".join(str(item["utt"]).split())
                part.setdefault(LOCALES[locale], []).append((key, text))
    for part in found.values():
        for language in part:
            part[language].sort(key=lambda row: _order(row[0]))
    return found


def action_requests() -> list[tuple[str, str]]:
    """(script, text) of Qasd's seeds for MIZAN's own actions, in every script
    the seeds are written in (Roman Hindi/Urdu among them, which MASSIVE lacks)."""
    from tadbir import qasd

    rows = []
    for label, text in qasd._rows("intents.tsv"):
        if label in ACTION_INTENTS:
            text = text.removeprefix("[project] ")
            rows.append((_script(text), text))
    return rows


def deen_requests() -> list[tuple[str, str]]:
    """(script, text) of Qasd's Quran and hadith request seeds."""
    from tadbir import qasd

    rows = []
    for label, text in qasd._rows("intents.tsv"):
        if label in DEEN_INTENTS and not text.startswith("[project]"):
            rows.append((_script(text), text))
    return rows


def _script(text: str) -> str:
    import unicodedata

    for char in text:
        name = unicodedata.name(char, "")
        if "DEVANAGARI" in name:
            return "deva"
        if "ARABIC" in name:
            return "arab"
    return "latin"


def added(rows: dict[str, list[tuple[str, str]]], count: int) -> list[tuple[str, str]]:
    return [(text, "no") for language in LOCALES.values() for _key, text in rows[language][:count]]


def halves(positives: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Qasd's Quran and hadith request seeds split in two by SHA-256: one half
    becomes deen ``yes`` rows, the other is held out to read recall on."""
    taught, held = [], []
    for script, text in positives:
        (taught if int(_order(f"half:{text}")[:8], 16) % 2 == 0 else held).append((script, text))
    return taught, held


def rate(model, texts: list[str]) -> float:
    found = [model.posterior(text) for text in texts]
    return round(sum(p.get("yes", 0.0) > p.get("no", 0.0) for p in found) / max(1, len(found)), 4)


def measure(massive: Path) -> dict:
    from core.tamyiz import Tamyiz
    from tadbir import qasd, talim

    parts = everyday(massive)
    train, dev, test = parts["train"], parts["dev"], parts["test"]
    asked = everyday(massive, QUESTIONS)
    taught, held = halves(deen_requests())
    actions_taught, actions_held = halves(action_requests())
    report: dict = {
        "deen_taught": len(taught),
        "deen_held": len(held),
        "actions_taught": len(actions_taught),
        "actions_held": len(actions_held),
    }
    plans = {
        "deen": [
            (0, False, False, False),
            *((count, True, True, False) for count in COUNTS),
            *((count, True, True, True) for count in COUNTS),
            *((-count, True, True, True) for count in COUNTS),
        ],
        "ruling": [
            (0, False, False, False),
            *((count, False, False, False) for count in (5, 10, *COUNTS)),
        ],
    }
    for facet, grid in plans.items():
        seeds = qasd.facet_examples(facet)
        rows: dict = {}
        for count, with_positives, with_actions, with_written in grid:
            # a negative count: as many everyday commands and as many everyday questions
            extra = added(train, abs(count))
            if count < 0:
                extra += added(asked["train"], -count)
            if with_positives:
                extra += [(text, "yes") for _script, text in taught]
            if with_actions:
                extra += [(text, "no") for _script, text in actions_taught]
            if with_written:
                extra += [(text, "yes") for _script, text in written()]
            model = Tamyiz(qasd._features).fit([*seeds, *extra])
            entry: dict = {
                "false_positive_dev": {
                    language: rate(model, [t for _k, t in dev[language][:300]])
                    for language in LOCALES.values()
                },
                "false_positive_test": {
                    language: rate(model, [t for _k, t in test[language][:300]])
                    for language in LOCALES.values()
                },
            }
            if facet == "deen":
                entry["recall_held_out"] = {
                    script: rate(model, [t for s, t in held if s == script])
                    for script in ("latin", "deva", "arab")
                }
                entry["false_positive_questions_test"] = {
                    language: rate(model, [t for _k, t in asked["test"][language][:300]])
                    for language in LOCALES.values()
                }
                entry["false_positive_actions_held_out"] = {
                    script: rate(model, [t for s, t in actions_held if s == script])
                    for script in ("latin", "deva", "arab")
                }
                questions = held_out()
                for label, name in (
                    ("yes", "recall_worship_held_out"),
                    ("no", "false_positive_questions_held_out"),
                ):
                    entry[name] = {
                        script: rate(
                            model, [t for lab, s, t in questions if lab == label and s == script]
                        )
                        for script in ("latin", "deva", "arab")
                    }
            if extra:
                verdict = talim.judge(f"qasd.{facet}", extra)
                entry["talim"] = {
                    key: verdict[key]
                    for key in ("before", "after", "p_worse", "kept", "changed_classes")
                }
            key = (
                f"{count}{'+yes' if with_positives else ''}{'+actions' if with_actions else ''}"
                f"{'+written' if with_written else ''}"
            )
            rows[key] = entry
            print(facet, key, json.dumps(entry), flush=True)
        report[facet] = rows
    return report


def write(massive: Path, count: int) -> int:
    """Append to the deen facet ``count`` everyday requests per language as
    ``no`` rows and the taught half of Qasd's Quran and hadith request seeds
    as ``yes`` rows (the owner's choice of 31 Oct 2026: deen recall first)."""
    parts = everyday(massive)
    taught, _held = halves(deen_requests())
    lines = [
        "# deen: Qasd's own Quran and hadith requests (half of them, by SHA-256; the other half is",
        "# held out to read recall) are about the deen; half of Qasd's requests for MIZAN's own actions",
        "# and everyday requests people wrote in English, Hindi and Urdu (MASSIVE 1.1 train, CC BY 4.0)",
        "# are not: the script is no evidence; questions about worship and belief written for the",
        "# facet (scripts/data/facet_deen_written.tsv, by a language model, at the owner's request) are",
        "# (scripts/facet_eval.py --write 40).",
    ]
    actions, _held = halves(action_requests())
    lines += [f"deen\tyes\t{text}" for _script, text in taught]
    lines += [f"deen\tno\t{text}" for _script, text in actions]
    lines += [f"deen\tyes\t{text}" for _script, text in written()]
    lines += [f"deen\tno\t{text}" for text, _label in added(parts["train"], count)]
    with SEEDS.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return len(lines) - 7


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--massive", type=Path, required=True)
    parser.add_argument("--write", type=int, default=0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.write:
        print(f"{write(args.massive, args.write)} rows written to {SEEDS}")
        return
    report = measure(args.massive)
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
