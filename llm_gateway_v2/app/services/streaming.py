import json
import os
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request
from openai import AsyncOpenAI
from starlette.responses import StreamingResponse

from ..core.errors import GATEWAY_MISCONFIGURED, UNKNOWN_MODEL, GatewayError
from ..config import MODEL_CONFIGS
from ..schemas import CallTrace, LLMRequest, RouteDecision, Usage
from .router import get_route_decision
from .usage import record_trace


async def stream_llm(
    llm_request: LLMRequest,
    request: Request,
) -> StreamingResponse:
    config = MODEL_CONFIGS.get(llm_request.model)
    if config is None:
        raise GatewayError(UNKNOWN_MODEL, "Unknown model", status_code=400)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise GatewayError(
            GATEWAY_MISCONFIGURED,
            "DEEPSEEK_API_KEY is not configured",
            status_code=500,
        )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=config.base_url,
        max_retries=0,
    )

    request_id = str(uuid4())
    start_time = time.perf_counter()
    timestamp = datetime.now(timezone.utc)
    # 流式：单模型直连，selected 即自身，rejected 为空
    route_decision: RouteDecision = get_route_decision(llm_request.model)
    route_decision.selected = llm_request.model

    usage: Usage | None = None
    ttft_ms: float | None = None

    async def event_stream() -> AsyncIterator[str]:
        nonlocal usage, ttft_ms
        stream = None
        try:
            # 从发出上游请求开始计时
            stream = await client.chat.completions.create(
                model=config.model,
                messages=[
                    message.model_dump() for message in llm_request.messages
                ],
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                if await request.is_disconnected():
                    print("[stream] 客户端断开，停止上游请求")
                    return

                delta = (
                    chunk.choices[0].delta.content
                    if chunk.choices
                    else None
                )
                # 只把有业务意义的 delta 当作首 token，忽略连接建立/空内容事件
                if delta:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - start_time) * 1000
                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"

                # 流式 usage 通常在末尾 chunk 携带
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    input_tokens = getattr(chunk_usage, "prompt_tokens", 0)
                    output_tokens = getattr(chunk_usage, "completion_tokens", 0)
                    total_tokens = getattr(
                        chunk_usage, "total_tokens", input_tokens + output_tokens
                    )
                    cached_tokens = None
                    reasoning_tokens = None
                    prompt_details = getattr(
                        chunk_usage, "prompt_tokens_details", None
                    )
                    if prompt_details is not None:
                        cached_tokens = getattr(
                            prompt_details, "cached_tokens", None
                        )
                    completion_details = getattr(
                        chunk_usage, "completion_tokens_details", None
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
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if stream is not None:
                await stream.close()
            await client.close()

            # 流式结束后落 Trace
            cost_usd: float | None = None
            if usage is not None:
                cost_usd = (
                    usage.input_tokens * config.input_price
                    + usage.output_tokens * config.output_price
                )
            record_trace(
                CallTrace(
                    request_id=request_id,
                    timestamp=timestamp,
                    requested_model=llm_request.model,
                    actual_model=config.model,
                    input_tokens=usage.input_tokens if usage else 0,
                    output_tokens=usage.output_tokens if usage else 0,
                    cached_tokens=usage.cached_tokens if usage else None,
                    reasoning_tokens=usage.reasoning_tokens if usage else None,
                    total_tokens=usage.total_tokens if usage else None,
                    latency_ms=round((time.perf_counter() - start_time) * 1000),
                    ttft_ms=ttft_ms,
                    cost_usd=cost_usd,
                    route=route_decision.model_dump(mode="json"),
                    attempts=1,
                    status="success",
                    error_code=None,
                )
            )

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
