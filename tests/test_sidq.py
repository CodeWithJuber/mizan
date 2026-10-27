"""Sidq, the Truth Gate: what MIZAN can prove wrong never reaches the user."""

import pytest

from tadbir import isnad, sidq


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
