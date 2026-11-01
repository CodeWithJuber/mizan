"""Measure Qāmūs's reading of Roman Hindi and Urdu on running text.

Dakshina (Google; Roark et al., 2020; CC BY-SA 4.0) holds Hindi and Urdu
Wikipedia sentences romanized by native speakers, word-aligned. Nothing is
learned from it (the reading is built from Aksharantar and MASSIVE,
``scripts/build_qamus_roman.py``), and nothing of it is shipped. Each Roman
token is read by ``qamus.read_roman``; it is right when it is read as the
word the sentence wrote, and "same English" when the two words share a
translation. Recall counts the tokens whose word the reading can give at all.
Reported for every token and for content tokens (more information than an
average running word, ``ahl_dhikr.average_information``), on Dakshina's dev and
test sentences, with 95% Wilson intervals.

    python -I scripts/qamus_roman_eval.py --dakshina /tmp/dakshina_dataset_v1.0

``--dakshina`` is the unpacked ``dakshina_dataset_v1.0`` folder (only
``hi/romanized`` and ``ur/romanized`` are read), outside the repository.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.adaptive import wilson_bounds  # noqa: E402
from tadbir import ahl_dhikr, qamus  # noqa: E402


def sentences(folder: Path, language: str, split: str) -> list[list[tuple[str, str]]]:
    """The split's sentences as (native, roman) word pairs."""
    base = folder / language / "romanized"
    rejoined = (base / f"{language}.romanized.rejoined.tsv").read_text(encoding="utf-8")
    aligned: list[list[tuple[str, str]]] = [[]]
    name = f"{language}.romanized.rejoined.aligned.cased_nopunct.tsv"
    for line in (base / name).read_text(encoding="utf-8").splitlines():
        native, _, roman = line.partition("\t")
        if native == "</s>":
            aligned.append([])
        elif native:
            aligned[-1].append((native, roman))
    index = {line.split("\t")[0]: i for i, line in enumerate(rejoined.splitlines())}
    wanted = (base / f"{language}.romanized.rejoined.{split}.native.txt").read_text(
        encoding="utf-8"
    )
    return [aligned[index[line]] for line in wanted.splitlines() if line in index]


def share(hits: int, total: int) -> str:
    low, high = wilson_bounds(hits, total)
    return f"{hits}/{total} = {hits / max(1, total):.3f} [{low:.3f}, {high:.3f}]"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dakshina", type=Path, required=True)
    folder = parser.parse_args().dakshina.resolve()
    if ROOT in folder.parents:
        parser.error("--dakshina must be outside the repository")
    floor = ahl_dhikr.average_information()
    for language in ("hi", "ur"):
        readable = set(qamus._roman().get(language, {}).values())
        for split in ("dev", "test"):
            tokens = [
                (qamus._visible(native), qamus.roman_letters(roman))
                for sentence in sentences(folder, language, split)
                for native, roman in sentence
            ]
            for kind, chosen in (
                ("all", tokens),
                ("content", [t for t in tokens if ahl_dhikr.information(t[0]) > floor]),
            ):
                held = read = right = same = 0
                for native, roman in chosen:
                    held += native in readable
                    word = qamus.read_roman(roman).get(language) if roman else None
                    if word is None:
                        continue
                    read += 1
                    right += word == native
                    same += word == native or bool(
                        set(qamus.translate(word, "en")) & set(qamus.translate(native, "en"))
                    )
                print(
                    f"{language} {split} {kind}: tokens {len(chosen)}, readable {held}; "
                    f"precision {share(right, read)}, same English {share(same, read)}, "
                    f"recall {share(right, held)}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
