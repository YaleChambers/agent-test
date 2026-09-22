import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import ModelConfig
from app.schemas import LLMRequest, Message
from app.services.adapters.anthropic_messages import AnthropicMessagesAdapter


def _make_request() -> LLMRequest:
    return LLMRequest(
        model="claude-3-5-haiku-latest",
        messages=[
            Message(role="system", content="You are a helpful assistant"),
            Message(role="user", content="Hello"),
        ],
    )


def _make_config() -> ModelConfig:
    return ModelConfig(
        model="claude-3-5-haiku-latest",
        base_url="https://api.anthropic.com",
        protocol="anthropic_messages",
    )


def _patch_client(mock_client_cls, response_data: dict):
    """配置 AsyncClient mock：__aenter__ 返回实例，post 返回假响应。"""
    fake_post = AsyncMock()
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = response_data
    fake_post.return_value = fake_response

    instance = mock_client_cls.return_value
    instance.__aenter__.return_value = instance
    instance.post = fake_post
    return instance


def _run_chat(adapter, request, config):
    with patch(
        "app.services.adapters.anthropic_messages.httpx.AsyncClient"
    ) as mock_client_cls, patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "test-key"}
    ):
        _patch_client(mock_client_cls, {"content": [{"type": "text", "text": "hi"}], "usage": {}})
        return asyncio.run(adapter.chat(request, config)), mock_client_cls.return_value.post


def test_request_url_and_headers():
    request = _make_request()
    config = _make_config()
    adapter = AnthropicMessagesAdapter()

    _, fake_post = _run_chat(adapter, request, config)

    url, kwargs = fake_post.call_args
    assert url[0] == "https://api.anthropic.com/v1/messages"
    headers = kwargs["headers"]
    assert headers["x-api-key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"


def test_request_body_has_max_tokens_and_system_split():
    request = _make_request()
    config = _make_config()
    adapter = AnthropicMessagesAdapter()

    _, fake_post = _run_chat(adapter, request, config)

    _, kwargs = fake_post.call_args
    body = kwargs["json"]
    assert body["max_tokens"] == 1024
    # system 被抽到 system 字段
    assert body["system"] == "You are a helpful assistant"
    # system 不在 messages 里
    assert all(m["role"] != "system" for m in body["messages"])
    assert body["messages"] == [{"role": "user", "content": "Hello"}]


def test_text_content_is_concatenated():
    request = _make_request()
    config = _make_config()
    adapter = AnthropicMessagesAdapter()

    with patch(
        "app.services.adapters.anthropic_messages.httpx.AsyncClient"
    ) as mock_client_cls, patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "test-key"}
    ):
        _patch_client(
            mock_client_cls,
            {
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": " World"},
                    {"type": "text", "text": " Goodbye"},
                ],
                "usage": {},
            },
        )
        result = asyncio.run(adapter.chat(request, config))

    assert result.response.content == "Hello World Goodbye"


def test_usage_extraction():
    request = _make_request()
    config = _make_config()
    adapter = AnthropicMessagesAdapter()

    with patch(
        "app.services.adapters.anthropic_messages.httpx.AsyncClient"
    ) as mock_client_cls, patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "test-key"}
    ):
        _patch_client(
            mock_client_cls,
            {
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 12, "output_tokens": 34},
            },
        )
        result = asyncio.run(adapter.chat(request, config))

    assert result.response.usage.input_tokens == 12
    assert result.response.usage.output_tokens == 34
    assert result.response.usage.total_tokens == 46