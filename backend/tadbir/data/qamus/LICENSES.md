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
values of slots the translators localised left out. No utterance is
redistributed.

Citation:

> Jack FitzGerald, Christopher Hench, Charith Peris, Scott Mackie, Kay
> Rottmann, Ana Sanchez, Aaron Nash, Liam Urbach, Vishesh Kakarala, Richa
> Singh, Swetha Ranganath, Laurie Crist, Misha Britan, Wouter Leeuwis, Gokhan
> Tur and Prem Natarajan. 2022. MASSIVE: A 1M-Example Multilingual Natural
> Language Understanding Dataset with 51 Typologically-Diverse Languages.
> arXiv:2204.08582.

Measured with, never shipped or learned from: FLORES-101 devtest
([gsarti/flores_101](https://huggingface.co/datasets/gsarti/flores_101) at
commit `1a45e707ea4b5ea3d6c71341f18bfca6a6e356a3`, CC BY-SA 4.0), read only by
`scripts/qamus_eval.py`.

No Quran or hadith text is used.
