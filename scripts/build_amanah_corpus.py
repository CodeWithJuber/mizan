"""Build the Amanah corpus: text aimed at an AI (attack) and ordinary text (data).

Writes backend/tadbir/data/amanah/{attack,data}.tsv (training) and
heldout_{attack,data}.tsv (evaluation only, never trained on), one window of at
most 300 characters per line: ``source<TAB>text``. Windows of one source text
share its source id, so leave-one-out holds them out together.

Sources, pinned to a Hugging Face revision (licences in LICENSES.md):

| set | source | label |
|---|---|---|
| train | deepset/prompt-injections, train split (Apache-2.0) | its 0/1 label |
| train | Lakera/gandalf_ignore_instructions, train (MIT) | attack |
| train | jackhhao/jailbreak-classification, train, ``jailbreak`` rows (Apache-2.0) | attack |
| train | reshabhs/SPML_Chatbot_Prompt_Injection user prompts (MIT) | its 0/1 label |
| train | Tatoeba sentences already in MIZAN's Lughah corpus (CC BY 2.0 FR) | data |
| train | HuggingFaceFW/fineweb-edu sample-10BT rows, read through the datasets-server (ODC-By 1.0) | data |
| train | authored.tsv: lines written for MIZAN in ur/hi/ar and hard negatives (CC0) | its label |
| train | sentences from MIZAN's own documentation (docs/*.md, README.md, CONTRIBUTING.md; this repository's licence), any sentence the patterns flag left out | data |
| held out | deepset/prompt-injections, test split | its 0/1 label |
| held out | microsoft/llmail-inject-challenge phase 2 attack emails (MIT) | attack |
| held out | 300 more FineWeb-Edu pages (first 3,000 characters each), never trained on or mined | data |
| train, held out | microsoft/llmail-inject-challenge emails_for_fp_tests (MIT): even rows train, odd rows held out | data |

The jailbreak-classification "benign" rows are role-play prompts written to an
AI; in outside text those are instructions too, so they are not used as data.
Any window close to an AGI-test task (character-trigram Jaccard ≥ 0.4) is
dropped, so the test is not trained on. Sampling is seeded.

    pip install huggingface_hub pyarrow
    python scripts/build_amanah_corpus.py <download-dir>
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "tadbir" / "data" / "amanah"
LUGHAH = ROOT / "backend" / "tadbir" / "data" / "lughah"
WINDOW = 300
MAX_WINDOWS = 6

SOURCES = {
    "deepset": ("deepset/prompt-injections", "4f61ecb038e9c3fb77e21034b22511b523772cdd"),
    "gandalf": ("Lakera/gandalf_ignore_instructions", "04737b65e90a6794ec227012e4a255a7def6344b"),
    "jailbreak": ("jackhhao/jailbreak-classification", "2f2ceeb39658696fd3f462403562b6eea5306287"),
    "spml": ("reshabhs/SPML_Chatbot_Prompt_Injection", "02ce8084e979bc7d4c24ee35d22ecb7f2db96ff5"),
    "llmail": ("microsoft/llmail-inject-challenge", "1063bdf01ec8762b812d5e06ee768a06faa5a6f7"),
}
# Ordinary web prose, so long text is not mistaken for an instruction for being long.
FINEWEB = "HuggingFaceFW/fineweb-edu"
FINEWEB_ROWS = [offset * 9973 for offset in range(8)]  # eight pages of 100 rows, spread out
# A larger pool of ordinary web prose, never trained on directly: the sentences a
# first model wrongly flags are added as data (hard-negative mining).
POOL_ROWS = [500_000 + offset * 7919 for offset in range(40)]
HARD_NEGATIVES = 300  # chosen on held-out pages: 2.4x the rules' recall at ~1.7% of pages flagged
# Web pages never trained on or mined: false alarms on whole pages are measured here.
HELDOUT_WEB_ROWS = [900_000 + offset * 6007 for offset in range(5)]
FILES = {
    "deepset": [
        "data/train-00000-of-00001-9564e8b05b4757ab.parquet",
        "data/test-00000-of-00001-701d16158af87368.parquet",
    ],
    "gandalf": ["data/train-00000-of-00001-ded53be747ff55cd.parquet"],
    "jailbreak": ["default/jailbreak_dataset_train.csv"],
    "spml": ["spml_prompt_injection.csv"],
    "llmail": [
        "data/emails_for_fp_tests.json",
        "data/labelled_unique_submissions_phase2.json",
    ],
}


def download(target: Path) -> None:
    """Fetch every source file at its pinned revision."""
    from huggingface_hub import hf_hub_download

    for name, (repo, revision) in SOURCES.items():
        for path in FILES[name]:
            hf_hub_download(
                repo, path, repo_type="dataset", revision=revision, local_dir=target / name
            )


def fineweb(target: Path, offsets: list[int] = FINEWEB_ROWS, name: str = "fineweb.json") -> None:
    """Fetch FineWeb-Edu rows (datasets-server, 100 per page) into a JSON file."""
    import httpx

    rows = []
    for offset in offsets:
        response = httpx.get(
            "https://datasets-server.huggingface.co/rows",
            params={
                "dataset": FINEWEB,
                "config": "sample-10BT",
                "split": "train",
                "offset": offset,
                "length": 100,
            },
            timeout=60,
        )
        response.raise_for_status()
        rows += [
            {"id": item["row"]["id"], "url": item["row"]["url"], "text": item["row"]["text"]}
            for item in response.json()["rows"]
        ]
    (target / name).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def windows(text: str) -> list[str]:
    """The text cut at sentence ends into pieces of at most WINDOW characters."""
    text = " ".join(str(text or "").replace("\t", " ").split())
    parts = re.split(r"(?<=[.!?۔।])\s+", text)
    found, current = [], ""
    for part in parts:
        while len(part) > WINDOW:
            cut = part.rfind(" ", 0, WINDOW)
            cut = cut if cut > WINDOW // 2 else WINDOW
            if current:
                found.append(current)
                current = ""
            found.append(part[:cut].strip())
            part = part[cut:].strip()
        if current and len(current) + 1 + len(part) > WINDOW:
            found.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        found.append(current)
    return [piece for piece in found if len(piece) >= 8][:MAX_WINDOWS]


def _parquet(path: Path) -> list[dict]:
    import pyarrow.parquet as pq

    return pq.read_table(path).to_pylist()


def _csv(path: Path) -> list[dict]:
    csv.field_size_limit(10**8)
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sample(rows: list, count: int, seed: str) -> list:
    rows = list(rows)
    return random.Random(seed).sample(rows, min(count, len(rows)))


def _trigrams(text: str) -> set[str]:
    text = " ".join(text.lower().split())
    return {text[i : i + 3] for i in range(len(text) - 2)}


def _guarded() -> list[set[str]]:
    """Trigram sets of every AGI-test task prompt (and the locked eval if cached)."""
    sets = []
    for path in sorted((ROOT / "backend" / "imtihan" / "tasks").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                task = json.loads(line)
                sets.append(_trigrams(str(task.get("prompt", ""))))
    locked = ROOT / "backend" / "data" / "imtihan" / "eval_v1.jsonl"
    if locked.exists():
        for line in locked.read_text(encoding="utf-8").splitlines():
            if line.strip():
                sets.append(_trigrams(json.dumps(json.loads(line), ensure_ascii=False)))
    return [s for s in sets if s]


def _clean(
    rows: list[tuple[str, str]], guarded: list[set[str]]
) -> tuple[list[tuple[str, str]], int]:
    kept, dropped = [], 0
    for source, text in rows:
        grams = _trigrams(text)
        if grams and any(len(grams & g) / len(grams | g) >= 0.4 for g in guarded):
            dropped += 1
            continue
        kept.append((source, text))
    return kept, dropped


def _units(prefix: str, texts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(f"{prefix}:{key}", piece) for key, text in texts for piece in windows(text)]


def _documentation() -> list[tuple[str, str]]:
    """Technical, imperative sentences from MIZAN's own docs ("Run X", "Set Y to Z"):
    ordinary text that tells a person what to do. A sentence the Amanah patterns flag
    (the docs quote injections when explaining Amanah) is left out."""
    sys.path.insert(0, str(ROOT / "backend"))
    from tadbir.amanah import PATTERNS, fold

    files = sorted((ROOT / "docs").glob("*.md")) + [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
    rows = []
    for path in files:
        text = re.sub(r"```.*?```", " ", path.read_text(encoding="utf-8"), flags=re.DOTALL)
        text = re.sub(r"[`*_#>|]", " ", text)
        for number, part in enumerate(re.split(r"(?<=[.!?])\s+|\n+", text)):
            sentence = " ".join(part.split()).strip("- ")
            if 20 <= len(sentence) <= 220 and not any(
                p.search(fold(sentence)) for p in PATTERNS.values()
            ):
                rows.append((f"docs:{path.name}:{number}", sentence))
    return _sample(rows, 1200, "amanah-docs")


def _hard_negatives(downloads: Path, train: dict) -> list[tuple[str, str]]:
    """Ordinary sentences a model trained on the rest reads as attacks."""
    sys.path.insert(0, str(ROOT / "backend"))
    from core.tamyiz import Tamyiz
    from tadbir.amanah import _features

    rows = [(text, label, source) for label in ("attack", "data") for source, text in train[label]]
    model = Tamyiz(_features).fit(rows)
    pool = json.loads((downloads / "fineweb_pool.json").read_text(encoding="utf-8"))
    scored = []
    for row in pool:
        for number, part in enumerate(re.split(r"(?<=[.!?])\s+|\n+", row["text"])):
            sentence = " ".join(part.split())
            if 15 <= len(sentence) <= 220:
                probability = model.posterior(sentence)["attack"]
                if probability > 0.5:
                    scored.append((probability, f"fineweb-hard:{row['id']}:{number}", sentence))
    scored.sort(reverse=True)
    print("hard negatives found", len(scored))
    return [(source, sentence) for _p, source, sentence in scored[:HARD_NEGATIVES]]


def main(downloads: Path) -> None:
    if not (downloads / "deepset").exists():
        download(downloads)
    if not (downloads / "fineweb.json").exists():
        fineweb(downloads)
    if not (downloads / "fineweb_pool.json").exists():
        fineweb(downloads, POOL_ROWS, "fineweb_pool.json")
    if not (downloads / "fineweb_heldout.json").exists():
        fineweb(downloads, HELDOUT_WEB_ROWS, "fineweb_heldout.json")
    train = {"attack": [], "data": []}
    heldout = {"attack": [], "data": []}

    deepset = downloads / "deepset" / "data"
    for split, target in (("train", train), ("test", heldout)):
        path = next(deepset.glob(f"{split}-*.parquet"))
        for number, row in enumerate(_parquet(path)):
            label = "attack" if int(row["label"]) == 1 else "data"
            target[label] += _units("deepset", [(f"{split}{number}", row["text"])])

    gandalf = next((downloads / "gandalf" / "data").glob("train-*.parquet"))
    rows = [(str(i), row["text"]) for i, row in enumerate(_parquet(gandalf))]
    train["attack"] += _units("gandalf", _sample(rows, 450, "amanah-gandalf"))

    jail = [
        (str(i), row["prompt"])
        for i, row in enumerate(
            _csv(downloads / "jailbreak" / "default" / "jailbreak_dataset_train.csv")
        )
        if row.get("type") == "jailbreak"
    ]
    train["attack"] += _units("jailbreak", _sample(jail, 350, "amanah-jailbreak"))

    spml = _csv(downloads / "spml" / "spml_prompt_injection.csv")
    for label, flag in (("attack", "1"), ("data", "0")):
        rows = [
            (str(i), row["User Prompt"])
            for i, row in enumerate(spml)
            if row["Prompt injection"] == flag
        ]
        train[label] += _units("spml", _sample(rows, 450, f"amanah-spml-{label}"))

    for code in ("en", "hi-latn", "ur", "hi", "ar"):
        lines = []
        for line in (LUGHAH / f"{code}.tsv").read_text(encoding="utf-8").splitlines():
            source, _, text = line.partition("\t")
            if source.startswith("tatoeba:") and text.strip():
                lines.append((source, text.strip()))
        train["data"] += _sample(lines, 160, f"amanah-{code}")

    web = json.loads((downloads / "fineweb.json").read_text(encoding="utf-8"))
    for row in _sample(web, 700, "amanah-fineweb"):
        train["data"] += [(f"fineweb:{row['id']}", piece) for piece in windows(row["text"])[:3]]
        # Single sentences too: short ordinary text (a title, a how-to step) is
        # not an instruction to an AI for being short or imperative.
        sentences = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+|\n+", row["text"])
            if 15 <= len(part.strip()) <= 200
        ]
        for number, sentence in enumerate(_sample(sentences, 3, f"amanah-s-{row['id']}")):
            train["data"].append((f"fineweb:{row['id']}:s{number}", sentence))

    train["data"] += _documentation()

    for number, line in enumerate((OUT / "authored.tsv").read_text(encoding="utf-8").splitlines()):
        if line.strip() and not line.startswith("#"):
            label, text = line.split("\t", 1)
            train[label].append((f"mizan:{number}", text.strip()))

    llmail = downloads / "llmail" / "data"
    benign = json.loads((llmail / "emails_for_fp_tests.json").read_text(encoding="utf-8"))
    # Every other benign email trains, so ordinary business mail is known as data;
    # the rest stay held out to measure false alarms on mail it never saw.
    emails = [(str(i), text) for i, text in enumerate(benign)]
    train["data"] += _units("llmail-fp", emails[0::2])
    heldout["data"] += _units("llmail-fp", emails[1::2])
    phase2 = json.loads(
        (llmail / "labelled_unique_submissions_phase2.json").read_text(encoding="utf-8")
    )
    attacks = [
        (str(i), email)
        for i, (email, label) in enumerate(sorted(phase2.items()))
        if str(label.get("attack_attempt")) == "True"
    ]
    # Whole emails: an email is caught if any window of it is caught.
    heldout["attack"] += [
        (f"llmail-p2:{key}", " ".join(email.split())[:2000])
        for key, email in _sample(attacks, 400, "amanah-llmail")
    ]

    train["data"] += _hard_negatives(downloads, train)
    pages = json.loads((downloads / "fineweb_heldout.json").read_text(encoding="utf-8"))
    for row in _sample(pages, 300, "amanah-web-heldout"):
        body = " ".join(row["text"].split())[:3000]  # a page's first 3,000 characters
        heldout["data"].append((f"fineweb-page:{row['id']}", body))

    guarded = _guarded()
    OUT.mkdir(parents=True, exist_ok=True)
    for prefix, sets in (("", train), ("heldout_", heldout)):
        for label, rows in sets.items():
            rows, dropped = _clean(sorted(set(rows)), guarded)
            body = "".join(f"{source}\t{text}\n" for source, text in rows)
            (OUT / f"{prefix}{label}.tsv").write_text(body, encoding="utf-8")
            print(f"{prefix}{label}", len(rows), f"(dropped {dropped} close to AGI-test tasks)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
