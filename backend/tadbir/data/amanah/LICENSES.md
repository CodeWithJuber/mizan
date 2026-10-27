# Amanah corpus: sources and licences

Each line of the `*.tsv` files is `source:id<TAB>text`: one window of at most
300 characters of a source text. `scripts/build_amanah_corpus.py` rebuilds the
files from the sources below, each pinned to a Hugging Face revision.
`attack.tsv` and `data.tsv` train the model. The `heldout_*.tsv` files are only
for measuring it (`scripts/amanah_eval.py`) and are never trained on.

| Prefix | Source | Licence |
|---|---|---|
| `deepset:` | [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections) at `4f61ecb0`: train split for training, test split held out | Apache License 2.0 |
| `gandalf:` | [Lakera/gandalf_ignore_instructions](https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions) at `04737b65` | MIT |
| `jailbreak:` | [jackhhao/jailbreak-classification](https://huggingface.co/datasets/jackhhao/jailbreak-classification) at `2f2ceeb3`, `jailbreak` rows | Apache License 2.0 |
| `spml:` | [reshabhs/SPML_Chatbot_Prompt_Injection](https://huggingface.co/datasets/reshabhs/SPML_Chatbot_Prompt_Injection) at `02ce8084`, user prompts | MIT |
| `llmail-p2:`, `llmail-fp:` | [microsoft/llmail-inject-challenge](https://huggingface.co/datasets/microsoft/llmail-inject-challenge) at `1063bdf0`: phase 2 attack emails, held out; `emails_for_fp_tests`, even rows train and odd rows are held out | MIT |
| `fineweb:`, `fineweb-hard:`, `fineweb-page:` | [HuggingFaceFW/fineweb-edu](https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu) `sample-10BT`, read through the datasets-server. `fineweb-hard` holds sentences a first model wrongly flagged (hard negatives); `fineweb-page` holds 300 pages, never trained on | ODC-By 1.0; its use is also subject to the Common Crawl terms of use |
| `tatoeba:` | Sentences from [Tatoeba](https://tatoeba.org) already in MIZAN's Lughah corpus | CC BY 2.0 FR |
| `docs:` | Sentences from MIZAN's own documentation, any sentence a pattern flags left out | Same licence as MIZAN |
| `mizan:`, `authored.tsv` | Lines written for MIZAN: attacks in Roman Hindi/Urdu, Urdu, Hindi and Arabic, and ordinary text that only looks like one | CC0 |

Any window close to an AGI-test task (character-trigram Jaccard ≥ 0.4) was
dropped, so the test is not trained on.

## Apache License 2.0 (deepset/prompt-injections, jackhhao/jailbreak-classification)

Licensed under the Apache License, Version 2.0. You may obtain a copy of the
License at <https://www.apache.org/licenses/LICENSE-2.0>. Distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND. The rows are
reproduced as windows of at most 300 characters; no other change was made.

## MIT notice (Lakera/gandalf_ignore_instructions, reshabhs/SPML_Chatbot_Prompt_Injection, microsoft/llmail-inject-challenge)

Copyright (c) Lakera AI; Copyright (c) the SPML authors (reshabhs); Copyright (c) Microsoft Corporation.

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

## ODC-By 1.0 (FineWeb-Edu)

FineWeb-Edu by Hugging Face is made available under the Open Data Commons
Attribution License, <https://opendatacommons.org/licenses/by/1-0/>.

## CC BY 2.0 FR (Tatoeba)

Sentences from Tatoeba, <https://tatoeba.org>, licensed under
<https://creativecommons.org/licenses/by/2.0/fr/>.
