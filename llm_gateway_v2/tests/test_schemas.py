import pytest
from pydantic import ValidationError

from app.schemas import LLMRequest, LLMResponse, Message, PromptSelection


def test_valid_llm_request_succeeds():
    # 测试合法的 LLMRequest 可以成功创建。
    request = LLMRequest(
        model="general-primary",
        messages=[Message(role="user", content="你好")],
    )

    assert request.model == "general-primary"
    assert len(request.messages) == 1


def test_llm_request_without_model_raises_validation_error():
    # 测试缺少 model 的 LLMRequest 会校验失败。
    with pytest.raises(ValidationError):
        LLMRequest(messages=[Message(role="user", content="你好")])


def test_llm_request_with_empty_messages_raises_validation_error():
    # 测试 messages 为空的 LLMRequest 会校验失败。
    with pytest.raises(ValidationError):
        LLMRequest(model="general-primary", messages=[])


def test_message_with_invalid_role_raises_validation_error():
    # 测试不支持的消息角色会校验失败。
    with pytest.raises(ValidationError):
        Message(role="invalid", content="你好")


def test_message_with_extra_field_raises_validation_error():
    # 测试 Message 包含额外字段时会校验失败。
    with pytest.raises(ValidationError):
        Message(role="user", content="你好", foo="bar")


def test_prompt_selection_variables_default_to_empty_dict():
    # 测试 PromptSelection 的 variables 默认为空字典。
    prompt = PromptSelection(name="knowledge_decision", version="v1")

    assert prompt.variables == {}


def test_llm_response_parsed_defaults_to_none():
    # 测试 LLMResponse 的 parsed 默认为 None。
    response = LLMResponse(content="回答", model="deepseek-chat")

    assert response.parsed is None
