# Lughah corpus: sources and licences

Each line of the `*.tsv` files starts with where it came from (`source:id`).
`scripts/build_lughah_corpus.py` rebuilds the files from the sources below.

| Prefix | Source | Licence |
|---|---|---|
| `tatoeba:<id>` | Sentences from [Tatoeba](https://tatoeba.org) (eng, ara, urd, hin exports); the id is the Tatoeba sentence id | [CC BY 2.0 FR](https://creativecommons.org/licenses/by/2.0/fr/) |
| `hinglish-1m:<row>` | [Abhishekcr448/Hinglish-Everyday-Conversations-1M](https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M) on Hugging Face | MIT (notice below) |
| `quran:<surah>:<ayah>` | The Quran, Uthmani text from the [Tanzil Project](https://tanzil.net), read through api.alquran.cloud; every seventh ayah, verbatim and unchanged | Tanzil terms: verbatim copies with the source indicated and a link to tanzil.net |
| `index:<n>` | Surah, collection and narrator names from MIZAN's own Quran and hadith indexes | Names (facts) |
| `mizan:<n>`, `authored.tsv` | Lines written for MIZAN | CC0 |

## MIT notice (Hinglish-Everyday-Conversations-1M)

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
