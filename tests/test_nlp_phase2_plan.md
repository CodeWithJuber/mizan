# MIZAN Phase 2 — Track 2: Integration Test Plan (preregistration)

**Status:** preregistered before implementation · **Branch:** `feature/mizan-nlp-phase2`
**Contract source:** `backend/nlp/DESIGN.md` §2–§3 (integration points IP-1…IP-4,
flag `MIZAN_NLP_NATIVE_WSD=1`, fail-closed fallback).
**Track 1 status at preregistration (2026-09-29):** no wiring landed — the branch
tip equals main (`acce8f97`); the env flag appears nowhere in `backend/` yet.

## Conventions this plan follows

- `tests/conftest.py` puts `backend/` on `sys.path` → tests import `nlp`,
  `agents.base`, `qca.engine`, `memory.dhikr`, `memory.masalik` directly
  (same as `tests/test_nlp.py`, `tests/test_agents.py`).
- `pytest-asyncio` runs in `auto` mode (`pyproject.toml`) → async tests need no
  decorator.
- No network, no GPU, small runtime. Agent construction reuses the
  `mock_wali` / `mock_izn` / `temp_db` fixtures and `create_agent("general", …)`.
- **Self-skip protocol for wiring-dependent tests:** each IP test first probes
  whether Track 1's hook exists (tool registration / source marker / output
  key). If absent, the test `pytest.skip()`s with reason
  `"Track 1 IP-N wiring not landed yet — contract per backend/nlp/DESIGN.md §2"`.
  The tests activate automatically when Track 1 lands; nothing needs editing.
  Flag-OFF tests (b, f-off, IP-4-off) run unconditionally — they pass on the
  unwired code *and* pin the flag gate once wiring lands.
- The fake `disambiguate` is injected via `monkeypatch.setattr` on **both**
  `nlp.disambiguate` and `agents.base.disambiguate` (if the latter binding
  exists), so the tests are robust to either import style Track 1 uses.

## Shared fixtures (in `tests/test_nlp_integration.py`)

| Fixture | What it proves / provides |
|---|---|
| `ar_task` | Arabic fixture input: `"إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ"`, lemma `"عمل"` (matches `test_nlp.py` fixtures). |
| `canned_senses(lemma)` | Fake `disambiguate` returning `[SenseCandidate("qcsmp2:ktb:v3", 0.82, lemma)]`. |
| `agent` (function-scoped) | `create_agent("general", …)` with `ai_client=None` (so `think()` takes the cheap `_structured_reasoning` path, no LLM). |
| `drain_think(agent, task)` | Helper draining the `think()` async generator to completion. |
| `message_spy(agent, monkeypatch)` | Wraps `_build_messages` to capture the message list `think()` mutates, so IP-1's `[NLP Senses: …]` append is observable without an LLM. |
| `flag_on(monkeypatch)` / `flag_off(monkeypatch)` | Set / delete `MIZAN_NLP_NATIVE_WSD` **before** agent construction (robust whether Track 1 reads the flag at import or per-call). |

## Test inventory

### Group A — `nlp` package contract, no wiring needed (always run)

| ID | Test | Proves | Pass criteria |
|---|---|---|---|
| A1 | `test_missing_artifact_raises_model_not_ready` | Missing artifact → fail-closed, never a raw `OSError`/`JSONDecodeError` | `disambiguate(AR_TEXT, "عمل")` raises `ModelNotReadyError` with `MIZAN_NLP_ARTIFACT` unset |
| A2 | `test_corrupt_artifact_dir_fails_closed` | A corrupt artifact dir (garbage files) is treated as *no* artifact | Same raise with `MIZAN_NLP_ARTIFACT` → tmp dir of garbage |
| A3 | `test_empty_result_contract` | The graceful-empty contract exists at type level (`DisambiguationResult.best is None` for `[]`) | `.best is None`; tuple-unpack loop over `[]` is a no-op |
| A4 | `test_sense_id_shape_contract` | `sense_id` follows `qcsmp2:<lemma>:<sense-slug>` (3 colon-separated parts, cf. real `sense_inventory.json`) | `SenseCandidate` accepts and round-trips a 3-part id |

### Group B — IP-1: `think()` context injection (`backend/agents/base.py`)

Contract (DESIGN.md §2): after the QCA roots line, call `disambiguate()` on
Arabic lemmas in the task and append `[NLP Senses: lemma→sense_id (conf)]`
next to it, guarded by `try/except ModelNotReadyError` (and per §5, *any*
inference exception → **log + fall back to the LLM path**; never a single
point of failure).

