# mizan.nlp — native Qur'anic Arabic word-sense disambiguation

**Status (2026-09-29):** the module ships with a real trained artifact and
**all four agent-loop integration points are wired**, gated behind
`MIZAN_NLP_NATIVE_WSD=1` (default off) — see
[Integration points](#integration-points).

## What it is

`mizan.nlp` (`nlp/`) is Mizan's own NLP: native Qur'anic Arabic
word-sense disambiguation (WSD). Given Arabic text and a lemma, it returns
ranked sense candidates with confidences — no LLM call, no network.

It is **not a neural model**. The shipped artifact is 48 per-lemma
scikit-learn `LogisticRegression` classifiers (lbfgs, C=1.0) over frozen
character 2–4-gram surface+context features, trained 2026-09-29 on
[Q-CSMP v2](https://doi.org/10.5281/zenodo.23024527) (48 lemmas, 96 senses). The 5.9 MB `model.joblib` lives in
[`nlp/artifacts/default/`](../../nlp/artifacts/default/)
next to its `manifest.json` (schema v1) and `sense_inventory.json`.

> **Design revision, recorded honestly:** [`DESIGN.md` §4](../../nlp/DESIGN.md)
> specified `model.safetensors` ("safetensors only, no pickle") — written
> assuming a neural model. Track 1 trained a real sklearn artifact instead,
> and safetensors physically cannot hold sklearn estimator objects.
> The spec was revised, not the model: `REQUIRED_FILES` is now
> `(manifest.json, model.joblib, sense_inventory.json)`, decided via JEV
> `choice` (confidence 0.89) and recorded in
> [`artifacts/DECISIONS.md`](../../nlp/artifacts/DECISIONS.md).
> The old assumption is kept visible here rather than rewritten away.

## API

```python
from nlp import disambiguate, is_ready, SenseCandidate, ModelNotReadyError
# (backend/ on sys.path; against the installed wheel: from backend.nlp import ...)

if is_ready():                      # False when no valid artifact is present
    for sense_id, confidence in disambiguate(text, lemma):
        ...
```

- `disambiguate(text: str, lemma: str) -> list[SenseCandidate]` — candidates
  sorted by confidence, descending; confidences sum to ≈1.0.
  `SenseCandidate` supports tuple unpacking, so each item reads as
  `(sense_id, confidence)`.
- `sense_id` is a stable string `"qcsmp2:<lemma>:<sense-slug>"`, e.g.
  `"qcsmp2:آيَة:sign"`. IDs are owned by the training track and immutable
  across artifact versions.
- **Fail-closed:** raises `ModelNotReadyError` when no valid artifact is
  loaded. The agent loop must catch it and fall back to the LLM path —
  never swallow it silently.
- **Honest abstention:** an unknown lemma returns `[]`. The model has no
  opinion rather than a guessed sense; `ModelNotReadyError` is reserved
  strictly for the artifact-missing case.

Example (real output from the shipped artifact):

```text
text : تِلْكَ آيَاتُ اللَّهِ نَتْلُوهَا عَلَيْكَ بِالْحَقِّ
lemma: آية
  qcsmp2:آيَة:sign    0.9732
  qcsmp2:آيَة:verse   0.0268
```

## Measured limits

From `manifest.json` (`backend/nlp/artifacts/default/manifest.json`) —
whole-surah holdout, n=627, preregistered 2026-09-29 11:40 +04 before any
test evaluation:

| Measure       | Value                                                                          |
| ------------- | ------------------------------------------------------------------------------ |
| Test accuracy | 0.8150 (n=627 whole-surah holdout; bootstrap CIs not recomputed for 96 senses) |
| Macro-F1      | 0.6380 (over the full 96-sense universe; absent senses contribute 0.0)         |
| Artifact size | 5.9 MB joblib (sha256 pinned in the manifest)                                  |
| Coverage      | 48 lemmas / 96 senses — anything else returns `[]`                            |

Honest note (from the manifest itself): retrained-model predictions are
bit-for-bit identical to the remapped baseline on all 627 test items — the
measured gain vs the 97-sense baseline comes from ontology simplification
(the AYY vocative micro-merge), not from retraining. Treat 0.8150 as
accuracy against the merged Q-CSMP v2 labels, not against human gold
judgment. The win-bar comparator passed 4/4 gates.

Latency/cold-start budgets (cold-start < 10 s, single-call p95 < 300 ms)
are **design budgets from `DESIGN.md` §4, not measurements**. Do not cite
them as measured.

## Trust boundary

`model.joblib` is a pickle-family file. The loader validates the manifest
(schema + required files + sha256 checksums) **before** unpickling, and
loads only from the packaged `artifacts/default/` directory or an
operator-set `MIZAN_NLP_ARTIFACT` directory. Never load remote or untrusted
artifact paths. See `artifact.py` and the manifest's `trust_boundary`
field.

## Integration points

The relationship is **propose / admit**: native WSD proposes sense
candidates; the agent loop admits them (or ignores them and falls back to
the LLM path). WSD output is advisory signal, never a write to memory or
belief — an unresolved disagreement between the native path and the LLM
path stays visible as a conflict, not silently folded.

| #    | Where                                                                                      | Wiring                                                                                                                                                                 | Status |
| ---- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| IP-1 | Agent loop, QCA context injection (`backend/agents/base.py` `think()`, ~L711)              | Appends `[NLP Senses: lemma→sense_id (conf)]` next to the heuristic root line, via the fail-closed `_native_sense_bits()` helper                                       | Landed |
| IP-2 | Native agent tool (`_register_base_tools`, `get_tool_schemas`, `_tool_disambiguate_sense`) | `disambiguate_sense(text, lemma)` tool returning JSON `[[sense_id, confidence]]` or `[]`; never raises — failures return a message directing the agent to the LLM path | Landed |
| IP-3 | QCA Layer 4, ISM Root-Space (`backend/qca/engine.py` `process_input`, ~L969)               | Additive `senses_identified` key alongside `roots_identified`; the 7-layer pipeline and Furqan validation are untouched                                                | Landed |
| IP-4 | Memory recall (`backend/memory/dhikr.py` ~L509, `backend/memory/masalik.py` ~L564)         | Advisory native-sense note on the recall query before spreading activation                                                                                             | Landed |

Rollout is flag-gated: `MIZAN_NLP_NATIVE_WSD=1` (default off; off means
today's behavior, bit-for-bit). The flag is consumed in all four files via
`_nlp_native_wsd_enabled()`. Admission is quantified: a sense is admitted
only at top-1 confidence ≥ 0.8 with margin ≥ 0.2 over the runner-up
(`NLP_MIN_SENSE_CONFIDENCE`, `NLP_MIN_SENSE_MARGIN` in
`backend/agents/base.py`); weaker candidates are skipped and the loop
continues on heuristics + LLM.
Deliberately untouched: prompt construction beyond IP-1's append, the
QalbProcessor LLM params, Lawh tiering, and faculty engines.

## Run it

```bash
pip install -e ".[nlp]"   # scikit-learn, joblib, numpy
python -c "
from nlp import disambiguate, is_ready
print(is_ready())
for sense_id, conf in disambiguate('تِلْكَ آيَاتُ اللَّهِ نَتْلُوهَا عَلَيْكَ بِالْحَقِّ', 'آية'):
    print(sense_id, round(conf, 4))
"
# qcsmp2:آيَة:sign 0.9732
# qcsmp2:آيَة:verse 0.0268
```

`pip install pymizan` (PyPI 3.0.0) does **not** include `nlp` —
the native module currently ships from source only.

## Further reading

- [`backend/nlp/DESIGN.md`](../../nlp/DESIGN.md) — interface spec and wiring plan
- [`backend/nlp/artifacts/DECISIONS.md`](../../nlp/artifacts/DECISIONS.md) — artifact-format and sense-ID decisions
- [`backend/nlp/artifacts/default/manifest.json`](../../nlp/artifacts/default/manifest.json) — the honest numbers
- [`tests/test_nlp.py`](../../../tests/test_nlp.py) — contract tests
