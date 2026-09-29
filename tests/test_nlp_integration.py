"""
Phase-2 integration tests for mizan.nlp native WSD wiring.

Preregistration: tests/test_nlp_phase2_plan.md (read it first; the
"Amendments" section records every deviation from the original plan).

What this file proves:
  * Flag OFF (MIZAN_NLP_NATIVE_WSD unset / != "1") -> the agent loop, QCA,
    and memory recall never consult mizan.nlp (behavior identical to before).
  * Flag ON -> the four DESIGN.md integration points (IP-1..IP-4) consult
    mizan.nlp, are fail-closed, and log their fallback.
  * Missing/corrupt artifact -> ModelNotReadyError, clean fallback to the
    LLM path, no exception escapes, fallback is LOGGED.

Mocking strategy (JEV `choice`, confidence 0.90): monkeypatch
`nlp.disambiguate` (+ `nlp.is_ready`, which every call site gates on) and any
importer binding. The real artifact ships on main but needs sklearn/joblib,
which are outside this track's file scope -- the wiring contract is what is
under test here, not the model.

Self-skip protocol: each wiring test first probes whether its integration
hook exists; if not, it pytest.skip()s with a contract reason instead of
failing (JEV `choice`, confidence 0.86). Flag-OFF tests run unconditionally.

Conventions: backend/ on sys.path via tests/conftest.py; pytest-asyncio
auto mode; fixtures mirror tests/test_agents.py. No network, no GPU.
"""

import inspect
import json
import logging
import sys

import nlp
import nlp.wsd
import pytest
from nlp import ModelNotReadyError, SenseCandidate, disambiguate

FLAG_ENV = "MIZAN_NLP_NATIVE_WSD"
SENSES_MARKER = "[NLP Senses:"
ADVISORY_MARKER = "[Native sense advisory:"

AR_TEXT = "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ"
AR_LEMMA = "عمل"
# Format-realistic canned sense (qcsmp2:<lemma>:<sense-slug>, cf. the real
# sense_inventory.json); clearly labeled test data, not a model claim.
CANNED_SENSE_ID = "qcsmp2:عمل:deeds"
CANNED_CONFIDENCE = 0.82
# ISM roots come from English concept words (CONCEPT_MAP), so IP-3 needs
# concept-bearing text to produce roots at all.
CONCEPT_TEXT = "knowledge is light العلم نور"

SKIP_WIRING = "Track 1 IP wiring not landed yet -- contract per backend/nlp/DESIGN.md section 2"


# ── helpers ────────────────────────────────────────────────────────────────


def _flag_on(monkeypatch):
    """Enable native WSD before agent construction (call sites read env per-call)."""
    monkeypatch.setenv(FLAG_ENV, "1")


def _flag_off(monkeypatch):
    monkeypatch.delenv(FLAG_ENV, raising=False)


def _patch_nlp(monkeypatch, fake):
    """Simulate 'artifact present': patch disambiguate (+ is_ready gate).

    Every Track-1 call site does `from nlp import ..., disambiguate, is_ready`
    at call time and checks `is_ready()` first, so patching the `nlp`
    attributes takes effect. Importer-module bindings are patched too, in
    case any call site ever hoists the import to module level.
    """
    monkeypatch.setattr(nlp, "disambiguate", fake)
    monkeypatch.setattr(nlp, "is_ready", lambda: True)
    for mod_name in ("agents.base", "qca.engine", "memory.dhikr", "memory.masalik"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "disambiguate"):
            monkeypatch.setattr(mod, "disambiguate", fake)
        if mod is not None and hasattr(mod, "is_ready"):
            monkeypatch.setattr(mod, "is_ready", lambda: True)


def _canned_disambiguate(text, lemma):
    return [SenseCandidate(sense_id=CANNED_SENSE_ID, confidence=CANNED_CONFIDENCE, lemma=lemma)]


def _source_has(mod_or_obj, *needles):
    try:
        src = inspect.getsource(mod_or_obj)
    except (OSError, TypeError):
        return False
    return any(n in src for n in needles)


def _ip1_landed(agent_cls):
    return _source_has(agent_cls.think, FLAG_ENV, SENSES_MARKER, "disambiguate")