| ID | Test | Proves | Pass criteria | Runs now? |
|---|---|---|---|---|
| B1 | `test_ip1_flag_on_consults_nlp` (task a) | Flag ON + Arabic input → agent path consults `mizan.nlp` and the `[NLP Senses]` context appears | Fake `disambiguate` (+`is_ready→True`) patched; fake called ≥1× with the task text; captured `messages[-1]["content"]` contains `"[NLP Senses:"` and the canned sense id | skip until IP-1 lands |
| B2 | `test_ip1_flag_off_no_nlp_calls` (task b) | Flag OFF → behavior identical to before: zero `nlp` calls | Fake (raises `AssertionError` if called) never called; `think()` completes normally | **yes** |
| B3 | `test_ip1_model_not_ready_fallback_logged` (task c) | `ModelNotReadyError` → clean fallback, no exception escapes, fallback is **logged** | `think()` completes; `caplog` has a `WARNING`+ record on logger `mizan.nlp` (or the agent logger) mentioning fallback; no `"[NLP Senses:"` injected | skip until IP-1 lands |
| B4 | `test_ip1_unknown_lemma_empty_graceful` (task d) | `disambiguate` → `[]` (unknown lemma) handled gracefully | `think()` completes; no exception; no `"[NLP Senses:"` marker injected (nothing to report) | skip until IP-1 lands |
| B4b | `test_ip1_unknown_stays_unknown_no_coercion` (hikmah: "unknown is a state") | Empty result is never coerced into a fabricated sense | `think()` completes; count of `"qcsmp2:"` sense ids in final message content == 0 | skip until IP-1 lands |
| B5 | `test_ip1_unexpected_inference_error_fallback` | DESIGN §5: *any* inference exception → log + fall back | Fake raises `RuntimeError("boom")`; `think()` completes; fallback logged; no escape | skip until IP-1 lands |
| B5b | `test_ip1_native_output_never_memory` (hikmah: "model output is never memory") | Failed native output never silently becomes ground truth in the answer | After `ModelNotReadyError`: canned sense id appears 0× in messages AND in yielded output; answer comes from the fallback path (`"Task received"` in output) | skip until IP-1 lands |

**Log contract the tests pin (Track 1 must implement):** on fallback, log at
`WARNING` on logger `"mizan.nlp"` with a message containing `"fallback"`.

### Group C — IP-2: `disambiguate_sense` native tool

Contract: tool named `disambiguate_sense(text, lemma)` registered in
`_register_base_tools` + schema in `get_tool_schemas`; returns a JSON list of
`(sense_id, confidence)` pairs; callable mid-loop as `await handler(params)`.

| ID | Test | Proves | Pass criteria | Runs now? |
|---|---|---|---|---|
| C1 | `test_ip2_tool_registered_when_flag_on` (task e) | Tool is registered and callable when flag is ON | `"disambiguate_sense" in agent.tools` | skip until IP-2 lands |
| C2 | `test_ip2_schema_valid` (task e) | Schema is a valid Claude tool_use schema | `name`/`description` non-empty; `input_schema.type == "object"`; `properties` has `text`+`lemma` (type `string`); `required == ["text", "lemma"]` | skip until IP-2 lands |
| C3 | `test_ip2_callable_midloop_shape` (task e) | Mid-loop call shape: `await handler(text=..., lemma=...)` (kwargs invoke style) → JSON list with the top `[sense_id, confidence]` pair | `json.loads(result)` == `[[canned_id, 0.82]]`; pair well-formed, confidence in `[0,1]` | skip until IP-2 lands |
| C4 | `test_ip2_tool_absent_when_flag_off` | Flag OFF → tool not exposed (flag-gated) | `"disambiguate_sense" not in agent.tools` | **yes** |

### Group D — IP-3: QCA `senses_identified` (`backend/qca/engine.py`)

Contract: `QCAEngine.process_input` augments `roots_identified` with native
sense candidates under a new optional key `senses_identified` (same dict
shape family); flag-gated.

| ID | Test | Proves | Pass criteria | Runs now? |
|---|---|---|---|---|
| D1 | `test_ip3_senses_identified_when_flag_on` (task f) | Key present when flag ON | `"senses_identified" in QCAEngine().process_input(concept_text)`; entries are dicts `{lemma, sense_id, confidence, english_term}` with well-formed values | skip until IP-3 lands |
| D2 | `test_ip3_key_absent_when_flag_off` (task f) | Key absent when flag OFF (pure additive signal) | `"senses_identified" not in result` | **yes** |

### Group E — IP-4: memory recall advisory (`dhikr.py`, `masalik.py`)

