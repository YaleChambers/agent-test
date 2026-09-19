import os
import json
from dataclasses import dataclass

from openai import AsyncOpenAI

from ..config import ModelConfig
from ..schemas import LLMRequest, LLMResponse


@dataclass(frozen=True)
class UpstreamResult:
    response: LLMResponse
    input_tokens: int
    output_tokens: int


async def call_upstream(
    request: LLMRequest,
    model_config: ModelConfig,
) -> UpstreamResult:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=model_config.base_url,
        max_retries=0,
    )
    try:
        messages = [message.model_dump() for message in request.messages]
        request_kwargs = {
            "model": model_config.model,
            "messages": messages,
        }
        if request.response_schema is not None:
            schema_text = json.dumps(request.response_schema, ensure_ascii=False)
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "只返回一个合法 JSON 对象，必须严格符合下列 JSON Schema，"
                        f"不要返回 Markdown 或额外文字：{schema_text}"
                    ),
                },
            )
            request_kwargs["response_format"] = {"type": "json_object"}
        completion = await client.chat.completions.create(
            **request_kwargs,
        )
        content = completion.choices[0].message.content or ""
        usage = completion.usage
        return UpstreamResult(
            response=LLMResponse(content=content, model=model_config.model),
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        )
    finally:
        await client.close()
