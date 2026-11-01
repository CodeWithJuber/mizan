"""An evaluation run recalls, learns and captures nothing (the benchmark of
27 Oct 2026: fresh test sessions recalled the owner's other chats, and test
answers were saved as training candidates)."""

from core.adaptive import AdaptiveStateStore
from memory import stateless


def test_nothing_is_learned_while_stateless(tmp_path):
    store = AdaptiveStateStore(str(tmp_path / "adaptive.db"))
    store.put("kept", {"n": 1})
    with stateless.bind():
        assert stateless.active()
        store.put("learned", {"n": 2})
        store.put("kept", {"n": 3})
    assert not stateless.active()
    assert store.get("learned") is None and store.get("kept") == {"n": 1}


def test_bind_never_turns_an_evaluation_off():
    with stateless.bind(), stateless.bind(False):
        assert stateless.active()


async def test_a_comparison_teaches_mizan_nothing(monkeypatch):
    from tadbir import muqabala

    seen = []

    async def base_arm(agent, prompt, history):
        seen.append(("base", stateless.active()))
        return {"text": "4"}

    async def mizan_arm(agent, prompt, context):
        seen.append(("mizan", stateless.active()))
        return {"text": "4", "verified": True, "spans": []}

    monkeypatch.setattr(muqabala, "base_arm", base_arm)
    monkeypatch.setattr(muqabala, "mizan_arm", mizan_arm)
    monkeypatch.setattr(muqabala, "checks", lambda prompt, base, mizan: {})
    await muqabala.compare(object(), "2+2", {}, [])
    assert sorted(seen) == [("base", True), ("mizan", True)]
    assert not stateless.active()


# ── Every memory writer respects a stateless run (audit of 29 Oct 2026) ──


async def test_recall_in_a_stateless_run_strengthens_nothing(tmp_path):
    from memory.dhikr import DhikrMemorySystem

    store = DhikrMemorySystem(str(tmp_path / "memory.db"))
    await store.remember("Maryam likes sabr stories", importance=0.6)

    def strength():
        conn = store._get_conn()
        try:
            return conn.execute(
                "SELECT access_count, stability, last_review FROM memories"
            ).fetchone()
        finally:
            store._release_conn(conn)

    before = strength()
    with stateless.bind():
        found = await store.recall("sabr stories")
    assert [m.content for m in found] == ["Maryam likes sabr stories"]
    assert strength() == before  # read, never reinforced
    await store.recall("sabr stories")
    assert strength()[0] == before[0] + 1  # an ordinary recall is a review


async def test_a_stateless_answer_leaves_no_task_record_pathway_or_graph_entry(
    monkeypatch, tmp_path
):
    from agents.specialized import create_agent
    from memory.dhikr import DhikrMemorySystem
    from providers import BaseLLMProvider, ContentBlock, LLMResponse
    from security.izn import IznPermission

    class OneReply(BaseLLMProvider):
        provider_name = "fixture"

        def create(self, **kwargs):
            return LLMResponse([ContentBlock(type="text", text="Sabr means patience.")], "m")

    class Graph:
        def __init__(self):
            self.entities, self.relationships = [], []

        async def add_entity(self, name, **kwargs):
            self.entities.append(name)

        async def add_relationship(self, source, target, **kwargs):
            self.relationships.append((source, target, kwargs.get("rel_type")))

    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = OneReply()
    agent.memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    agent.knowledge_graph = graph = Graph()
    encoded = []
    monkeypatch.setattr(agent.memory.masalik, "encode", lambda text, **kw: encoded.append(text))
    # A tool the run used, as the agent loop records it in Lawh tier 3.
    agent.qca.lawh.tiers[3]["TOOL:web_search:1"] = {"content": "searched"}

    def task_rows():
        conn = agent.memory._get_conn()
        try:
            return conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
        finally:
            agent.memory._release_conn(conn)

    with stateless.bind():
        result = await agent.execute("What does sabr mean?")
    assert result["success"]
    assert (task_rows(), encoded, graph.entities, graph.relationships) == (0, [], [], [])

    result = await agent.execute("What does sabr mean?")
    assert result["success"]
    assert task_rows() == 1 and len(encoded) == 1
    assert graph.entities == ["What does sabr mean?"]
    # The relationship loop reads Lawh's real tiers (it read `_tiers`, which does
    # not exist, and so had never written a relationship).
    assert graph.relationships == [("What does sabr mean?", "web_search", "used_tool")]
