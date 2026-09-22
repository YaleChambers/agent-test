"""OpenAI Responses API 适配器。

走 Responses API（/v1/responses）协议，与 Chat Completions (openai_compatible)
协议不同。使用 httpx 直接发 HTTP 请求，避免依赖 OpenAI SDK 对
responses 方法版本支持的不确定性。
"""

import json
import os
import time
from collections.abc import AsyncIterator

import httpx

from ...config import ModelConfig
from ...core.errors import map_upstream_error
from ...schemas import LLMRequest, LLMResponse, Usage
from .base import BaseAdapter
from .types import UpstreamResult


def _api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    return key


def _messages_to_input(messages: list) -> list[dict]:
    """把 LLMRequest.messages 拼成 Responses API 的 input 格式。"""
    return [
        {"role": m.role, "content": m.content}
        for m in messages
    ]


def _extract_text(output: list) -> str:
    parts: list[str] = []
    for item in output or []:
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    parts.append(content.get("text", "") or "")
    return "".join(parts)


def _extract_usage(data: dict) -> Usage:
    usage = data.get("usage") or {}
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    total_tokens = int(
        usage.get("total_tokens", input_tokens + output_tokens) or 0
    )

    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    input_details = usage.get("input_tokens_details") or {}
    if input_details.get("cached_tokens") is not None:
        cached_tokens = int(input_details["cached_tokens"])
    output_details = usage.get("output_tokens_details") or {}
    if output_details.get("reasoning_tokens") is not None:
        reasoning_tokens = int(output_details["reasoning_tokens"])

    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _responses_url(model_config: ModelConfig) -> str:
    base = model_config.base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/responses"
    return f"{base}/v1/responses"


class OpenAIResponsesAdapter(BaseAdapter):
    async def chat(
        self,
        request: LLMRequest,
        model_config: ModelConfig,
    ) -> UpstreamResult:
        headers = {
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        }
        input_messages: list[dict] = _messages_to_input(request.messages)
        if request.response_schema is not None:
            # 把 JSON Schema 拼成 system 提示，插到 messages 最前面，
            # 引导模型只返回符合 schema 的 JSON（与 openai_compatible 行为一致）
            schema_text = json.dumps(request.response_schema, ensure_ascii=False)
            schema_prompt = (
                "只返回一个合法 JSON 对象，必须严格符合下列 JSON Schema，"
                f"不要返回 Markdown 或额外文字：{schema_text}"
            )
            input_messages.insert(0, {"role": "system", "content": schema_prompt})

        body = {
            "model": model_config.model,
            "input": input_messages,
        }

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _responses_url(model_config), headers=headers, json=body
            )
            resp.raise_for_status()
            data = resp.json()
        ttft_ms = (time.perf_counter() - start) * 1000

        content = _extract_text(data.get("output") or [])
        usage = _extract_usage(data)

        return UpstreamResult(
            response=LLMResponse(
                content=content,
                model=model_config.model,
                usage=usage,
                ttft_ms=ttft_ms,
            ),
        )

    async def stream(
        self,
        request: LLMRequest,
        model_config: ModelConfig,
    ) -> AsyncIterator[bytes]:
        headers = {
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        }
        # 注：作业只要求非流式结构化输出。流式暂不注入 response_schema 提示，
        # 需要时可在输入前置一条与 chat 相同的 system 消息。
        body = {
            "model": model_config.model,
            "input": _messages_to_input(request.messages),
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", _responses_url(model_config), headers=headers, json=body
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "response.output_text.delta":
                        delta = event.get("delta", "")
                        if delta:
                            chunk = (
                                f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                            ).encode("utf-8")
                            yield chunk

        yield b"data: [DONE]\n\n"

    def translate_error(self, exc: Exception) -> tuple[str, int]:
        return map_upstream_error(exc)