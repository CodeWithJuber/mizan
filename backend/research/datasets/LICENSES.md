# Research datasets: sources and licences

Only the files below are in the repository. Everything else the research
scripts read is downloaded from its original source when they run, or built
from it, and is never committed (`.gitignore` lists the names).

## Shipped

| File | Source | Licence |
|---|---|---|
| `raw/arabic_font.ttf` | Amiri Regular 1.002, Copyright 2010-2022 The Amiri Project Authors, <https://github.com/aliftype/amiri>. Used to draw Arabic labels in the figures | SIL Open Font License 1.1 (`LICENSES/OFL-1.1.txt`) |
| `wajh_deen_tagged.csv`, `wajh_ummah_tagged.csv` | The occurrences of دين and أمة: each row's location and words are read from the Quranic Arabic Corpus (below); the sense (`face`), confidence and basis were written for MIZAN | Rows written for MIZAN: same licence as MIZAN. The words are the Quran's; their reading is the Quranic Arabic Corpus's, credited below |

## Downloaded or built when needed

| File | Source | Licence | Read by |
|---|---|---|---|
| `raw/qac_raw.txt` | Quranic Arabic Corpus morphology v0.4 (Kais Dukes, University of Leeds, <https://corpus.quran.com>), Arabic-script copy at [mustafa0x/quran-morphology](https://github.com/mustafa0x/quran-morphology) commit `8f38b39016824284f9ed16ae15069ff9102c4acf`, SHA-256 `742bfac59941b2cb09736d5b7aae694af50792261fb8450cbf6afafcc340645f` (the copy `tadbir/sarf.py` also pins). `analyzer/quran_word_analyzer.py` downloads it on first use and refuses another digest | GNU General Public License, with the corpus's terms of use: verbatim copies only, the source indicated and linked. Not redistributed here | the analyzer |
| `raw/wbw_en.json` | Quran.com word-by-word English and transliteration (api.quran.com v4) | Terms of use unclear: not redistributed. Optional: without it the English columns are blank | the analyzer |
| `quran_words.csv`, `roots_summary.csv` | Built by `analyzer/quran_word_analyzer.py build` from the two files above | Derived from the Quranic Arabic Corpus (and Quran.com's glosses when present): not redistributed | the experiments |
| `hadith_tokens.txt` | Arabic text of Sahih al-Bukhari, Sahih Muslim and Sunan Abi Dawud from [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api) (`editions/ara-*.min.json`), cut into normalised words. `experiments/partA2_sizematched.py` and `partA_baseline.py` download it | The repository is released under the Unlicense, but it does not say where its texts come from or on what terms, so the text is fetched rather than shipped | the baseline experiments |
| `poetry_tokens.txt`, `tabari_tokens.txt` | A classical poetry sample (the experiment names arbml/ashaar) and a sample of al-Ṭabarī's tafsīr, cut into normalised words | No documented source or licence: removed. `experiments/partD_baselines.py` skips a register whose file is missing | `partD_baselines.py` |

The experiment scripts are a record of the October 2026 study; they read their
inputs from `data/` and `output/` next to themselves, as they were run.
Their results are in `../results/`: numbers, with short examples of a few words and\ntheir glosses for the cases they discuss.

## Quranic Arabic Corpus notice

The corpus's own header, as its download page gives it, in part:

> Quranic Arabic Corpus (morphology, version 0.4)
> Copyright (C) 2011 Kais Dukes
> License: GNU General Public License
>
> Permission is granted to copy and distribute verbatim copies of this file,
> but CHANGING IT IS NOT ALLOWED. [...] provided its source (the Quranic Arabic
> Corpus) is clearly indicated, and a link is made to http://corpus.quran.com to
> enable users to keep track of changes. [...] This copyright notice shall be
> included in all verbatim copies of the text, and shall be reproduced
> appropriately in all works derived from or containing substantial portion of
> this file.

The full header and the corpus are at <https://corpus.quran.com/download/>.
