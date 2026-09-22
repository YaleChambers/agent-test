"""Anthropic Messages API 适配器。

走 Anthropic Messages API（/v1/messages）协议。使用 httpx 直发，
鉴权用 x-api-key + anthropic-version 头，与 OpenAI 的 Bearer 不同。
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
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return key


def _split_messages(messages: list):
    """把 LLMRequest.messages 拆成 (system, anthropic_messages)。

    system 抽出单独返回；其余消息 role 仅保留 user/assistant。
    """
    system_parts: list[str] = []
    anthropic_messages: list[dict] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        else:
            role = m.role if m.role in ("user", "assistant") else "user"
            anthropic_messages.append({"role": role, "content": m.content})
    return ("\n".join(system_parts) or None), anthropic_messages


def _url(model_config: ModelConfig) -> str:
    base = model_config.base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def _headers() -> dict:
    return {
        "x-api-key": _api_key(),
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _body(model_config: ModelConfig, request: LLMRequest, streaming: bool) -> dict:
    system, anthropic_messages = _split_messages(request.messages)
    body: dict = {
        "model": model_config.model,
        "max_tokens": 1024,
        "messages": anthropic_messages,
    }
    if system:
        body["system"] = system
    if streaming:
        body["stream"] = True
    return body


def _extract_text(content: list) -> str:
    parts: list[str] = []
    for item in content or []:
        if item.get("type") == "text":
            parts.append(item.get("text", "") or "")
    return "".join(parts)


def _extract_usage(data: dict) -> Usage:
    usage = data.get("usage", {}) or {}
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)

    # Anthropic 计数口径：input 含 cache read 部分，total = input + output
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    input_details = usage.get("input_tokens_details") or {}
    if input_details.get("cache_read_input_tokens") is not None:
        cached_tokens = int(input_details["cache_read_input_tokens"])
    output_details = usage.get("output_tokens_details") or {}
    if output_details.get("thinking_tokens") is not None:
        reasoning_tokens = int(output_details["thinking_tokens"])

    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )


class AnthropicMessagesAdapter(BaseAdapter):
    async def chat(
        self,
        request: LLMRequest,
        model_config: ModelConfig,
    ) -> UpstreamResult:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _url(model_config),
                headers=_headers(),
                json=_body(model_config, request, streaming=False),
            )
            resp.raise_for_status()
            data = resp.json()
        ttft_ms = (time.perf_counter() - start) * 1000

        content = _extract_text(data.get("content") or [])
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                _url(model_config),
                headers=_headers(),
                json=_body(model_config, request, streaming=True),
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
                    # 只关心内容增量事件
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                chunk = (
                                    f"data: {json.dumps({'delta': text}, ensure_ascii=False)}\n\n"
                                ).encode("utf-8")
                                yield chunk

        yield b"data: [DONE]\n\n"

    def translate_error(self, exc: Exception) -> tuple[str, int]:
        return map_upstream_error(exc)