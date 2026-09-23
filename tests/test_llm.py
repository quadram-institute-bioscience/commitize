import json

import httpx
import respx

from commitize.llm import LLMAuthError, LLMRequestError, OpenAICompatibleClient


@respx.mock
def test_chat_success_sends_expected_request():
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "feat: add thing"}}]}
        )
    )

    client = OpenAICompatibleClient(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-test",
        model="openai/gpt-4o-mini",
        extra_headers={"X-Title": "commitize"},
    )
    result = client.chat(system="sys", user="usr")

    assert result == "feat: add thing"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer sk-test"
    assert request.headers["X-Title"] == "commitize"
    body = json.loads(request.content)
    assert body["model"] == "openai/gpt-4o-mini"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "usr"}


@respx.mock
def test_chat_missing_api_key_raises_without_request():
    client = OpenAICompatibleClient(base_url="https://x/api", api_key=None, model="m")
    try:
        client.chat(system="sys", user="usr")
        assert False, "expected LLMAuthError"
    except LLMAuthError:
        pass


@respx.mock
def test_chat_401_raises_auth_error():
    respx.post("https://x/api/chat/completions").mock(return_value=httpx.Response(401))
    client = OpenAICompatibleClient(base_url="https://x/api", api_key="bad", model="m")
    try:
        client.chat(system="sys", user="usr")
        assert False, "expected LLMAuthError"
    except LLMAuthError:
        pass


@respx.mock
def test_chat_server_error_raises_request_error():
    respx.post("https://x/api/chat/completions").mock(return_value=httpx.Response(500, text="boom"))
    client = OpenAICompatibleClient(base_url="https://x/api", api_key="k", model="m")
    try:
        client.chat(system="sys", user="usr")
        assert False, "expected LLMRequestError"
    except LLMRequestError:
        pass


@respx.mock
def test_usage_and_cost_accumulate_across_calls():
    respx.post("https://x/api/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json={
                "choices": [{"message": {"content": "a"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.0002},
            }),
            httpx.Response(200, json={
                "choices": [{"message": {"content": "b"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 5, "cost": 0.0001},
            }),
        ]
    )
    client = OpenAICompatibleClient(base_url="https://x/api", api_key="k", model="m")

    client.chat(system="s", user="u")
    client.chat(system="s", user="u")

    assert client.usage.requests == 2
    assert client.usage.prompt_tokens == 150
    assert client.usage.completion_tokens == 15
    assert abs(client.usage.cost - 0.0003) < 1e-12


@respx.mock
def test_cost_is_none_when_provider_does_not_report_it():
    respx.post("https://x/api/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "a"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        })
    )
    client = OpenAICompatibleClient(base_url="https://x/api", api_key="k", model="m")

    client.chat(system="s", user="u")

    assert client.usage.requests == 1
    assert client.usage.cost is None