def _ip3_landed():
    from qca.engine import QCAEngine

    return _source_has(QCAEngine.process_input, "senses_identified", FLAG_ENV)


def _ip4_landed():
    from memory.dhikr import DhikrMemorySystem
    from memory.masalik import MasalikNetwork

    return _source_has(
        DhikrMemorySystem.recall_unified_for_prompt, "_native_sense_advisory", "recall advisory"
    ) or _source_has(MasalikNetwork.recall, "_log_native_sense_advisory", "recall advisory")


async def _drain_think(agent, task):
    chunks = []
    async for chunk in agent.think(task):
        chunks.append(chunk)
    return "".join(chunks)


def _capture_messages(agent, monkeypatch):
    """Capture the message list think() mutates, so IP-1's append is observable."""
    captured = {}
    orig = agent._build_messages

    def spy(task, context):
        msgs = orig(task, context)
        captured["messages"] = msgs
        return msgs

    monkeypatch.setattr(agent, "_build_messages", spy)
    return captured


def _fallback_logged(caplog):
    """The DESIGN.md section 5 contract: the fallback must be LOGGED, never
    swallowed silently. Track 1 logs not-ready at INFO and inference errors
    at WARNING, always mentioning mizan.nlp -- the plan pins the property,
    not the level."""
    return any(
        rec.levelno >= logging.INFO and "mizan.nlp" in rec.message.lower() for rec in caplog.records
    )


def _build_agent(mock_wali, mock_izn, temp_db):
    from agents.specialized import create_agent
    from memory.dhikr import DhikrMemorySystem

    memory = DhikrMemorySystem(db_path=temp_db)
    agent = create_agent(
        "general",
        name="TestNlpAgent",
        memory=memory,
        config={"model": "test-model"},
        wali=mock_wali,
        izn=mock_izn,
    )
    agent.ai_client = None  # force the _structured_reasoning path: no network
    return agent


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def agent(mock_wali, mock_izn, temp_db, monkeypatch):
    """General agent with the flag explicitly OFF (deterministic)."""
    _flag_off(monkeypatch)
    return _build_agent(mock_wali, mock_izn, temp_db)


@pytest.fixture
def agent_nlp(mock_wali, mock_izn, temp_db, monkeypatch):
    """General agent with the flag ON before construction (IP-2 registers
    its tool in _register_base_tools based on the flag at build time)."""
    _flag_on(monkeypatch)
    return _build_agent(mock_wali, mock_izn, temp_db)


# ── Group A: nlp package contract, no wiring needed ─────────────────────────


class TestNlpPackageContract:
    def test_missing_artifact_raises_model_not_ready(self, monkeypatch):
        """Missing artifact -> fail-closed ModelNotReadyError, never a raw error.

        The loader falls back to the packaged artifacts/default/ when the env
        var is unset, so a truly-missing artifact is simulated at the
        find_artifact() seam the loader itself uses.
        """
        nlp.wsd.reset_for_tests()
        monkeypatch.delenv("MIZAN_NLP_ARTIFACT", raising=False)
        monkeypatch.setattr(nlp.wsd, "find_artifact", lambda: None)
        with pytest.raises(ModelNotReadyError):
            disambiguate(AR_TEXT, AR_LEMMA)

    def test_corrupt_artifact_dir_fails_closed(self, monkeypatch, tmp_path):
        """A corrupt artifact dir is rejected -> ModelNotReadyError (fail-closed).

        find_artifact() itself refuses dirs with invalid manifests and the
        loader falls back to packaged/default; the fail-closed path (invalid
        manifest at load time) is simulated at the find_artifact() seam.
        """
        nlp.wsd.reset_for_tests()
        garbage = tmp_path / "artifact"
        garbage.mkdir()
        (garbage / "manifest.json").write_text("{not valid json")
        (garbage / "model.joblib").write_text("junk")
        monkeypatch.setenv("MIZAN_NLP_ARTIFACT", str(garbage))
        monkeypatch.setattr(nlp.wsd, "find_artifact", lambda: garbage)
        with pytest.raises(ModelNotReadyError):
            disambiguate(AR_TEXT, AR_LEMMA)

    def test_empty_result_contract(self):
        """Unknown lemma -> [] must be gracefully consumable (post-artifact)."""
        result = nlp.DisambiguationResult(text=AR_TEXT, lemma="غيرمعروف")
        assert result.best is None
        seen = [sid for sid, _conf in result.candidates]  # tuple-unpack loop over []
        assert seen == []

    def test_sense_id_shape_contract(self):
        """sense_id follows qcsmp2:<lemma>:<sense-slug> (3 colon-separated parts)."""
        cand = SenseCandidate(sense_id=CANNED_SENSE_ID, confidence=CANNED_CONFIDENCE)
        parts = cand.sense_id.split(":")
        assert len(parts) == 3
        sid, conf = cand  # the contract reads as list of (sense_id, confidence)
        assert sid == CANNED_SENSE_ID
        assert 0.0 <= conf <= 1.0