Contract: with the flag ON, `recall_unified_for_prompt` (and/or
`MasalikNetwork.recall`) disambiguates Arabic lemmas in the recall *query*
before activation — advisory-only.

| ID | Test | Proves | Pass criteria | Runs now? |
|---|---|---|---|---|
| E1 | `test_ip4_recall_consults_nlp_when_flag_on` | Flag ON → recall path consults `mizan.nlp` | Fake `disambiguate` called during `recall_unified_for_prompt(AR_TEXT)` (or `masalik.recall`) | skip until IP-4 lands |
| E2 | `test_ip4_recall_no_nlp_when_flag_off` | Flag OFF → recall never touches `nlp` | Fake (raises if called) never called | **yes** |

## What is deliberately NOT tested here

- The trained artifact's accuracy (training track owns the eval gate;
  DESIGN.md §3.4 — `eval_accuracy` is re-measured in CI).
- Latency budgets (cold-start < 10 s, p95 < 300 ms) — CI-only concerns.
- `_build_messages` prompt construction beyond IP-1's append (DESIGN.md:
  deliberately untouched in Phase 2).

## Acceptance

- `ruff check` clean on both new files; Python ≥ 3.11.
- `pytest tests/test_nlp_integration.py` green under
  `pip install -e ".[dev,nlp]"` — no network, no GPU.
- This plan committed **before** the test implementation
  (`tests/test_nlp_phase2_plan.md`).

## Amendments (recorded 2026-09-29 — preregistration is a living document)

1. **Track 1 landed mid-task.** Branch tip moved `acce8f97` → `7ba88d1d`
   (commits `c1af69e3` IP-1+IP-2, `d9e55dff` IP-3, `7a02a63e` IP-4a,
   `7ba88d1d` IP-4b). The self-skip probes now fire: 21/21 tests run,
   0 skipped, all green against the real wiring.
2. **Real artifact on main** (`nlp` v0.2.0, `backend/nlp/artifacts/default/`):
   Group A now exercises the real loader. `sense_id` format is
   `qcsmp2:<lemma>:<sense-slug>` (canned test ID updated to
   `qcsmp2:عمل:deeds`); unknown lemma → `[]` is now real behavior.
3. **Log contract relaxed (property, not level).** DESIGN.md §5 requires
   "log + fall back" without a level; Track 1 logs not-ready at INFO and
   inference errors at WARNING, always mentioning `mizan.nlp`. The tests
   pin INFO+ mentioning `mizan.nlp` — the never-swallowed-silently property.
4. **IP-3 shape:** `senses_identified` is a list of dicts
   `{lemma, sense_id, confidence, english_term}` (same dict shape family as
   `roots_identified`), not `(sense_id, confidence)` tuples.
5. **IP-2 shape:** mid-loop invocation is kwargs-style
   (`await handler(text=..., lemma=...)`); the tool returns the gated top-1
   `[sense_id, confidence]` pair (empty list when below the gate).
6. **Tests patch `nlp.is_ready → True`** alongside the fake `disambiguate`
   to simulate artifact-present — every call site gates on `is_ready()`.
7. **Added:** `test_ip1_low_confidence_stays_out_of_loop` (pins Track 1's
   JEV-gated 0.80/0.20 threshold — a weak native read stays unknown) and
   `test_ip2_tool_graceful_when_not_ready` (tool returns guidance, never raises).
8. **D1 uses English-concept text** (`"knowledge is light العلم نور"`)
   because ISM roots come from `CONCEPT_MAP` English terms.
9. **JEV log:** mocking strategy `choice` → monkeypatch-bindings (0.90);
   skip protocol `choice` → self-skip-probes (0.86); mock-vs-real-artifact
   `noul` → YES mock (0.76) — dep changes out of scope, CI runtime small.
9. **Group A missing/corrupt tests simulate at the `find_artifact()` seam**
   (2026-09-29, post-CI): the preregistered versions deleted/set
   `MIZAN_NLP_ARTIFACT` expecting fail-closed, but the loader intentionally
   falls back to the packaged `artifacts/default/` (shipped in-repo), so CI
   never saw ModelNotReadyError — 2 failures. Fix: `test_missing_artifact…`
   patches `nlp.wsd.find_artifact → None`; `test_corrupt_artifact…` patches
   it to a dir with an invalid manifest (the real fail-closed path:
   `json.load` raises → `_LOAD_ERROR` → ModelNotReadyError). Env-var-only
   simulation was the wrong seam; the tests now pin the true fail-closed
   contract.
10. **ruff I001 in `tests/test_nlp.py`** (2026-09-29): import order corrected
    (`import pytest` before `import nlp`) — the earlier fix attempt had the
    order backwards and CI's lint job caught it.
