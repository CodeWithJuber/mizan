# Quranic data: inputs and an evaluation-only canary

## The rule

The Quran is a source MIZAN quotes by lookup from pinned editions. It is never
a training target of Ruh or any other model in this repository. It (and hadith
text) may be an input, a retrieval source or an evaluation set. "Root-space"
means a root and pattern inventory catalogued from Quranic Arabic morphology,
used as lexicon ids. (Today Bayan's root inventory is a hand-authored list of
55 roots in `backend/qca/roots.py`, and new Ruh training uses Bayan v2 byte ids,
so even that catalogue is not yet built.)

## What enforces it in the Ruh data code

`ruh_model/data/scripture.py` holds the rule; `ruh_model/tests/test_scripture_targets.py`
checks it by building real windows and batches from a corpus that quotes an
ayah and asserting that no supervised label falls inside it.

- **Mixing weights.** `quran` and `hadith` default to 0 in `train_full`
  (`_DEFAULT_RATIOS`, `--quran-weight`, `--hadith-weight`) and in
  `RealDataPipeline`. A positive weight for a scripture domain, or for any
  source whose `kind` is `verified_quran`/`quran`/`hadith` or that carries
  `verse_columns`, is refused with an error citing the rule. No permission
  field reopens it: the old `verified_quran` exemption and the
  `training_permission` route for custom Quran/hadith sources are gone, and
  `DEFAULT_SOURCES` holds Arabic Wikipedia only.
- **Records.** `sequence.tokenize_record` (used by `train_sequence`,
  `train_quranic_paths` and the streaming pipeline) and `RuhDataset` refuse a
  record whose `domain` is `quran`/`hadith` or that is `evaluation_only`.
- **Declared spans.** A record lists the scripture it quotes in `scripture`
  (exact strings: an ayah, a translation of one, a hadith). Every occurrence of
  each string in the serialized record is a span; a declared string that does
  not occur verbatim is an error. `tokenize_record` removes every byte of a
  span from `target_mask`, and from the end-of-text target when the record ends
  inside one, and marks it in `scripture_mask`. `RuhCollator` sets the label to
  the ignore index (`pad_id`, 0) for every position that would predict a marked
  token, whatever `target_mask` says.
- **Known gap.** Only declared spans are masked. An ayah quoted inside a
  general corpus row (Arabic Wikipedia quotes many) is not detected; that needs
  a folded n-gram match against the pinned edition, which is not built.

Elsewhere in MIZAN, models that see the Quran see it as an input with a label
as the target: Fihris indexes the editions for retrieval and classifies a
query word's language from the translation's word list; Lughah's `quote` class
holds every seventh ayah as language-identification input; Iqtibas leaves those
rows out of its ordinary-speech bigram model.

## The three Quranic paths

The prepared corpus covers all 114 surahs and the standard Hafs 6,236 numbered
verses. It does not claim that a model has learned the Quran, understands
tafsir, or can give correct religious advice.

| Path | Supervised target | Scripture in the record | Data in the verified snapshot |
| --- | --- | --- | --- |
| `canary` | None: evaluation-only, refused as training data | The ayah is what the model must fail to reproduce | 6,236 Tanzil Uthmani Hafs verses |
| `morphology` | QAC labels per segment: location, tag, ROOT/LEM/POS features | The word's letters (Arabic and Buckwalter) are input only, declared and masked | 77,429 words, 128,219 annotated segments |
| `grounded_qa` | The citation `[Quran s:a; Pickthall, 1930 translation]` | The ayah and its translation are retrieved context; the quoted translation in the answer is masked | 6,236 Pickthall 1930 translations |

The Arabic text is the pinned Tanzil edition. QAC 0.4 is a separately identified
older edition, not a replacement for the original text. Its root and lemma
labels are linguistic annotations. They are not definitions, translations, or
religious conclusions. Pickthall is a translation and remains distinct from
the original Arabic; it is masked as scripture all the same, so a model is never
trained to produce it. Grounded QA learns to cite: its expected answer is
deliberately included in retrieved context, and only the citation is a target.
Its quote scores measure copying from context the model was never trained to
emit, not unaided memorization or independent interpretation.

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
used only to report agreement; it never changes the text. Tanzil embeds
unnumbered opening basmalas into the first verse outside surahs 1 and 9; the
comparison accounts for that edition convention without removing them from
the edition. Other Hafs distributors also differ in pause marks and
diacritics, so a byte-identical match across editions is not claimed.

