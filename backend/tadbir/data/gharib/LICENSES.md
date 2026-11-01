# Gharib word frequencies: sources and licences

`words.json.gz` holds, for English, Arabic, Hindi, Urdu, Tamil and Roman
Hindi/Urdu, each word written at least once per million running words, with
its frequency rounded to the centibel, and each language's average running-word
information. It is computed by `scripts/build_gharib.py` (`--check` rebuilds it
and compares its SHA-256) from the sources below. It holds words and numbers,
no sentence of any source.

| Languages | Source | Licence |
|---|---|---|
| `en`, `ar`, `hi`, `ur`, `ta` | [wordfreq](https://github.com/rspeer/wordfreq) 3.1.1 (Robyn Speer), its "small" lists (`wordfreq/data/small_<lang>.msgpack.gz`), read from the wheel `wordfreq-3.1.1-py3-none-any.whl` (SHA-256 `4b1c6ecffc6198be3396d5cf871c4423ca71c907c231348d352dd54d62b97473`); the SHA-256 of each list read is recorded in the file (`source.wordfreq.files`) | Data [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); code Apache-2.0 (none of it is used or shipped) |
| `hi-latn` | Lughah's Roman Hindi sentences (`backend/tadbir/data/lughah/hi-latn.tsv`, from [Hinglish-Everyday-Conversations-1M](https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M)), mixed with the English list above | MIT (notice in `../lughah/LICENSES.md`); the English part as above |

## Attribution (CC BY-SA 4.0)

Word frequencies from wordfreq by Robyn Speer, licensed under CC BY-SA 4.0:

> Robyn Speer. (2022). rspeer/wordfreq: v3.0 (v3.0.2). Zenodo.
> https://doi.org/10.5281/zenodo.7199437

**Changes:** each listed word was cut into words as MIZAN cuts text
(`core.adaptive.tokenize`), each digit written 0, the frequencies of the
pieces summed and divided by their total plus the share of running words the
list leaves out, and rounded to the centibel; words below once per million
were dropped. The Roman Hindi list is a mixture of Lughah's Roman Hindi words
(fitted by EM) and the English list. `words.json.gz` is therefore an adapted
work of wordfreq's data and is itself licensed under **CC BY-SA 4.0**.

wordfreq's data is in turn built from these sources, which its licence asks to
credit (from wordfreq's README):

- Wikipedia, the free encyclopedia (CC BY-SA);
- the Leeds Internet Corpus, University of Leeds Centre for Translation
  Studies (CC);
- ParaCrawl (CC);
- OPUS OpenSubtitles 2018 (<http://opus.nlpl.eu/OpenSubtitles.php>), from the
  OpenSubtitles project (<http://www.opensubtitles.org/>), used with
  attribution to OpenSubtitles;
- the SUBTLEX word lists (SUBTLEX-US and SUBTLEX-UK in the English list),
  created by Marc Brysbaert et al.
  (<http://crr.ugent.be/programs-data/subtitle-frequencies>): SUBTLEX is
  freely available data, and its authors are credited here as the permission
  wordfreq obtained requires;
- Google Books Ngrams (<http://books.google.com/ngrams>), acknowledged as the
  source;
- NewsCrawl 2014, GlobalVoices, OSCAR, and word counts from Twitter's
  streaming API and Reddit (no text of them is republished).

No Quran or hadith text is used.
