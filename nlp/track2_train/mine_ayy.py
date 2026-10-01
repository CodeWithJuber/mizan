#!/usr/bin/env python3
"""Phase-3 Track-2: mine real interrogative أَيّ occurrences (targeted mining).

Quran lens: REAL Quranic occurrences only — every item cites its real
surah:ayah:word location, surface verified against the Tanzil Uthmani text
(the same source the Q-CSMP v2 build used). No synthetic items, no
perturbations, train split only. Test surah (55) and dev surah (33) excluded.

Selection was gloss-verified by hand (tabayyun): only clear interrogative
uses ("what/which/in what/for what/to what/which of ..."). Borderline
forms (أَيًّا 'by whatever' 17:110:7, أَيُّهُمْ 'those of them' 19:69:6,
أَيَّمَا 'whichever' 28:28:5, أَىِّ 'whatever' 82:8:2) were EXCLUDED.
Vocative يَا أَيُّهَا forms excluded (non-interrogative; the vocative senses
remain separate under Amendment A1's frozen 9-merge ontology).

Writes: nlp/mining/mined_interrogative_ayy.jsonl (24 records).
Inputs (env-overridable; defaults are the Track-2 workdir paths):
  MIZAN_QURAN_WORDS_CSV, MIZAN_TANZIL_XML, MIZAN_QCSMP_DATA.
"""

import csv
import json
import os
import sys
import xml.etree.ElementTree as ET

_HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.environ.get(
    "MIZAN_QURAN_WORDS_DIR", os.path.expanduser("~/workspace/research/papers/mizan-unpublished")
)
W162 = os.environ.get("MIZAN_QURAN_WORDS_CSV", f"{SUB}/quran_words-3_162_d6lx.csv")
TANZIL = os.environ.get("MIZAN_TANZIL_XML", f"{SUB}/quran-uthmani_151_vjvg.xml")
DATA = os.environ.get(
    "MIZAN_QCSMP_DATA", os.path.expanduser("~/workspace/research/stage2/qcsmp_v2.jsonl")
)
OUT = os.environ.get(
    "MIZAN_MINED_OUT", os.path.join(_HERE, "..", "mining", "mined_interrogative_ayy.jsonl")
)

# (loc, expected English gloss) — hand-verified interrogatives
TARGETS = [
    ("3:44:13", "(as to) which of them"),
    ("4:11:60", "which of them"),
    ("6:19:2", "What"),
    ("7:185:19", "So in what"),
    ("9:124:8", "Which of you"),
    ("11:7:14", "which of you"),
    ("17:57:8", "which of them"),
    ("18:12:4", "which"),
    ("18:19:28", "which is"),
    ("19:73:11", "Which"),
    ("20:71:23", "which of us"),
    ("26:227:17", "(to) what"),
    ("27:38:4", "Which of you"),
    ("31:34:21", "in what"),
    ("40:81:3", "Then which"),
    ("45:6:7", "Then in what"),
    ("53:55:1", "Then which (of)"),
    ("67:2:6", "which of you"),
    ("68:6:1", "Which of you"),
    ("68:40:2", "which of them"),
    ("77:12:1", "For what"),
    ("77:50:1", "Then in what"),
    ("80:18:2", "what"),
    ("81:9:1", "For what"),
]

EXCLUDED_SURAHS = {33, 55}  # dev / test surahs for أَيّ — never touch


def main():
    rows = {r["loc"]: r for r in csv.DictReader(open(W162, encoding="utf-8-sig"))}
    # TANZIL is the trusted local Tanzil Uthmani XML (the same source file the
    # Q-CSMP v2 build used), not untrusted network input.
    t = ET.parse(TANZIL).getroot()  # noqa: S314
    tanzil = {}
    for s in t.findall(".//sura"):
        for a in s.findall("aya"):
            tanzil[(int(s.get("index")), int(a.get("index")))] = a.get("text", "")
    ds_addr = set()
    for line in open(DATA, encoding="utf-8"):
        r = json.loads(line)
        ds_addr.add((r["lemma"], r["address"]))

    out = []
    for loc, gloss in TARGETS:
        x = rows[loc]
        assert x["lemma"] == "أَيّ", f"lemma drift at {loc}"
        sn, ay = int(x["sura"]), int(x["aya"])
        assert sn not in EXCLUDED_SURAHS, f"excluded surah at {loc}"
        assert ("أَيّ", loc) not in ds_addr, f"already in dataset: {loc}"
        assert x["word_en"].strip().lower().startswith(gloss.lower()[:8]), (
            f"gloss drift at {loc}: {x['word_en']!r} vs {gloss!r}"
        )
        txt = tanzil[(sn, ay)]
        ok = (x["form"] in txt) or (x["skeleton"] in txt)
        assert ok, f"tanzil surface check failed at {loc}"
        rec = {
            "lemma": "أَيّ",
            "root": x["root"],
            "root_translit": "ʾ-y-y",
            "pos": x["pos"],
            "surah": sn,
            "ayah": ay,
            "word": int(x["word"]),
            "address": loc,
            "form": x["form"],
            "translit": x["translit"],
            "word_en": x["word_en"],
            "morph": {
                "n_seg": x["n_seg"],
                "n_letters": x["n_letters"],
                "skeleton": x["skeleton"],
                "norm": x["norm"],
            },
            "sense": "so which",
            "sense_gloss": (
                "interrogative 'which/what' — targeted-mined real "
                "Quranic occurrence (Phase-3 Track-2)"
            ),
            "sense_alt": None,
            "label_source": "targeted-mining",
            "sense_quality": "n/a",
            "evidence": {"word_en": x["word_en"], "tanzil_surface_ok": True},
            "split": "train",
            "item_id": f"أَيّ_{loc.replace(':', '-')}_mined",
            "perturbation": "base",
            "prev": {
                "form": x["prev_form"] or None,
                "en": x["prev_en"] or None,
                "root": x["prev_root"] or None,
                "pos": x["prev_pos"] or None,
            },
            "next": {
                "form": x["next_form"] or None,
                "en": x["next_en"] or None,
                "root": x["next_root"] or None,
                "pos": x["next_pos"] or None,
            },
            "perturbed_surface": None,
        }
        out.append(rec)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"mined {len(out)} interrogative أَيّ items -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
