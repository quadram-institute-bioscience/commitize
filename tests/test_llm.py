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
