"""Sidq, the Truth Gate: what MIZAN can prove wrong never reaches the user."""

import pytest

from tadbir import isnad, sidq

REAL_DEAD_LINKS = sidq.dead_links  # the tests below replace it with an offline stand-in


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    async def no_links(urls, timeout=4.0):
        return [url for url in urls if "made-up" in url]

    monkeypatch.setattr(sidq, "dead_links", no_links)

    async def no_source(text):
        return []

    monkeypatch.setattr("tadbir.muhasaba.scripture", no_source)


async def test_wrong_arithmetic_is_corrected(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    text, report = await sidq.gate("So 12 * 12 = 154, which is the area.")
    assert "12 * 12 = 144" in text and "154" not in text.split("_")[0]
    assert report["corrected"][0]["kind"] == "arithmetic"
    assert "Truth Gate" in text


async def test_flag_mode_keeps_the_text_and_marks_it(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "flag")
    text, report = await sidq.gate("So 12 * 12 = 154.")
    assert "= 154" in text and report["flagged"] and not report["corrected"]


async def test_an_action_with_no_receipt_is_removed(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    answer = "The total is 10. I ran the code and verified it in the sandbox."
    ledger = isnad.ledger(answer)
    text, report = await sidq.gate(answer, ledger)
    assert "I ran the code" not in text and "The total is 10." in text
    assert report["removed"][0]["kind"] == "action"


async def test_a_link_that_does_not_exist_is_removed(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    answer = "See [the guide](https://made-up.example/guide) and https://quran.com/2/255 too."
    text, report = await sidq.gate(answer, isnad.ledger(answer))
    assert "made-up" not in text and "the guide" in text and "https://quran.com/2/255" in text
    assert report["links"]["dead"] == ["https://made-up.example/guide"]


async def test_off_and_correct_answers_pass_untouched(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "off")
    assert await sidq.gate("2 + 2 = 5") == ("2 + 2 = 5", {})
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    text, report = await sidq.gate("2 + 2 = 4, as expected.")
    assert text == "2 + 2 = 4, as expected." and report == {"mode": "strict", "passed": True}


async def test_an_altered_quote_is_replaced_by_the_source(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    source = "قُلْ هُوَ اللَّهُ أَحَدٌ"

    async def differs(text):
        return [{"kind": "quote", "reference": "Quran 112:1", "source": source}]

    monkeypatch.setattr("tadbir.muhasaba.scripture", differs)
    text, report = await sidq.gate("Surah 112:1 says:\nقل هو الله واحد احد\nThat is tawhid.")
    assert f"> {source}" in text and "واحد" not in text and "That is tawhid." in text
    assert report["corrected"][0]["kind"] == "quote"


async def test_the_gate_runs_on_words_only_answers(monkeypatch, tmp_path):
    from agents.specialized import create_agent
    from providers import BaseLLMProvider, ContentBlock, LLMResponse
    from security.izn import IznPermission

    class Model(BaseLLMProvider):
        provider_name = "fixture"

        def create(self, **kwargs):
            return LLMResponse([ContentBlock(type="text", text="7 * 8 = 54.")], model="fixture")

    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "m.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = Model()
    monkeypatch.setattr(agent, "get_tool_schemas", lambda: [])
    result = await agent.execute("What is seven times eight, in words?")
    assert "7 * 8 = 56" in result["result"]
    assert result["usage"]["sidq"]["corrected"]


def test_every_learning_step_reaches_the_live_record():
    from types import SimpleNamespace

    from security.auth import bind_principal, reset_principal
    from tadbir import sijill, trace

    sijill.clear("u-live")
    tokens = bind_principal(SimpleNamespace(user_id="u-live", roles=["user"]))
    try:
        trace.event("learn", "hifz", kept=True, language="python")  # traced or not
        trace.event("verify", "furqan")  # not a learning step
        trace.event("learn", "majlis", agent="Katib", intent="build_and_run", worked=True)
    finally:
        reset_principal(tokens)
    notes = sijill.since("u-live")
    assert [note["kind"] for note in notes] == ["hifz", "majlis"]
    assert notes[0]["summary"] == "Kept a verified python program to re-run next time"
    assert "Katib" in notes[1]["summary"] and notes[1]["summary"].endswith("worked")
    assert sijill.since("u-live", after=notes[0]["seq"]) == notes[1:]
    assert sijill.since("someone-else") == []


async def test_every_redirect_hop_is_checked_and_a_private_one_is_not_followed(monkeypatch):
    import httpx

    from connectors import net_guard

    async def public(url, **kwargs):
        return None

    async def pinned(url):
        host = httpx.URL(url).host
        if host == "internal.example":
            raise ValueError("URL resolves to a non-public address")
        return httpx.URL(url), host, host

    asked = []

    def handler(request):
        host = request.headers["host"]
        asked.append(host)
        routes = {
            "a.example": httpx.Response(302, headers={"location": "http://internal.example/"}),
            "b.example": httpx.Response(301, headers={"location": "https://c.example/gone"}),
            "c.example": httpx.Response(404),
        }
        return routes.get(host, httpx.Response(200))

    real = httpx.AsyncClient
    monkeypatch.setattr(net_guard, "check_url", public)
    monkeypatch.setattr(net_guard, "pinned_destination", pinned)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    dead = await REAL_DEAD_LINKS(["https://a.example/x", "https://b.example/y"])
    assert dead == ["https://b.example/y"]  # moved, then gone
    assert "internal.example" not in asked  # the private hop was never opened
