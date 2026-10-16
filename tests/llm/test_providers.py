
"""Tests for the GraphMem LLM provider abstraction."""

import os

import httpx
import pytest

from graphmem.llm.base import LLMResponse, Message
from graphmem.llm.providers import MockProvider, OpenAICompatibleProvider


def test_mock_provider_returns_scripted_responses_in_order():
    provider = MockProvider(["first answer", "second answer"])
    messages = [Message(role="user", content="Hello")]

    first = provider.generate(messages)
    second = provider.generate(
        [Message(role="user", content="Another question")]
    )

    assert first.text == "first answer"
    assert second.text == "second answer"
    assert len(provider.prompts) == 2
    assert provider.prompts[0] == messages
    assert provider.prompts[1][0].content == "Another question"


def test_mock_provider_records_tools():
    provider = MockProvider(["tool-aware answer"])
    messages = [Message(role="user", content="Find a function")]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "Search source code",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    result = provider.generate(messages, tools=tools)

    assert result.text == "tool-aware answer"
    assert provider.calls[0]["tools"] == tools


def test_mock_provider_raises_when_script_is_exhausted():
    provider = MockProvider(["only answer"])

    provider.generate([Message(role="user", content="First")])

    with pytest.raises(RuntimeError, match="script exhausted"):
        provider.generate([Message(role="user", content="Second")])


def test_llm_response_has_default_usage():
    response = LLMResponse(text="hello")

    assert response.tool_calls == []
    assert response.usage == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    assert response.latency_ms == 0.0


def test_openai_compatible_provider_parses_response(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Found two functions.",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_code",
                                        "arguments": '{"query": "foo"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 7,
                },
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1/",
        model="test-model",
        api_key="test-key",
    )

    result = provider.generate(
        [Message(role="user", content="Find foo")],
        tools=[{"type": "function", "function": {"name": "search_code"}}],
    )

    assert captured["url"] == (
        "http://localhost:11434/v1/chat/completions"
    )
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["messages"] == [
        {"role": "user", "content": "Find foo"}
    ]
    assert "tools" in captured["json"]
    assert captured["headers"]["Authorization"] == "Bearer test-key"

    assert result.text == "Found two functions."
    assert result.usage == {
        "prompt_tokens": 12,
        "completion_tokens": 7,
    }
    assert result.tool_calls[0]["id"] == "call_1"
    assert result.latency_ms >= 0


def test_openai_compatible_provider_defaults_missing_usage_to_zero(
    monkeypatch,
):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [{"message": {"content": "Hello"}}],
            }

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        model="test-model",
    )

    result = provider.generate([Message(role="user", content="Hi")])

    assert result.usage == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    assert result.text == "Hello"


def test_provider_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("GRAPHMEM_LLM_BASE_URL", "http://example.test/v1")
    monkeypatch.setenv("GRAPHMEM_LLM_MODEL", "env-model")
    monkeypatch.setenv("GRAPHMEM_LLM_API_KEY", "env-key")

    provider = OpenAICompatibleProvider()

    assert provider.base_url == "http://example.test/v1"
    assert provider.model == "env-model"
    assert provider.api_key == "env-key"


def test_provider_retries_transient_server_failure(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self.body = body or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request(
                    "POST", "http://localhost:11434/v1/chat/completions"
                )
                response = httpx.Response(
                    self.status_code, request=request
                )
                raise httpx.HTTPStatusError(
                    "request failed",
                    request=request,
                    response=response,
                )

        def json(self):
            return self.body

    responses = iter(
        [
            FakeResponse(503),
            FakeResponse(
                200,
                {"choices": [{"message": {"content": "Recovered"}}]},
            ),
        ]
    )
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("graphmem.llm.providers.time.sleep", lambda _: None)

    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        model="test-model",
    )

    result = provider.generate([Message(role="user", content="Hello")])

    assert result.text == "Recovered"
    assert len(calls) == 2


@pytest.mark.skipif(
    os.getenv("GRAPHMEM_LLM_INTEGRATION") != "1",
    reason="Set GRAPHMEM_LLM_INTEGRATION=1 to test a live LLM endpoint",
)
def test_live_openai_compatible_endpoint():
    provider = OpenAICompatibleProvider()
    result = provider.generate(
        [
            Message(
                role="user",
                content="Reply with exactly the word GraphMem.",
            )
        ]
    )

    assert result.text.strip()
    assert result.latency_ms >= 0
    assert "prompt_tokens" in result.usage
    assert "completion_tokens" in result.usage
