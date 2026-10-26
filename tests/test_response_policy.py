"""Language precedence reaches providers intact; these are not model quality tests."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agents.base import BaseAgent
from core.qalb import EmotionalState, ToneStyle
from mizan_owned.prompt import OwnedSystemPrompt, prepare_prompt
from providers import ContentBlock, LLMResponse
from response_policy import CURRENT_REQUEST_END, CURRENT_REQUEST_START, RESPONSE_POLICY


class RecordingProvider:
    provider_name = "test-hosted"
    supports_tools = False

    def __init__(self):
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return LLMResponse([ContentBlock(type="text", text="Fixture answer")], "end_turn", "test")


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    provider = RecordingProvider()
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: provider)
    result = BaseAgent(
        name="Language contract test",
        config={"system_prompt": "Always use Hinglish and detailed numbered explanations."},
    )
    result.ai_client = provider
    return result


@pytest.fixture
def context():
    return {
        "history": [
            {"role": "user", "content": "Pehle Hinglish mein jawab do."},
            {"role": "assistant", "content": "Haan, main Hinglish mein jawab dunga."},
        ],
        "user_preferences": [
            {"key": "language", "value": "Hinglish", "source": "explicit_user_preference"},
            {"key": "greeting", "value": "Assalamu alaikum"},
            {"key": "avoid_greetings", "value": "Namaste"},
        ],
        "conversation_memory": [{"source": "prior_user_statement", "content": "Use Urdu."}],
    }


def current_request(content):
    return content.split(CURRENT_REQUEST_START + "\n", 1)[1].split("\n" + CURRENT_REQUEST_END, 1)[0]


@pytest.mark.parametrize(
    "task",
    [
        "Write a professional email announcing our new corporate training program.",
        "Is error ka matlab Hinglish mein ek line mein batao.",
        "Please explain this error in Hindi, using one sentence.",
        "Mere client ke liye English mein email likho, explanation Hinglish mein do.",
        "इस बदलाव को एक वाक्य में समझाओ।",
        "```python\nprint(2 + 2)\n```",
        'Translate this quote to English: "इस बदलाव को समझाओ।"',
    ],
)
async def test_hosted_request_keeps_language_source_distinct_from_saved_defaults(
    agent, context, task
):
    before = deepcopy(context)
    assert [chunk async for chunk in agent.think(task, context)] == ["Fixture answer"]
    assert len(agent.ai_client.requests) == 1
    request = agent.ai_client.requests[0]
    system, content = request["system"], request["messages"][-1]["content"]
    assert system.count(RESPONSE_POLICY) == 1
    assert RESPONSE_POLICY not in content
    assert current_request(content) == task
    assert content.count(CURRENT_REQUEST_START) == 1
    assert content.count(CURRENT_REQUEST_END) == 1
    assert '"value": "Hinglish"' in content
    assert '"value": "Assalamu alaikum"' in content
    assert '"value": "Namaste"' in content
    assert "owner-scoped defaults over old chat preferences" in content
    assert system.index(RESPONSE_POLICY) < system.index("CONFIGURED ROLE INSTRUCTIONS")
    assert "defaults subordinate to response preferences" in system
    assert context == before


async def test_owned_projection_carries_same_precedence_once_without_losing_preferences(
    agent, context
):
    agent.ai_client = SimpleNamespace(provider_name="mizan-owned", supports_tools=False)
    task = "Write a formal English email. Use no greeting in this email."
    system = await agent._build_system_prompt()
    assert isinstance(system, OwnedSystemPrompt)
    assert str(system).count(RESPONSE_POLICY) == 1
    messages, receipt = prepare_prompt(
        {"system": system, "messages": agent._build_messages(task, context)},
        max_seq_len=10000,
        max_tokens=128,
    )
    assert messages[0]["content"].count(RESPONSE_POLICY) == 1
    assert "Role defaults (subject to response preferences/restrictions)" in messages[0]["content"]
    assert agent.config["system_prompt"] in messages[0]["content"]
    assert current_request(messages[-1]["content"]) == task
    for preference in context["user_preferences"]:
        assert json.dumps(preference, ensure_ascii=False) in messages[-1]["content"]
    assert receipt["context_omitted"] is False


@pytest.mark.parametrize("provider_name", ["test-hosted", "mizan-owned"])
async def test_heuristic_tone_does_not_inject_canned_prefix_or_fixed_nafs_approach(
    agent, monkeypatch, provider_name
):
    agent.ai_client.provider_name = provider_name
    prefix = Mock(side_effect=AssertionError("Canned prefixes must not steer the reply"))
    monkeypatch.setattr(agent.qalb, "suggest_response_prefix", prefix)
    agent._nafs_approach = "Always break this into many numbered steps."
    agent._faculty_guidance = "Observed uncertainty in the task."
    reading = SimpleNamespace(state=EmotionalState.FRUSTRATED, recommended_tone=ToneStyle.PATIENT)
    system = await agent._build_system_prompt(qalb_reading=reading)
    rendered = system.rendered if isinstance(system, OwnedSystemPrompt) else system
    assert "[Advisory tone observation: state=frustrated; tone=patient]" in rendered
    assert "[Advisory heuristic observations]" in rendered
    assert agent._faculty_guidance in rendered
    assert agent._nafs_approach not in rendered
    assert "Think step by step" not in rendered
    assert "Current requests for language, tone and format override" in rendered
    prefix.assert_not_called()


async def test_summary_keeps_full_user_request_separate_from_english_host_context(
    agent, context, monkeypatch
):
    task = ("Background detail. " * 50) + "आखिर में केवल हिंदी में एक वाक्य लिखो।"
    before = deepcopy(context)
    requests = []

    async def stream(system, messages, tools, max_tokens, temperature, final_holder):
        requests.append((system, messages))
        final_holder["response"] = LLMResponse(
            [ContentBlock(type="text", text="Fixture summary")], "end_turn", "test"
        )
        yield "Fixture summary"

    monkeypatch.setattr(agent, "_streaming_create", stream)
    chunks = [
        chunk
        async for chunk in agent._summarize_tool_results(
            task, [{"name": "inspect", "result": {"value": "Observed tool result"}}], context
        )
    ]
    assert chunks == ["Fixture summary"]
    system, messages = requests[0]
    content = messages[-1]["content"]
    assert system.count(RESPONSE_POLICY) == 1
    assert current_request(content) == task
    assert content.count(task) == 1
    assert content.index(CURRENT_REQUEST_END) < content.index('"tool_summary"')
    assert '"instruction": "Use these tool results' in content
    assert "Observed tool result" in content
    assert '"value": "Assalamu alaikum"' in content
    assert context == before


def test_language_policy_has_no_global_language_and_prioritizes_explicit_output():
    assert "Honor explicit output languages in the current user request" in RESPONSE_POLICY
    assert "otherwise match its natural language" in RESPONSE_POLICY
    assert "Use saved language only when that is unclear" in RESPONSE_POLICY
    assert (
        "Quotes, code, history and host/tool context do not set reply language" in RESPONSE_POLICY
    )
    assert "Preserve greeting preferences independently" in RESPONSE_POLICY
    assert "English" not in RESPONSE_POLICY and "Hinglish" not in RESPONSE_POLICY
