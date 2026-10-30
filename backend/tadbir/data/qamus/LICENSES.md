# Qāmūs lexicon: source and licence

Each `<x>-en.json.gz` file is a word-translation lexicon between English and
Hindi (`hi`), Urdu (`ur`), Arabic (`ar`) or Tamil (`ta`), computed by
`scripts/build_qamus.py` from the source below. The files hold words and the
probabilities MIZAN learned for them. They hold no utterance of the source.

| Source | Used | Licence |
|---|---|---|
| [MASSIVE 1.1](https://github.com/alexa/massive) (FitzGerald et al., 2022), read from the Hugging Face parquet conversion of [AmazonScience/massive](https://huggingface.co/datasets/AmazonScience/massive) at commit `ed58ac423a2f4121720918bf5301577edce4ffd3`; locales `en-US`, `hi-IN`, `ur-PK`, `ar-SA`, `ta-IN`. The SHA-256 of every file read is recorded in each lexicon (`source.files`) | Train split: the lexicon. Validation split: when EM stops and the cut-off. Test split: the precision@1 recorded in each file | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

Attribution: MASSIVE, Copyright Amazon.com Inc. or its affiliates, licensed
under CC BY 4.0. Changes: the aligned utterances were reduced to word
translation probabilities (IBM Model 1, both directions, multiplied), with the
values of slots the translators localised left out, name pairs that are not
transliterations of each other removed, and pieces of words written apart
removed. No utterance is redistributed.

Citation:

> Jack FitzGerald, Christopher Hench, Charith Peris, Scott Mackie, Kay
> Rottmann, Ana Sanchez, Aaron Nash, Liam Urbach, Vishesh Kakarala, Richa
> Singh, Swetha Ranganath, Laurie Crist, Misha Britan, Wouter Leeuwis, Gokhan
> Tur and Prem Natarajan. 2022. MASSIVE: A 1M-Example Multilingual Natural
> Language Understanding Dataset with 51 Typologically-Diverse Languages.
> arXiv:2204.08582.

Used to build, not shipped: [anyascii](https://github.com/anyascii/anyascii)
0.3.2 (ISC licence, Copyright (c) 2020-2023 Hunter WB) romanises the words of
name pairs, so the builder can test whether one is a transliteration of the
other. The lexicon holds none of its output.

Measured with, never shipped or learned from: FLORES-101 devtest
([gsarti/flores_101](https://huggingface.co/datasets/gsarti/flores_101) at
commit `1a45e707ea4b5ea3d6c71341f18bfca6a6e356a3`, CC BY-SA 4.0), read only by
`scripts/qamus_eval.py`.

## Roman Hindi and Urdu: `hi-latn.json.gz`

`hi-latn.json.gz` reads a word of Hindi or Urdu written in Latin letters as the
Devanagari or Urdu word it most probably spells. It holds Roman spellings and
the native words they are read as, and how they were fitted and measured,
computed by `scripts/build_qamus_roman.py` from the sources below. It holds no
pair of the sources as given and no sentence.

| Source | Used | Licence |
|---|---|---|
| [Aksharantar](https://huggingface.co/datasets/ai4bharat/Aksharantar) (AI4Bharat; Madhani et al., 2022), `hin.zip` and `urd.zip` at commit `e418c1fc928d9f5393af33268472cf20c1891be8`; the SHA-256 of each file read is recorded in the file (`source.files`). Rows whose source is Dakshina are left out | Train split (100,000 pairs per language): how native letters are written in Latin letters. Validation split: when EM stops. Test split: the accuracy recorded in the file | Manually collected pairs [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); pairs mined from Samanantar and IndicCorp, and existing sources, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| MASSIVE 1.1 (above), locales `hi-IN`, `ur-PK` and `en-US`, train split | Which Hindi and Urdu words there are and how often each is used (the prior); English words, which are never read as Roman Hindi | CC BY 4.0 |

Attribution: Aksharantar, AI4Bharat, IIT Madras. Changes: the transliteration
pairs were reduced to a model of how each letter is written (a noisy channel
fitted by EM), and that model to the most probable reading of each likely
spelling of MASSIVE's words.

Citation:

> Yash Madhani, Sushane Parthan, Priyanka Bedekar, Ruchi Khapra, Anoop
> Kunchukuttan, Pratyush Kumar and Mitesh Shantadevi Khapra. 2022. Aksharantar:
> Towards Building Open Transliteration Tools for the Next Billion Users.
> arXiv:2205.03018.

Measured with, never learned from or shipped:
[Dakshina](https://github.com/google-research-datasets/dakshina) v1.0 (Roark
et al., 2020; CC BY-SA 4.0), its romanized Hindi and Urdu Wikipedia sentences,
read only by `scripts/qamus_roman_eval.py`.

No Quran or hadith text is used.