All paths share a deterministic split by complete surah. Surahs containing an
identical or comparison-folded repeated verse are joined into one component
before splitting. This prevents a verse held out in one surah from reappearing
in training in another. The initial seed 42 split reserves surahs 55, 57, 62,
75, 85, 87, 100, 104 and 109. The nominal 10% is a probability over components,
not a promise of 10% of verses; the manifest records actual counts. All three
paths retain the same held-out surahs; the canary's held-out surahs are the ones
the generation check samples.

Run preparation from the repository root:

```bash
python -m scripts.prepare_quranic_data --cache /tmp/ruh-quran-cache --output /tmp/ruh-quran-data
```

Run a bounded CPU engineering smoke for one input-only path (`morphology` or
`grounded_qa`; `canary` is refused):

```bash
OMP_NUM_THREADS=2 python -m scripts.train_quranic_paths \
  --data-dir /tmp/ruh-quran-data --path morphology \
  --output /tmp/ruh-quran-smoke --steps 20 --max-seconds 120
```

A fresh smoke uses a small model to verify the complete path. It is not a
replacement for the 46M architecture. To continue trained V2 weights and AdamW,
add `--resume-from /private/run/candidate`; its sibling `training_state.pt` must
be retained. Legacy epoch 19 cannot be reinterpreted as a byte-token checkpoint.
Keep the original architecture and tokenizer files when comparing objectives.
Each independent objective starts from the same verified baseline so evaluation
can compare changes without silently mixing training histories.

Teacher-forced loss must be reported separately from actual generation. The
canary is the evaluation-only check of what a model must fail to reproduce:
prompted with the first third of a held-out ayah, its exact-match rate should be
no higher than a model never shown the Quran.

```bash
python -m scripts.generate_quranic_predictions \
  --data-dir /tmp/ruh-quran-data --path canary \
  --candidate /private/run/candidate --output-dir /private/run --samples 8
```

Generation scoring checks exact characters, diacritics, negation tokens, verse
citations and structured annotations. It includes actual generated responses
and marks promotion unapproved. Exactness checks are mechanical; semantic
evaluation of commentary needs qualified-source review. Do not treat falling
loss as proof of correct Quran quotation or chat quality.

`build_tafsir_path` accepts separately attributed commentary with an explicit
licence, snapshot hash and established training permission. The commentary may
be a target; the ayah it is about is declared scripture, so wherever the
commentary quotes it verbatim those bytes are masked. No unverified tafsir or
hadith enters the three default paths. Hadith authenticity grading
and commentary are separate tasks and cannot be relabelled as Quran verses.

GPU notebooks must remain private, use verified free Kaggle quota, preserve
exit codes and stop within a bounded session. Before deleting temporary
compute, retain model/config/tokenizer/vocabulary, AdamW state, exact source
revision, data manifest and hashes, evaluation, step count and randomness
state. Validate a durable archive by reading it back and checking hashes. A
successful local copy alone does not establish that a cloud backup is durable.
The Kaggle notebook that trained the old `continuation` objective is removed.
The `quran_morphology` and `quran_grounded_qa` notebooks pin revision
`6546f7d`, the commit that enforces this rule (their earlier pin, `37cdbd8`,
trained the word letters and the Pickthall translation as targets).

The existing trainer stores model and optimizer continuation snapshots. Exact
bit-for-bit future replay also needs sampler/RNG state; objective runs must
record that limitation rather than promise identical replay after restart.

The older `ruh_model.train_full` streaming CLI streams pinned Arabic Wikipedia
by default and has no Quran or hadith source. `--quran-weight` and
`--hadith-weight` default to 0 and a positive value exits with an argparse error
citing the rule; `RUH_DATA_SOURCES` cannot add a scripture source either. A
general source row may declare the scripture it quotes (`scripture`); such rows
are windowed by `tokenize_record` so those bytes are masked.

The split-aware `train_quranic_paths` CLI is the appropriate entry point for
candidate comparison and held-out generation on the input-only paths. The
older curriculum CLI does not itself provide an independent validation split
and must not be presented as a validated model simply because its training
epochs finish.
