import json
import os
from collections.abc import AsyncIterator

from fastapi import Request
from openai import AsyncOpenAI
from starlette.responses import StreamingResponse

from ..core.errors import GATEWAY_MISCONFIGURED, UNKNOWN_MODEL, GatewayError
from ..config import MODEL_CONFIGS
from ..schemas import LLMRequest


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

    async def event_stream() -> AsyncIterator[str]:
        stream = None
        try:
            stream = await client.chat.completions.create(
                model=config.model,
                messages=[
                    message.model_dump() for message in llm_request.messages
                ],
                stream=True,
            )
            async for chunk in stream:
                if await request.is_disconnected():
                    print("[stream] 客户端断开，停止上游请求")
                    return
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if stream is not None:
                await stream.close()
            await client.close()

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
