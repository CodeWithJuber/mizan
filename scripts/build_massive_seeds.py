"""Build Ta'lim batches from MASSIVE so MIZAN reads new languages (Tamil, …).

MASSIVE (Amazon, CC BY 4.0) has the same 16,521 utterances written in 51
languages, each with one of 60 intents. Read here through its Hugging Face
parquet mirror ``mteb/amazon_massive_intent`` (pinned by commit).

1. Lughah: each language's utterances (an even sample over intents) teach
   Lughah that language, under its ISO code and name.
2. Qasd: MASSIVE's intents are not MIZAN's, and no hand-written table maps
   them. MIZAN's own Qasd model reads every English utterance; a MASSIVE
   intent is aligned to the MIZAN intent most of its utterances get, and only
   when that share's 95% Wilson lower bound is above ½. Other intents are
   left out. The aligned label then carries over to the same utterance id in
   every language, so Qasd learns Tamil wording for what it already does.

Each batch is written as JSON for ``POST /api/tadbir/talim``; with ``--post``
it is sent there (an administrator's token in a file), where the acceptance
gate keeps it only if it does not make MIZAN worse.

    python scripts/build_massive_seeds.py --locales ta,bn,ms --out /tmp/massive
    python scripts/build_massive_seeds.py --locales ta --post https://your-mizan --token-file .token
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

DATASET = "mteb/amazon_massive_intent"
VIEWER = "https://datasets-server.huggingface.co/rows"
LICENCE = "CC BY 4.0 (MASSIVE, Amazon); mirror Apache-2.0 (mteb)"
# The names of MASSIVE's languages, as its README lists them (data, not rules).
NAMES = {
    "ta": "Tamil", "bn": "Bengali", "ms": "Malay", "id": "Indonesian", "tr": "Turkish",
    "fa": "Persian", "sw": "Swahili", "te": "Telugu", "ml": "Malayalam", "kn": "Kannada",
    "az": "Azerbaijani", "sq": "Albanian", "fr": "French", "de": "German", "es": "Spanish",
    "ru": "Russian", "zh-CN": "Chinese (Simplified)", "ja": "Japanese", "ko": "Korean",
    "th": "Thai", "vi": "Vietnamese", "tl": "Tagalog", "am": "Amharic", "he": "Hebrew",
}  # fmt: skip


def wilson_lower(successes: int, total: int, z: float = 1.959964) -> float:
    if total == 0:
        return 0.0
    share = successes / total
    centre = share + z * z / (2 * total)
    margin = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total * total))
    return (centre - margin) / (1 + z * z / total)


def _page(client: httpx.Client, params: dict, tries: int = 5) -> httpx.Response:
    """One page of rows. The dataset viewer answers 429 (rate limited) or 5xx
    under load: wait as long as Retry-After says, else 2, 4, 8, 16 s."""
    for attempt in range(tries):
        response = client.get(VIEWER, params=params)
        if response.status_code != 429 and response.status_code < 500:
            break
        if attempt == tries - 1:
            break
        try:
            wait = float(response.headers.get("Retry-After", ""))
        except ValueError:
            wait = 2.0 ** (attempt + 1)
        time.sleep(min(60.0, max(1.0, wait)))
    response.raise_for_status()
    return response


def fetch(locale: str, split: str = "train", limit: int = 20_000) -> list[dict]:
    rows: list[dict] = []
    with httpx.Client(timeout=60) as client:
        while len(rows) < limit:
            response = _page(
                client,
                {
                    "dataset": DATASET,
                    "config": locale,
                    "split": split,
                    "offset": len(rows),
                    "length": 100,
                },
            )
            time.sleep(0.5)  # a pause between pages keeps under the viewer's rate
            page = [item["row"] for item in response.json().get("rows", [])]
            rows += page
            if len(page) < 100:
                break
    return rows


def align(english: list[dict]) -> dict[str, dict]:
    """MASSIVE intent -> the MIZAN intent MIZAN's own Qasd reads for it, kept
    only when the majority's Wilson lower bound is above ½."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from tadbir import qasd

    read: dict[str, Counter] = defaultdict(Counter)
    for row in english:
        ranked = qasd.ranked(row["text"])
        read[row["label_text"]][ranked[0][0]] += 1
    found = {}
    for intent, counts in sorted(read.items()):
        label, hits = counts.most_common(1)[0]
        total = sum(counts.values())
        bound = wilson_lower(hits, total)
        found[intent] = {
            "mizan": label if bound > 0.5 else None,
            "share": round(hits / total, 3),
            "wilson_lower": round(bound, 3),
            "n": total,
        }
    return found


def sample(rows: list[dict], per_intent: int, seed: int = 0) -> list[dict]:
    by_intent: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_intent[row["label_text"]].append(row)
    rng = random.Random(seed)
    chosen = []
    for intent in sorted(by_intent):
        group = by_intent[intent]
        rng.shuffle(group)
        chosen += group[:per_intent]
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--locales", default="ta", help="MASSIVE configs, comma-separated")
    parser.add_argument("--lughah-per-intent", type=int, default=4)
    parser.add_argument("--qasd-per-intent", type=int, default=6)
    parser.add_argument("--out", default="massive-batches")
    parser.add_argument("--post", default="", help="MIZAN's URL, to send each batch")
    parser.add_argument("--token-file", default="")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    english = fetch("en")
    mapping = align(english)
    (out / "alignment.json").write_text(json.dumps(mapping, indent=1), encoding="utf-8")
    kept = {intent: entry["mizan"] for intent, entry in mapping.items() if entry["mizan"]}
    print(f"{len(kept)} of {len(mapping)} MASSIVE intents align to a MIZAN intent")
    batches = []
    for locale in [item.strip() for item in args.locales.split(",") if item.strip()]:
        rows = fetch(locale)
        source = f"https://huggingface.co/datasets/{DATASET} ({locale}/train)"
        language = [
            {"text": row["text"], "label": locale} for row in sample(rows, args.lughah_per_intent)
        ]
        batches.append(
            {
                "model": "lughah",
                "examples": language,
                "source": source,
                "licence": LICENCE,
                "language_name": NAMES.get(locale, ""),
            }
        )
        aligned = [row for row in rows if row["label_text"] in kept]
        intents = [
            {"text": row["text"], "label": kept[row["label_text"]]}
            for row in sample(aligned, args.qasd_per_intent, seed=1)
        ]
        batches.append({"model": "qasd", "examples": intents, "source": source, "licence": LICENCE})
    for number, batch in enumerate(batches):
        path = out / f"{number:02d}-{batch['model']}.json"
        path.write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
        print(path, batch["model"], len(batch["examples"]))
    if args.post:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=600) as client:
            for batch in batches:
                response = client.post(
                    f"{args.post.rstrip('/')}/api/tadbir/talim", json=batch, headers=headers
                )
                data = response.json()
                print(
                    batch["model"],
                    response.status_code,
                    {
                        key: data.get(key)
                        for key in ("status", "before", "after", "p_worse", "learned")
                    },
                )


if __name__ == "__main__":
    main()
