# mizan.nlp — Design (Phase 1: interface skeleton)

**Status:** ✅ design + stub committed on `feature/mizan-nlp`. No behavior change
to the agent loop yet — `disambiguate()` raises `ModelNotReadyError` until the
trained artifact lands (fail-closed, JEV `choice` decision, confidence 0.91).

**Logical name:** `mizan.nlp` — Mizan's *own* NLP, its native Qur'anic Arabic
sense-disambiguation module. **Physical path:** `nlp/` — the wheel
packages only `backend` (`pyproject.toml` → `[tool.hatch.build.targets.wheel]`
→ `packages = ["backend"]`), and the codebase imports with `backend/` on
`sys.path` (e.g. `backend/agents/base.py` does `from agents... import ...`).
So `from nlp import disambiguate` works inside the repo/runtime, and
`from backend.nlp import disambiguate` works against the installed wheel.

## 1. Interface spec

```python
from nlp import disambiguate, is_ready, SenseCandidate, ModelNotReadyError

if is_ready():  # False in Phase 1
    for sense_id, confidence in disambiguate(text, lemma):
        ...
```

- **`disambiguate(text: str, lemma: str) -> list[SenseCandidate]`** —
  sorted by confidence, descending. `SenseCandidate` supports tuple
  unpacking, so the contract reads as the mission's `list of
  (sense_id, confidence)`.
- **`sense_id`**: stable string `"<dataset>:<root>:<sense>"`, e.g.
  `"qcsmp2:ktb:v3"`. The training track owns the inventory and MUST keep
  shipped IDs immutable (see `artifact.py`).
- **`confidence`**: float in `[0.0, 1.0]`, calibrated posterior P(sense |
  context). Must sum to ≈1.0 when multiple candidates are returned.
- **Failure modes**: `TypeError` (non-str args), `ValueError` (empty args),
  `ModelNotReadyError` (subclass of `NotImplementedError`) when no artifact
  is loaded. The agent loop must catch it and fall back to the LLM path —
  never swallow silently.
- **`is_ready() -> bool`**: Phase 1 always `False`. Phase 2 checks
  `MIZAN_NLP_ARTIFACT` env dir, then `nlp/artifacts/default/`.
- Files: `__init__.py` (public API), `wsd.py` (entry point), `types.py`
  (`SenseCandidate`, `DisambiguationResult`), `artifact.py` (training-track
  handoff contract).

## 2. Integration points (design only — Phase 2 wiring)

| # | Where | File:line (on main) | What changes in Phase 2 |
|---|-------|--------------------|--------------------------|
| IP-1 | Agent loop — QCA context injection | `backend/agents/base.py:585-592` (`think()`: `qca_input = self.qca.process_input(task[:500])` → `[QCA Context: ...]` appended to user message) | After the LLM-independent path: call `disambiguate()` on Arabic lemmas in the task, append `[NLP Senses: lemma→sense_id (conf)]` next to the heuristic root line. Guard with `try/except ModelNotReadyError`. This is where the agent *understands* Arabic input today — currently 100% heuristic (`qca/roots.py` `CONCEPT_MAP`) + LLM. |
| IP-2 | Native agent tool | `backend/agents/base.py:224` (`_register_base_tools`) and `:242` (`get_tool_schemas`; subclass override also at `:2407`) | Add `disambiguate_sense(text, lemma)` tool + schema. Lets the agent resolve a sense natively mid-loop without an LLM round-trip (latency + cost win). Tool returns JSON list of (sense_id, confidence). |
| IP-3 | QCA Layer 4 (ISM Root-Space) | `backend/qca/engine.py:861` (`QCAEngine.process_input`); ISM roots via `ism.find_roots_in_text(text)` (`:871`) | Augment `roots_identified` with native sense candidates (new optional key `senses_identified`, same dict shape family). Keeps the 7-layer pipeline, Furqan validation, and faculty loops untouched — pure additive signal. |
| IP-4 | Memory recall | `backend/memory/dhikr.py:410` (`recall_unified_for_prompt` — feeds the system prompt) and `backend/memory/masalik.py:474` (`recall` — spreading activation) | Disambiguate Arabic lemmas in the recall *query* before activation, so same-root/different-sense concepts don't merge in the Masalik network. Advisory-only in Phase 2 (behind flag). |

Deliberately NOT touched in Phase 2: `_build_messages` (`base.py:1218`)
prompt construction beyond what IP-1 appends; the QalbProcessor LLM params;
Lawh tiering; faculty engines. Small blast radius, additive signal.

## 3. Phase-2 wiring plan

1. **Artifact lands** → `wsd._load_artifact()` implemented: lazy
   process-global singleton, validates manifest via `ArtifactManifest.validate()`
   + `REQUIRED_FILES`, checks `SIZE_BUDGET_BYTES`.
2. **Flag-gated rollout**: env `MIZAN_NLP_NATIVE_WSD=1` (default off).
   Off = today's behavior, bit-for-bit.
3. **Wire IP-1 → IP-3 → IP-2 → IP-4** in that order (loop understanding
   first, memory last). Each guarded by `except ModelNotReadyError`.
4. **Eval gate**: enable only if held-out Q-CSMP v2 accuracy ≥ the number in
   the manifest's `eval_accuracy` (honest number, re-measured in CI).
5. **Fallback**: any inference exception → log + fall back to LLM path;
   native WSD is an accelerant, never a single point of failure.

## 4. What the trained artifact must provide

All enforced by `nlp/artifact.py` (`ArtifactManifest.validate()`):

- **Format**: directory containing exactly `manifest.json` (+ schema v1),
  `model.safetensors` (weights — **safetensors only, no pickle**),
  `tokenizer.json` (HF tokenizers format), `sense_inventory.json`
  (`sense_id → {lemma, gloss, examples}`).
- **License**: `Apache-2.0` for weights + inventory (compatible with the
  repo license). The Q-CSMP v2 dataset itself (Zenodo
  `10.5281/zenodo.23024527`) is NOT redistributed — only derived weights.
- **Size budget**: ≤ 250 MB total. Must run CPU-native alongside the
  FastAPI backend: no GPU assumption, cold-start < 10 s, single-call
  p95 < 300 ms.
- **Stability**: `sense_id`s immutable across artifact versions; manifest
  carries `eval_accuracy` (held-out WSD) as an honest, re-measurable number.

## 5. Open questions for the coordinator / training track

1. Tokenizer: reuse an existing Arabic tokenizer vs. train a tiny one on
   Q-CSMP v2? (Size budget pushes toward tiny.)
2. Should IP-2's tool be visible to the LLM as a tool, or loop-internal
   only (IP-1 style)? Loop-internal first — fewer moving parts.
3. Sense inventory source of truth: Q-CSMP v2 label set directly, or a
   curated Qur'anic subset? Inventory freeze must precede IP wiring.
