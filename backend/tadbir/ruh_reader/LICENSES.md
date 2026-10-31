# Ruh reader corpus: sources and licences

The reader learns from Lughah's seeds (sources and licences in
`backend/tadbir/data/lughah/LICENSES.md`) and from its own corpus, which is
**not shipped**: `python -m tadbir.ruh_reader --corpus` (`corpus.py`) downloads
the sources below into `$MIZAN_DATA_DIR/corpora/ruh_reader/sources/` and
writes `train.tsv` and `short.tsv` there. Each line starts with where it came
from (`source:id`), and `manifest.json` records every source's URL, licence
and SHA-256.

| Prefix | Source | Licence | Used for |
|---|---|---|---|
| `tatoeba:<id>` | Sentences from [Tatoeba](https://tatoeba.org) (eng, hin, urd, ara per-language exports, `downloads.tatoeba.org/exports/per_language/`); the id is the Tatoeba sentence id. Every id Lughah's seeds use is left out. The exports change weekly: their SHA-256 is recorded, not pinned | [CC BY 2.0 FR](https://creativecommons.org/licenses/by/2.0/fr/) | training |
| `massive:<locale>:<id>` | [MASSIVE 1.1](https://github.com/alexa/massive) (Amazon), `amazon-massive-dataset-1.1.tar.gz`, SHA-256 `4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577`; locales en-US, hi-IN, ur-PK, ar-SA; the id is MASSIVE's utterance id (the same request in every locale) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (notice below) | `train` partition: training; `test` partition, 3–8 words: the held-out short-message slice |
| `hinglish-1m:<row>:<column>` | [Abhishekcr448/Hinglish-Everyday-Conversations-1M](https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M), commit `cf040b1b80857c6038eb73ddad441f0b435e02a6`, `hinglish_conversations.csv`, SHA-256 `3ec4aa4f23394dc7e6ecef990453641fa85c0f03175ad60f1408e3b3c0c36484`; row and column (`input`/`output`) of the utterance | MIT (notice below) | training; held-out rows (3–8 words, groups the seeds' rule holds out): the Roman Hindi/Urdu part of the short-message slice |

Changes made to the material: lines are selected (script, length, not a seed,
not held out, once, not scripture), whitespace is collapsed, and the reader
trains on the words as Lughah reads them (letters and marks, lower case). The
trained weights hold no line of text.

**Provenance to keep in mind.** The Hinglish set was written by a language
model (GPT-4o-mini, per its card), so it is synthetic Roman Hindi/Urdu, not
messages people sent; its held-out rows test the reader on that style only.
MASSIVE's utterances were written in English for SLURP and localised by
professional translators.

## Notices

**MASSIVE** — "MASSIVE: A 1M-Example Multilingual Natural Language
Understanding Dataset with 51 Typologically-Diverse Languages", FitzGerald et
al., 2022 ([arXiv:2204.08582](https://arxiv.org/abs/2204.08582)). Copyright
Amazon.com Inc. or its affiliates, licensed under CC BY 4.0. MASSIVE was
created by translating and localizing the English text of SLURP (Bastianelli
et al., EMNLP 2020), which is licensed under CC BY 4.0
([licence](https://github.com/pswietojanski/slurp/blob/master/LICENSE.txt));
some SLURP text is included in MASSIVE.

**Tatoeba** — sentences © their contributors on tatoeba.org, licensed under
CC BY 2.0 FR.

**Hinglish-Everyday-Conversations-1M** (MIT):

Copyright (c) Abhishekcr448

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN
AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Speaker (planned)

The Ruh speaker (`speaker.py`, `docs/ruh-speaker.md`) is a pilot prepared on
31 October 2026 and not yet run: nothing below has been downloaded for it.
`python -m tadbir.ruh_reader.speaker prepare --plan pilot` would fetch the
pinned files into its own folder on the training pod and record each file's
SHA-256 in `shards.json`. Each card was read on 31 Oct 2026 at the commit
given.

**Accepted** (pinned in `speaker.SOURCES`):

| Prefix | Source | Licence | Used for |
|---|---|---|---|
| `fineweb-edu:<id>` | [HuggingFaceFW/fineweb-edu](https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu) at commit `87f09149ef4734204d70ed1d046ddc9ca3f2b8f9`, `sample/10BT/000_00000.parquet` (SHA-256 `b1ba7b2c…e871`) and `001_00000.parquet` (`3fcf2dc6…5693`); the id is the Common Crawl record id | ODC-By 1.0, "also subject to CommonCrawl's Terms of Use" (card, Licensing Information). Its pages were chosen by a classifier trained on Llama-3-70B-Instruct's scores; the text is web text, no model's output | English training text, 4.5 GB |
| `fineweb-2-<subset>:<id>` | [HuggingFaceFW/fineweb-2](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2) at commit `af9c13333eb981300149d5ca60a8e9d659b276b9`: `data/hin_Deva/train/000_00000.parquet` (`071a6d4c…adad`), `data/urd_Arab/train/000_00000.parquet` (`a3e64b92…338d`), `data/arb_Arab/train/000_00000.parquet` (`814460aa…0583`), `data/hin_Latn/train/000_00000.parquet` (`e26effec…97ea`), `data/urd_Latn/train/000_00000.parquet` (`82937843…73bd`) | ODC-By 1.0, and Common Crawl's terms of use (card, Licensing Information); a URL and crawl per document, and an opt-out form | Hindi 4 GB, Urdu 3 GB, Arabic 3 GB, Roman Hindi/Urdu (both Latin subsets, all of them) |
| `tatoeba:<id>` | Tatoeba per-language exports, as above | CC BY 2.0 FR | training |
| `massive:<locale>:<id>` | MASSIVE 1.1, as above, **train partition only** (dev and test are the reader's measured slices) | CC BY 4.0 | training |

Changes made to the material: documents are selected (script, not a seed's
words, once, held out by SHA-256, never Quran text by `ruh_reader.scripture`,
never a run of 8 words of the six books of hadith), and tokenised; the
weights hold no document. The kept documents' ids are recorded so a removal
request can be honoured.

**Rejected** (`speaker.REJECTED`):

| Source | Card or paper | Why |
|---|---|---|
| [Abhishekcr448/Hinglish-Everyday-Conversations-1M](https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M) | MIT | Written by GPT-4o-mini (its card): OpenAI's terms forbid using output to develop competing models (`docs/consent.md`). The reader v1 above trains on it; changing that is the owner's decision |
| [ai4bharat/sangraha](https://huggingface.co/datasets/ai4bharat/sangraha) at `8b813c3f` | CC BY 4.0 | "Synthetic" is WikiMedia English translated (share-alike re-licensed); "Verified" holds OCR'd PDFs and transcribed "videos, podcasts, movies" with no source per row |
| [ai4bharat/IndicCorpV2](https://huggingface.co/datasets/ai4bharat/IndicCorpV2) | "released under a CC-0 license" | Crawled text AI4Bharat does not own, with no source per line |
| [statmt/cc100](https://huggingface.co/datasets/statmt/cc100) (`hi_rom`, `ur_rom`) | licence "unknown"; "no claims of intellectual property", Common Crawl terms | No licence of its own, no source per paragraph |
| Samanantar, BPCC | see `backend/tadbir/data/qamus/LICENSES.md` | NC with Quran translations inside; share-alike re-licensed |
| [LingoIITGN/PHINC](https://huggingface.co/datasets/LingoIITGN/PHINC) | CC BY 4.0 | Tweets its authors do not own: evaluation only, as Qamus uses it |
| Dakshina | CC BY-SA 4.0 | Evaluation only, as Qamus uses it |
| Wikipedia | CC BY-SA 4.0 | Share-alike: not in the first run, the owner's decision |

### ODC-By 1.0 (FineWeb-Edu, FineWeb-2)

FineWeb-Edu and FineWeb-2 by Hugging Face are made available under the Open
Data Commons Attribution License, <https://opendatacommons.org/licenses/by/1-0/>.
Their use is also subject to Common Crawl's terms of use,
<https://commoncrawl.org/terms-of-use>.
