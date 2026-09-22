import pytest

from app.config import ModelConfig
from app.core.errors import GatewayError
from app.services.adapters.base import BaseAdapter
from app.services.adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.adapters.openai_responses import OpenAIResponsesAdapter
from app.services.adapters.registry import get_adapter


def _make_config(
    model: str = "deepseek-chat", protocol: str = "openai_compatible"
) -> ModelConfig:
    return ModelConfig(
        model=model,
        base_url="https://api.deepseek.com",
        input_price=0.00000014,
        output_price=0.00000028,
        protocol=protocol,
    )


def test_get_adapter_returns_same_instance_for_same_config():
    config = _make_config()

    adapter_a = get_adapter(config)
    adapter_b = get_adapter(config)

    assert adapter_a is adapter_b


def test_get_adapter_returns_base_adapter_instance():
    config = _make_config()

    adapter = get_adapter(config)

    assert isinstance(adapter, BaseAdapter)


def test_get_adapter_returns_distinct_instances_for_different_configs():
    adapter_a = get_adapter(_make_config("deepseek-chat"))
    adapter_b = get_adapter(_make_config("deepseek-flash"))

    assert adapter_a is not adapter_b


def test_protocol_openai_responses_returns_responses_adapter():
    adapter = get_adapter(_make_config(protocol="openai_responses"))

    assert isinstance(adapter, OpenAIResponsesAdapter)


def test_protocol_openai_compatible_returns_compatible_adapter():
    adapter = get_adapter(_make_config(protocol="openai_compatible"))

    assert isinstance(adapter, OpenAICompatibleAdapter)


def test_missing_protocol_defaults_to_compatible_adapter():
    config = ModelConfig(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
    )

    adapter = get_adapter(config)

    assert isinstance(adapter, OpenAICompatibleAdapter)


def test_unknown_protocol_raises_gateway_error():
    config = _make_config(protocol="unknown_proto")

    with pytest.raises(GatewayError) as exc_info:
        get_adapter(config)

    assert exc_info.value.code == "unknown_protocol"