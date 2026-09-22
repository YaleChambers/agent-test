"""OpenAI 兼容协议适配器。

非流式逻辑由 app/services/upstream.py 的 call_upstream 原样搬入；
流式输出为 SSE 字节流（适配 BaseAdapter.stream 签名）。
"""

import json
import os
import time
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from ...config import ModelConfig
from ...core.errors import map_upstream_error
from ...schemas import LLMRequest, LLMResponse, Usage
from .base import BaseAdapter
from .types import UpstreamResult


class OpenAICompatibleAdapter(BaseAdapter):
    async def chat(
        self,
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

            # 非流式 ttft：从发出上游请求到收到完整响应的时间，作为近似 ttft
            start = time.perf_counter()
            completion = await client.chat.completions.create(**request_kwargs)
            ttft_ms = (time.perf_counter() - start) * 1000

            content = completion.choices[0].message.content or ""

            # 从上游响应提取真实 token 用量，不写死 0
            usage_obj = completion.usage
            input_tokens = (
                getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0
            )
            output_tokens = (
                getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0
            )
            total_tokens = (
                getattr(usage_obj, "total_tokens", input_tokens + output_tokens)
                if usage_obj
                else input_tokens + output_tokens
            )

            cached_tokens: int | None = None
            reasoning_tokens: int | None = None
            if usage_obj is not None:
                prompt_details = getattr(usage_obj, "prompt_tokens_details", None)
                if prompt_details is not None:
                    cached_tokens = getattr(prompt_details, "cached_tokens", None)
                completion_details = getattr(
                    usage_obj, "completion_tokens_details", None
                )
                if completion_details is not None:
                    reasoning_tokens = getattr(
                        completion_details, "reasoning_tokens", None
                    )

            usage = Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
                reasoning_tokens=reasoning_tokens,
            )

            return UpstreamResult(
                response=LLMResponse(
                    content=content,
                    model=model_config.model,
                    usage=usage,
                    ttft_ms=ttft_ms,
                ),
            )
        finally:
            await client.close()

    async def stream(
        self,
        request: LLMRequest,
        model_config: ModelConfig,
    ) -> AsyncIterator[bytes]:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=model_config.base_url,
            max_retries=0,
        )
        stream = None
        try:
            stream = await client.chat.completions.create(
                model=model_config.model,
                messages=[message.model_dump() for message in request.messages],
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                delta = (
                    chunk.choices[0].delta.content if chunk.choices else None
                )
                if delta:
                    chunk_bytes = (
                        f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                    ).encode("utf-8")
                    yield chunk_bytes
        finally:
            if stream is not None:
                await stream.close()
            await client.close()

        yield b"data: [DONE]\n\n"

    def translate_error(self, exc: Exception) -> tuple[str, int]:
        return map_upstream_error(exc)