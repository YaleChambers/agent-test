"""上游适配器抽象。

通过适配器模式支持多种上游协议：每个具体适配器封装一种上游的
请求/响应格式，网关通过统一接口调用，避免上层耦合具体协议。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ...config import ModelConfig
from ...schemas import LLMRequest
from .types import UpstreamResult


class BaseAdapter(ABC):
    """上游协议适配器抽象基类。"""

    @abstractmethod
    async def chat(
        self,
        request: LLMRequest,
        model_config: ModelConfig,
    ) -> UpstreamResult:
        """非流式调用上游，返回统一的 UpstreamResult。"""

    @abstractmethod
    async def stream(
        self,
        request: LLMRequest,
        model_config: ModelConfig,
    ) -> AsyncIterator[bytes]:
        """流式调用上游，返回 SSE 字节块迭代器。"""

    @abstractmethod
    def translate_error(self, exc: Exception) -> tuple[str, int]:
        """把上游异常翻译为 (error_code, http_status)。"""