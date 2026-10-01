"""RuhModelProvider.stream() — the chat loop calls provider.stream() as a context
manager; the Ruh provider previously inherited BaseLLMProvider.stream() which
raises NotImplementedError, so every ruh-provider turn died silently. These
tests pin the wrapper contract: context-manager protocol, single-chunk text
stream, and final response passthrough."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from providers import ContentBlock, LLMResponse  # noqa: E402
from providers_ruh import RuhModelProvider, _RuhStreamWrapper  # noqa: E402


class _FakeRuh(RuhModelProvider):
    """Skip model loading entirely; stub create() with canned output."""

    def __init__(self) -> None:
        super().__init__(model_path="/nonexistent", device="cpu")

    def create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        return LLMResponse(
            content=[ContentBlock(type="text", text="as-salamu alaykum")],
            stop_reason="end_turn",
            model="ruh-local",
            usage={"input_tokens": 3, "output_tokens": 4},
        )


def test_stream_wrapper_is_returned():
    provider = _FakeRuh()
    wrapper = provider.stream(model="ruh-local", max_tokens=64, system="sys", messages=[])
    assert isinstance(wrapper, _RuhStreamWrapper)


def test_stream_yields_single_text_chunk_and_final_response():
    provider = _FakeRuh()
    with provider.stream(model="ruh-local", max_tokens=64, system="sys", messages=[]) as s:
        chunks = list(s.text_stream)
        final = s.get_final_response()
    assert chunks == ["as-salamu alaykum"]
    assert final.model == "ruh-local"
    assert final.stop_reason == "end_turn"
    assert final.usage == {"input_tokens": 3, "output_tokens": 4}
    assert final.content[0].text == "as-salamu alaykum"


def test_stream_empty_text_yields_nothing():
    provider = _FakeRuh()

    def _empty_create(self, model, max_tokens, system, messages, tools=None, temperature=None):
        return LLMResponse(content=[], model="ruh-local")

    provider.create = _empty_create.__get__(provider, _FakeRuh)
    with provider.stream(model="ruh-local", max_tokens=64, system="sys", messages=[]) as s:
        assert list(s.text_stream) == []


def test_get_final_response_before_enter_raises():
    provider = _FakeRuh()
    wrapper = provider.stream(model="ruh-local", max_tokens=64, system="sys", messages=[])
    with pytest.raises(RuntimeError):
        wrapper.get_final_response()
