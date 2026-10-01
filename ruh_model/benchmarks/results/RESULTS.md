# Ruh eval results — 2026-09-29

First measured numbers from the phase-0 eval harness. Every number below was
produced by running `ruh_model/eval/` on real data today; nothing is projected,
estimated, or carried over from slides. Where Ruh loses, it says so.

Conventions: ✅ verified (ran today, data + code cited) · ❌ could-not-verify
(data unavailable, honestly reported) · beta = harness is new, treat numbers as
preliminary.

---

## 1. Morphology: root accuracy vs QAC-derived gold ✅

| field | value |
|---|---|
| analyzer | `ArabicMorphAnalyzer` — rule-based, stdlib-only. **Not a trained model; this measures the analyzer, not Ruh.** |
| gold | `ruh_model/benchmarks/data/morph_gold_qac_test.tsv` — 172 unique (word, root) types from the Q-CSMP v2 **test split** (3,135 records; 35 particle records with no triliteral root excluded, not counted as misses). Roots trace to Quranic Arabic Corpus annotation (silver standard: expert-curated, not adjudicated for this purpose). |
| normalization | diacritics stripped + hamza normalized on **both** sides, exactly as the analyzer does internally |
| pattern | **not scored** — Q-CSMP v2 does not annotate the coarse pattern vocabulary |

**Result: root_accuracy = 0.3488 (60/172), n_failed = 0.**

Failure analysis (the useful part):
- Words containing U+0671 (superscript alef, standard Quranic orthography, e.g. ٱلناس): **0/40 correct**. The analyzer's prefix tables only know U+0627 alef, so Quranic ٱل never strips — garbage roots out.
- Words without U+0671: **60/132 = 0.4545**.

Verdict: weak baseline on Quranic orthography. The single highest-leverage fix is
U+0671 → alef normalization in the analyzer. Until then, no morphology-quality
claim beyond "rule-based baseline, 35% on Quranic wordforms."

CAMeL Tools head-to-head: ❌ could-not-verify — `camel_tools` could not be
installed in this sandbox (first attempt: /tmp full; second attempt on a
workspace venv: pip dependency resolution stalled for 7+ minutes grinding
through metadata, killed; even on success, `Analyzer("msa")` needs a
multi-GB pretrained-data download). The harness degrades to Ruh-only rather
than inventing a comparison, and so do we. Retry on a machine with proper
disk/network, then re-run the `--gold` command above *with* the CAMeL leg.

---

## 2. Q-CSMP v2 sense disambiguation: majority baseline on test split ✅

| field | value |
|---|---|
| data | Q-CSMP v2 test split, local copy of Zenodo DOI 10.5281/zenodo.23024527 (CC-BY-4.0) |
| n | 3,135 records · 48 lemmas · 88 senses |
| predictor | per-lemma majority sense — **in-sample** (built from the eval records themselves), so this is an optimistic floor, not a held-out baseline |

**Result: accuracy = 0.7831, macro-F1 = 0.4762.**

Rare-sense problem: **40/88 senses have zero recall** under the majority
baseline (by construction it can never predict a rare sense). The pilot card
reported 12/88 — same disease, this split shows it worse.

How this relates to the pilot bar (read carefully):
- Pilot (surface-stat model, pilot slice): acc 0.7592, macro-F1 0.5471, Δ_Q = −0.0555 — **surface statistics beat root/pattern/morph features at pilot scale. That negative headline stands.**
- These numbers (in-sample majority, full test split) are **not directly comparable** to the pilot's: different predictor, different slice. They define the floor a real model must beat on held-out data; they do not overturn Δ_Q.
- The real question — do root-space features beat surface stats once labels are trustworthy? — is still open. It needs (a) adjudicated labels at κ ≥ 0.61 (pending), (b) a non-linear model on held-out data (not built yet).

---

## 3. Dialect ID (NADI/MADAR) ❌

could-not-verify. NADI/MADAR are rights-restricted and not bundled; no licensed
copy exists in this environment. The harness refuses to synthesize data
(`FileNotFoundError` + download pointers — verified). **No dialect number is
claimed.** The majority-baseline floor the future normalization layer must beat
cannot be established until licensed data is obtained.

---

## What remains unverified (lā taqfu checklist)

- CAMeL head-to-head morphology numbers (install blocked; retry pending)
- Any trained-Ruh-model quality claim (no checkpoint is wired into any eval here)
- Cross-lingual / compression-quality parity (the 7.8× is params, not quality)
- Dialect normalization (engine not built; data not licensed)
- Adjudicated Q-CSMP labels at κ ≥ 0.61 (protocol exists, annotation not done)

## Reproducing

```bash
# morphology (needs repo root on sys.path; torch-free via _bootstrap)
python -m ruh_model.eval.morphology_eval \
  --gold ruh_model/benchmarks/data/morph_gold_qac_test.tsv \
  --no-camel --out /tmp/morph.json
# qcsmp (needs Q-CSMP v2 JSONL from Zenodo DOI 10.5281/zenodo.23024527)
python -m ruh_model.eval.qcsmp_eval --gold qcsmp_v2.jsonl --out /tmp/qcsmp.json
# dialect (exits 2 with pointers until licensed data is provided)
python -m ruh_model.eval.dialect_eval --gold nadi.tsv
```

JSON reports: `morphology_qac_roots.json`, `qcsmp_majority_baseline.json`,
`dialect_nadi_madar.json` (this directory).
