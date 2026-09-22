"""适配器层共享类型定义。"""

from dataclasses import dataclass

from ...schemas import LLMResponse


@dataclass(frozen=True)
class UpstreamResult:
    response: LLMResponse