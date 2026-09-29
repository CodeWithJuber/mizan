# Artifact decisions — mizan.nlp Track-1 wiring

## 2026-09-29 — Artifact format: ship the joblib (JEV `choice`, conf 0.89)

**Question (to JEV, model jev-1.13.0):** Track 1 trained a REAL artifact — a
5.9 MB joblib of 48 per-lemma sklearn LogisticRegression classifiers (test
acc 0.7592). DESIGN.md §4 specified safetensors/no-pickle, but that was
written assuming a neural model. Ship the joblib as-is (+ manifest.json
schema v1 + trust-boundary documentation), or re-train as a neural model to
fit the safetensors spec?

**Options:** `ship-joblib` / `convert-neural`.
**Decision:** `ship-joblib` (confidence 0.89).
**Threshold logic (mine, not JEV's):** 0.89 > 0.7 operational threshold, and
independent assessment agrees — safetensors physically cannot hold sklearn
estimator objects; re-training would discard a real, preregistered-evaluated
artifact for a spec line written before the model choice was made. The honest
standard for sklearn artifacts is joblib; the spec was wrong, not the model.

**Consequences:**
- `artifact.py` contract revised: `REQUIRED_FILES` is now
  `(manifest.json, model.joblib, sense_inventory.json)`; `tokenizer.json`
  dropped (frozen char n-gram feature fn in `wsd.py`, no learned tokenizer).
- Trust boundary documented in `artifact.py` module docstring + manifest:
  manifest validated (schema + files + sha256) BEFORE unpickling; load only
  from the packaged dir or operator-set `MIZAN_NLP_ARTIFACT` — never
  remote/untrusted paths.
- Spec deviation from DESIGN.md §4 recorded here and in the wiring report.

## 2026-09-29 — Sense-ID scheme: `qcsmp2:<lemma>:<sense-slug>`

DESIGN.md said `<dataset>:<root>:<sense>`. Track-1 labels are lemma-keyed
sense slugs (e.g. `('يَوْم', 'judgment-day')`) — no root field is carried.
The lemma stands in for the root: `qcsmp2:يَوْم:judgment-day`. IDs remain
stable strings owned by the training track.

## 2026-09-29 — Unknown lemma → empty list (graceful, not guessed)

The loader returns `(None, None, {})` for unseen lemmas; `wsd.disambiguate()`
maps this to `[]`. An empty candidate list is the honest answer — the model
has no opinion — rather than a low-confidence guess that could leak into the
agent loop as signal. `ModelNotReadyError` is reserved strictly for the
artifact-missing case.
