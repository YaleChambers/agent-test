"""适配器注册表。

按模型配置的上游协议（ModelConfig.protocol）返回对应的适配器，
并用 dict 缓存实例，避免每次调用都新建适配器。
"""

from ...config import ModelConfig
from ...core.errors import GatewayError
from .anthropic_messages import AnthropicMessagesAdapter
from .base import BaseAdapter
from .openai_compatible import OpenAICompatibleAdapter
from .openai_responses import OpenAIResponsesAdapter

_REGISTRY: dict[ModelConfig, BaseAdapter] = {}

# 协议名 -> 适配器工厂
_ADAPTER_FACTORIES: dict[str, type[BaseAdapter]] = {
    "openai_compatible": OpenAICompatibleAdapter,
    "openai_responses": OpenAIResponsesAdapter,
    "anthropic_messages": AnthropicMessagesAdapter,
}


def _build_adapter(model_config: ModelConfig) -> BaseAdapter:
    protocol = model_config.protocol or "openai_compatible"
    factory = _ADAPTER_FACTORIES.get(protocol)
    if factory is None:
        raise GatewayError(
            "unknown_protocol",
            f"Unknown upstream protocol: {protocol}",
            status_code=500,
        )
    return factory()


def get_adapter(model_config: ModelConfig) -> BaseAdapter:
    """返回该模型配置对应适配器（同一 model_config 复用一个实例）。"""
    adapter = _REGISTRY.get(model_config)
    if adapter is None:
        adapter = _build_adapter(model_config)
        _REGISTRY[model_config] = adapter
    return adapter