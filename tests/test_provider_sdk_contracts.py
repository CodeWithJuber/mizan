"""Check provider tool contracts through the real current SDK HTTP stacks."""

import json

import anthropic
import httpx
import httpx2
import openai

from providers import AnthropicProvider, OpenAICompatibleProvider

TOOL = {
    "name": "read_file",
    "description": "Read a workspace file",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
}


def test_current_openai_sdk_preserves_tool_schema_arguments_and_usage():
    def respond(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["messages"][0] == {"role": "system", "content": "Use workspace tools"}
        assert body["tools"][0]["function"]["parameters"] == TOOL["input_schema"]
        return httpx.Response(
            200,
            json={
                "id": "contract-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "contract-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Reading your file.",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"src/main.py"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            },
        )

    provider = OpenAICompatibleProvider(api_key="local-sdk-contract-placeholder")
    provider._client.close()
    with openai.OpenAI(
        api_key="local-sdk-contract-placeholder",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as client:
        provider._client = client
        result = provider.create(
            "contract-model",
            64,
            "Use workspace tools",
            [{"role": "user", "content": "Read it"}],
            tools=[TOOL],
        )

    assert result.content[0].text == "Reading your file."
    assert result.content[1].type == "tool_use"
    assert result.content[1].name == "read_file"
    assert result.content[1].input == {"path": "src/main.py"}
    assert result.stop_reason == "tool_use"
    assert result.usage["input"] == 7
    assert result.usage["output"] == 3
    assert result.usage["total_tokens"] == 10


def test_current_anthropic_sdk_httpx2_preserves_tools_and_usage():
    def respond(request):
        assert request.url.path == "/v1/messages"
        body = json.loads(request.content)
        assert body["system"] == "Use workspace tools"
        assert body["tools"] == [TOOL]
        return httpx2.Response(
            200,
            json={
                "id": "contract-message",
                "type": "message",
                "role": "assistant",
                "model": "contract-model",
                "content": [
                    {"type": "text", "text": "Reading your file."},
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "read_file",
                        "input": {"path": "src/main.py"},
                    },
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 7, "output_tokens": 3},
            },
        )

    provider = AnthropicProvider(api_key="local-sdk-contract-placeholder")
    provider._client.close()
    with anthropic.Anthropic(
        api_key="local-sdk-contract-placeholder",
        http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),
    ) as client:
        provider._client = client
        result = provider.create(
            "contract-model",
            64,
            "Use workspace tools",
            [{"role": "user", "content": "Read it"}],
            tools=[TOOL],
        )

    assert result.content[0].text == "Reading your file."
    assert result.content[1].type == "tool_use"
    assert result.content[1].name == "read_file"
    assert result.content[1].input == {"path": "src/main.py"}
    assert result.stop_reason == "tool_use"
    assert result.usage == {"input": 7, "output": 3}
