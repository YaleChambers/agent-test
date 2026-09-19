from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    role: str
    content: str


class PromptSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    variables: dict[str, str] = {}


class LLMRequest(BaseModel):
    model: str
    messages: list[Message]
    response_schema: dict | None = None
    prompt: PromptSelection | None = None


class LLMResponse(BaseModel):
    content: str
    model: str
    parsed: dict | None = None


class CallTrace(BaseModel):
    request_id: str
    timestamp: datetime
    requested_model: str
    actual_model: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int
    status: Literal["success", "failed"]
    error_code: str | None