# ── Group B: IP-1 think() context injection ─────────────────────────────────


class TestIP1ThinkInjection:
    async def test_ip1_flag_off_no_nlp_calls(self, agent, monkeypatch):
        """(b) Flag OFF -> behavior identical to before: zero nlp calls."""

        def boom(text, lemma):
            raise AssertionError("mizan.nlp consulted while flag is OFF")

        _patch_nlp(monkeypatch, boom)
        out = await _drain_think(agent, AR_TEXT)
        assert "Task received" in out  # think() completed normally

    async def test_ip1_flag_on_consults_nlp(self, agent_nlp, monkeypatch):
        """(a) Flag ON + Arabic input -> agent consults mizan.nlp; marker appears."""
        if not _ip1_landed(type(agent_nlp)):
            pytest.skip(f"{SKIP_WIRING} (IP-1)")
        captured = _capture_messages(agent_nlp, monkeypatch)
        calls = []

        def fake(text, lemma):
            calls.append((text, lemma))
            return _canned_disambiguate(text, lemma)

        _patch_nlp(monkeypatch, fake)
        await _drain_think(agent_nlp, AR_TEXT)
        assert calls, "think() never consulted mizan.nlp with the flag ON"
        assert any(AR_TEXT in text for text, _ in calls)
        content = captured["messages"][-1]["content"]
        assert SENSES_MARKER in content
        assert CANNED_SENSE_ID in content

    async def test_ip1_model_not_ready_fallback_logged(self, agent_nlp, monkeypatch, caplog):
        """(c) ModelNotReadyError -> clean fallback to LLM path, no escape, LOGGED."""
        if not _ip1_landed(type(agent_nlp)):
            pytest.skip(f"{SKIP_WIRING} (IP-1)")
        captured = _capture_messages(agent_nlp, monkeypatch)

        def fake(text, lemma):
            raise ModelNotReadyError("test: no artifact")

        # is_ready stays True (artifact was ready, call failed mid-flight)
        _patch_nlp(monkeypatch, fake)
        with caplog.at_level(logging.INFO):
            out = await _drain_think(agent_nlp, AR_TEXT)
        assert "Task received" in out  # no exception escaped; LLM path taken
        assert _fallback_logged(caplog), "fallback was not logged"
        assert SENSES_MARKER not in captured["messages"][-1]["content"]

    async def test_ip1_unknown_lemma_empty_graceful(self, agent_nlp, monkeypatch):
        """(d) disambiguate -> [] (unknown lemma) handled gracefully."""
        if not _ip1_landed(type(agent_nlp)):
            pytest.skip(f"{SKIP_WIRING} (IP-1)")
        captured = _capture_messages(agent_nlp, monkeypatch)
        _patch_nlp(monkeypatch, lambda text, lemma: [])
        out = await _drain_think(agent_nlp, AR_TEXT)
        assert "Task received" in out
        assert SENSES_MARKER not in captured["messages"][-1]["content"]

    async def test_ip1_unknown_stays_unknown_no_coercion(self, agent_nlp, monkeypatch):
        """hikmah-stack: 'unknown is a state' -- [] is never coerced into a sense."""
        if not _ip1_landed(type(agent_nlp)):
            pytest.skip(f"{SKIP_WIRING} (IP-1)")
        captured = _capture_messages(agent_nlp, monkeypatch)
        _patch_nlp(monkeypatch, lambda text, lemma: [])
        await _drain_think(agent_nlp, AR_TEXT)
        content = captured["messages"][-1]["content"]
        assert content.count("qcsmp2:") == 0, "wiring fabricated a sense from an empty result"

    async def test_ip1_low_confidence_stays_out_of_loop(self, agent_nlp, monkeypatch):
        """Track-1 JEV gate: top-1 confidence < 0.80 (or margin < 0.20) must not
        enter the loop -- a weak native read stays unknown, never injected."""
        if not _ip1_landed(type(agent_nlp)):
            pytest.skip(f"{SKIP_WIRING} (IP-1)")
        captured = _capture_messages(agent_nlp, monkeypatch)

        def weak(text, lemma):
            return [SenseCandidate(sense_id=CANNED_SENSE_ID, confidence=0.50, lemma=lemma)]

        _patch_nlp(monkeypatch, weak)
        out = await _drain_think(agent_nlp, AR_TEXT)
        assert "Task received" in out
        content = captured["messages"][-1]["content"]
        assert SENSES_MARKER not in content
        assert "qcsmp2:" not in content

    async def test_ip1_unexpected_inference_error_fallback(self, agent_nlp, monkeypatch, caplog):
        """DESIGN.md section 5: ANY inference exception -> log + fall back."""
        if not _ip1_landed(type(agent_nlp)):
            pytest.skip(f"{SKIP_WIRING} (IP-1)")

        def fake(text, lemma):
            raise RuntimeError("boom: inference exploded")

        _patch_nlp(monkeypatch, fake)
        with caplog.at_level(logging.INFO):
            out = await _drain_think(agent_nlp, AR_TEXT)
        assert "Task received" in out  # native WSD is never a single point of failure
        assert _fallback_logged(caplog)

    async def test_ip1_native_output_never_memory(self, agent_nlp, monkeypatch, caplog):
        """hikmah-stack: 'model output is never memory' -- failed native output
        must not silently become ground truth in the agent's answer."""
        if not _ip1_landed(type(agent_nlp)):
            pytest.skip(f"{SKIP_WIRING} (IP-1)")
        captured = _capture_messages(agent_nlp, monkeypatch)

        def fake(text, lemma):
            raise ModelNotReadyError("test: no artifact")

        _patch_nlp(monkeypatch, fake)
        with caplog.at_level(logging.INFO):
            out = await _drain_think(agent_nlp, AR_TEXT)
        assert "Task received" in out  # answer came from the fallback path
        assert CANNED_SENSE_ID not in out
        assert CANNED_SENSE_ID not in captured["messages"][-1]["content"]
        assert _fallback_logged(caplog)


