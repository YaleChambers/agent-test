from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class PromptSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    variables: dict[str, str] = {}


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[Message] = Field(min_length=1)
    response_schema: dict | None = None
    prompt: PromptSelection | None = None


class Usage(BaseModel):
    """真实 token 用量，从上游响应提取，不写死 0。"""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int
    output_tokens: int
    total_tokens: int
    # 上游返回 prompt_tokens_details.cached_tokens 时填充，否则 None
    cached_tokens: int | None = None
    # 上游返回 completion_tokens_details.reasoning_tokens 时填充，否则 None
    reasoning_tokens: int | None = None


class RejectedCandidate(BaseModel):
    """路由中被拒绝（调用失败）的候选模型及原因。"""

    model_config = ConfigDict(extra="forbid")

    model: str
    reason: str


class RouteDecision(BaseModel):
    """路由决策：逻辑模型、选中模型、候选列表、被拒绝列表、策略。"""

    model_config = ConfigDict(extra="forbid")

    logical_model: str
    selected: str | None
    candidates: list[str]
    rejected: list[RejectedCandidate]
    policy: str


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    model: str
    parsed: dict | None = None
    usage: Usage | None = None
    # 非流式：发出请求到收到完整响应的耗时（近似 ttft）
    # 流式：发出请求到收到第一个有业务意义 delta 的耗时
    ttft_ms: float | None = None
    # 成本，单位：美元（USD）
    cost_usd: float | None = None
    route: RouteDecision | None = None


class CallTrace(BaseModel):
    request_id: str
    timestamp: datetime
    requested_model: str
    actual_model: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int
    ttft_ms: float | None = None
    cost_usd: float | None = None
    # route 以 JSON 字符串形式存储在 SQLite，反序列化后为 dict
    route: dict | None = None
    attempts: int
    status: Literal["success", "failed"]
    error_code: str | None
