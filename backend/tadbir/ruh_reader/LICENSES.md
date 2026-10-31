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
| `hinglish-1m:<row>:<column>` | [Abhishekcr448/Hinglish-Everyday-Conversations-1M](https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M), commit `cf040b1b80857c6038eb73ddad441f0b435e02a6`, `hinglish_conversations.csv`, SHA-256 `3ec4aa4f23394dc7e6ecef990453641fa85c0f03175ad60f1408e3b3c0c36484`; row and column (`input`/`output`) of the utterance | MIT (notice below) | training; held-out rows (3–8 words, groups the seeds' rule holds out): the Roman Hindi/Urdu part of the short-message slice; rows never read: v1.1's and test 3's slices |
| `clinc150:<split>:<index>` | [CLINC150](https://github.com/clinc/oos-eval) (clinc/oos-eval), commit `828f8093932c8fe6ca7936c3d2e52903b1c523de`, `data/data_full.json`, SHA-256 `36923c3705a59e08fe9c3883d8bc2dd966ef93e22cb78ac41171782a698d56e0`; split and index of the query | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) (notice below) | never trained on: English requests of test 3's gate (`build_fresh`), downloaded into `sources/clinc150/` |

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

**CLINC150** — "An Evaluation Dataset for Intent Classification and
Out-of-Scope Prediction", Larson, Mahendran, Peper, Clarke, Lee, Hill,
Kummerfeld, Leach, Laurenzano, Tang and Mars, EMNLP-IJCNLP 2019
([D19-1131](https://www.aclweb.org/anthology/D19-1131)); the dataset of
github.com/clinc/oos-eval, licensed under the Creative Commons Attribution 3.0
Unported licence (its `LICENSE` file at the pinned commit). Queries were
written by crowd workers. Changes: queries of 3–8 words are selected, those
whose words are, or nearly are, a text MIZAN has seen are left out; nothing of
it is trained on or shipped.

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