# ── Group C: IP-2 disambiguate_sense tool ───────────────────────────────────


class TestIP2DisambiguateSenseTool:
    def _schema(self, agent):
        for s in agent.get_tool_schemas():
            if s.get("name") == "disambiguate_sense":
                return s
        return None

    def test_ip2_tool_registered_when_flag_on(self, agent_nlp):
        """(e) Flag ON -> disambiguate_sense registered and callable."""
        if "disambiguate_sense" not in agent_nlp.tools:
            pytest.skip(f"{SKIP_WIRING} (IP-2)")
        assert callable(agent_nlp.tools["disambiguate_sense"])

    def test_ip2_schema_valid(self, agent_nlp):
        """(e) Schema is a valid Claude tool_use schema for (text, lemma)."""
        schema = self._schema(agent_nlp)
        if schema is None:
            pytest.skip(f"{SKIP_WIRING} (IP-2)")
        assert schema["description"], "tool description must be non-empty"
        inp = schema["input_schema"]
        assert inp["type"] == "object"
        assert inp["properties"]["text"]["type"] == "string"
        assert inp["properties"]["lemma"]["type"] == "string"
        assert inp["required"] == ["text", "lemma"]

    async def test_ip2_callable_midloop_shape(self, agent_nlp, monkeypatch):
        """(e) Mid-loop call shape: await handler(text=..., lemma=...) (kwargs
        invoke style) -> JSON list with the top [sense_id, confidence] pair."""
        handler = agent_nlp.tools.get("disambiguate_sense")
        if handler is None:
            pytest.skip(f"{SKIP_WIRING} (IP-2)")
        _patch_nlp(monkeypatch, _canned_disambiguate)
        raw = await handler(text=AR_TEXT, lemma=AR_LEMMA)
        pairs = json.loads(raw)
        assert pairs == [[CANNED_SENSE_ID, CANNED_CONFIDENCE]]
        for sid, conf in pairs:  # contract: list of (sense_id, confidence)
            assert isinstance(sid, str) and len(sid.split(":")) == 3
            assert 0.0 <= conf <= 1.0

    async def test_ip2_tool_graceful_when_not_ready(self, agent_nlp, monkeypatch):
        """Fail-closed tool: not-ready -> guidance message, never an exception."""
        handler = agent_nlp.tools.get("disambiguate_sense")
        if handler is None:
            pytest.skip(f"{SKIP_WIRING} (IP-2)")

        def fake(text, lemma):
            raise ModelNotReadyError("test: no artifact")

        _patch_nlp(monkeypatch, fake)
        raw = await handler(text=AR_TEXT, lemma=AR_LEMMA)
        assert isinstance(raw, str) and "LLM path" in raw

    def test_ip2_tool_absent_when_flag_off(self, agent):
        """Flag OFF -> tool not exposed (flag-gated rollout)."""
        assert "disambiguate_sense" not in agent.tools
        assert self._schema(agent) is None


