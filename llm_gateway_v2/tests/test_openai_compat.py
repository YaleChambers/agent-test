from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.errors import GatewayError
from app.main import app


client = TestClient(app)


def test_chat_completions_returns_openai_response():
    # 测试普通请求返回 OpenAI Chat Completions 格式。
    result = SimpleNamespace(content="你好", model="deepseek-chat")
    with patch("app.api.routes.call_llm", new=AsyncMock(return_value=result)):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "general-primary",
                "messages": [{"role": "user", "content": "你好"}],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "general-primary"
    assert body["choices"][0]["message"]["content"] == "你好"


def test_chat_completions_rejects_streaming():
    # 测试暂不支持流式 Chat Completions。
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "general-primary",
            "messages": [{"role": "user", "content": "你好"}],
            "stream": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "streaming_not_supported"


def test_chat_completions_converts_gateway_error():
    # 测试 GatewayError 会转换为 OpenAI 错误格式。
    error = GatewayError("unknown_model", "Unknown model", status_code=400)
    with patch("app.api.routes.call_llm", new=AsyncMock(side_effect=error)):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "unknown-model",
                "messages": [{"role": "user", "content": "你好"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_model"
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_chat_completions_converts_unknown_error():
    # 测试未知异常会转换为 500 internal_error。
    with patch(
        "app.api.routes.call_llm",
        new=AsyncMock(side_effect=RuntimeError("unexpected")),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "general-primary",
                "messages": [{"role": "user", "content": "你好"}],
            },
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
