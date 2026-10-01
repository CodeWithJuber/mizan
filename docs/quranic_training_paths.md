# Reproducible Quranic training paths

The corpus covers all 114 surahs and the standard Hafs 6,236 numbered verses.
Preparation produces three separate objectives. It does not claim that a model
has learned the Quran, understands tafsir, or can give correct religious advice.

| Path | Real targets | Data in the verified snapshot |
| --- | --- | --- |
| `continuation` | Exact original Arabic bytes, including diacritics and negation | 6,236 Tanzil Uthmani Hafs verses |
| `morphology` | Attributed QAC segments, original ROOT/LEM/POS features and locations | 77,429 words, 128,219 annotated segments |
| `grounded_qa` | Quote a supplied interpretation with verse ID and translator | 6,236 Pickthall 1930 translations |

The Arabic text is the pinned Tanzil edition. QAC 0.4 is a separately identified
older edition, not a replacement for the original text. Its root and lemma
labels are linguistic annotations. They are not definitions, translations, or
religious conclusions. Pickthall is a translation and remains distinct from
the original Arabic. Grounded QA learns quotation and attribution; its expected
answer is deliberately included in retrieved context. Its scores measure use of
evidence, not unaided memorization or independent interpretation.

Preparation downloads known HTTPS sources at immutable revisions and requires
the recorded SHA-256 hashes. It retains original source files, their complete
copyright and licence metadata, QAC's original notice, and a preparation
manifest. No LLM generates, corrects, removes, or inserts words into the Quran.
Tanzil source terms allow verbatim copies with attribution; QAC carries its
original GNU GPL and embedded Tanzil BY-ND notice. The translation snapshot
records its public-domain original and upstream attribution. Source terms remain
in force separately from this repository's software licence.

Cross-checking the independently digitized KFGQPC Hafs edition finds the same
6,236 verse IDs. Their orthographic comparison agrees on 6,232 verses. Four
differences are retained, with both exact texts, at 2:72, 15:7, 27:20 and 36:22.
They involve hamza or joined/separate spelling. Orthographic normalization is
used only to report agreement; it never changes training targets. Tanzil embeds
unnumbered opening basmalas into the first verse outside surahs 1 and 9; the
comparison accounts for that edition convention without removing them from
the training edition. Other Hafs distributors also differ in pause marks and
diacritics, so a byte-identical match across editions is not claimed.

All paths share a deterministic split by complete surah. Surahs containing an
identical or comparison-folded repeated verse are joined into one component
before splitting. This prevents a verse held out in one surah from reappearing
in training in another. The initial seed 42 split reserves surahs 55, 57, 62,
75, 85, 87, 100, 104 and 109. The nominal 10% is a probability over components,
not a promise of 10% of verses; the manifest records actual counts. All three
objectives retain the same held-out surahs. Duplicate raw continuation targets
are deduplicated by the existing sequence trainer.

Run preparation from the repository root:

```bash
python -m scripts.prepare_quranic_data --cache /tmp/ruh-quran-cache --output /tmp/ruh-quran-data
```

Run a bounded CPU engineering smoke for one objective:

```bash
OMP_NUM_THREADS=2 python -m scripts.train_quranic_paths \
  --data-dir /tmp/ruh-quran-data --path continuation \
  --output /tmp/ruh-quran-smoke --steps 20 --max-seconds 120
```

A fresh smoke uses a small model to verify the complete path. It is not a
replacement for the 46M architecture. To continue trained V2 weights and AdamW,
add `--resume-from /private/run/candidate`; its sibling `training_state.pt` must
be retained. Legacy epoch 19 cannot be reinterpreted as a byte-token checkpoint.
Keep the original architecture and tokenizer files when comparing objectives.
Each independent objective starts from the same verified baseline so evaluation
can compare changes without silently mixing training histories.

Teacher-forced loss must be reported separately from actual generation:

```bash
python -m scripts.generate_quranic_predictions \
  --data-dir /tmp/ruh-quran-data --path continuation \
  --candidate /private/run/candidate --output-dir /private/run --samples 8
```

Generation scoring checks exact characters, diacritics, negation tokens, verse
citations and structured annotations. It includes actual generated responses
and marks promotion unapproved. Exactness checks are mechanical; semantic
evaluation of commentary needs qualified-source review. Do not treat falling
loss as proof of correct Quran quotation or chat quality.

`build_tafsir_path` accepts separately attributed commentary with an explicit
licence, snapshot hash and established training permission. No unverified
tafsir or hadith enters the three default paths. Hadith authenticity grading
and commentary are separate tasks and cannot be relabelled as Quran verses.

GPU notebooks must remain private, use verified free Kaggle quota, preserve
exit codes and stop within a bounded session. Before deleting temporary
compute, retain model/config/tokenizer/vocabulary, AdamW state, exact source
revision, data manifest and hashes, evaluation, step count and randomness
state. Validate a durable archive by reading it back and checking hashes. A
successful local copy alone does not establish that a cloud backup is durable.

The existing trainer stores model and optimizer continuation snapshots. Exact
bit-for-bit future replay also needs sampler/RNG state; objective runs must
record that limitation rather than promise identical replay after restart.
