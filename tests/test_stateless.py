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