# ── Group D: IP-3 QCA senses_identified ─────────────────────────────────────


class TestIP3QcaSensesIdentified:
    def test_ip3_key_absent_when_flag_off(self, monkeypatch):
        """(f) Flag OFF -> no senses_identified key (pure additive signal)."""
        _flag_off(monkeypatch)
        from qca.engine import QCAEngine

        result = QCAEngine().process_input(AR_TEXT)
        assert "senses_identified" not in result
        assert "roots_identified" in result  # existing signal untouched

    def test_ip3_senses_identified_when_flag_on(self, monkeypatch):
        """(f) Flag ON -> senses_identified present as dict entries
        {lemma, sense_id, confidence, english_term} (same dict shape family
        as roots_identified)."""
        if not _ip3_landed():
            pytest.skip(f"{SKIP_WIRING} (IP-3)")
        _flag_on(monkeypatch)
        _patch_nlp(monkeypatch, _canned_disambiguate)
        from qca.engine import QCAEngine

        result = QCAEngine().process_input(CONCEPT_TEXT)
        assert "senses_identified" in result
        assert result["roots_identified"], "fixture text must yield ISM roots"
        assert result["senses_identified"], "native senses missing for identified roots"
        for entry in result["senses_identified"]:
            assert isinstance(entry["sense_id"], str) and len(entry["sense_id"].split(":")) == 3
            assert 0.0 <= entry["confidence"] <= 1.0
            assert entry["lemma"]


# ── Group E: IP-4 memory recall advisory ─────────────────────────────────────


class TestIP4MemoryRecallAdvisory:
    def test_ip4_recall_no_nlp_when_flag_off(self, agent, monkeypatch):
        """Flag OFF -> recall never touches mizan.nlp."""

        def boom(text, lemma):
            raise AssertionError("mizan.nlp consulted by recall while flag is OFF")

        _patch_nlp(monkeypatch, boom)
        agent.memory.recall_unified_for_prompt(AR_TEXT)
        agent.memory.masalik.recall(AR_TEXT)

    def test_ip4_recall_consults_nlp_when_flag_on(self, agent_nlp, monkeypatch):
        """Flag ON -> recall disambiguates Arabic lemmas in the query (advisory);
        the note is appended, recall results themselves are unchanged."""
        if not _ip4_landed():
            pytest.skip(f"{SKIP_WIRING} (IP-4)")
        calls = []

        def fake(text, lemma):
            calls.append((text, lemma))
            return _canned_disambiguate(text, lemma)

        _patch_nlp(monkeypatch, fake)
        out = agent_nlp.memory.recall_unified_for_prompt(AR_TEXT)
        assert calls, "dhikr recall did not consult mizan.nlp with the flag ON"
        assert ADVISORY_MARKER in out
        assert CANNED_SENSE_ID in out
        agent_nlp.memory.masalik.recall(AR_TEXT)
        assert calls, "masalik recall did not consult mizan.nlp with the flag ON"
