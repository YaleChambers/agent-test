import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from ..core.auth import verify_token
from ..core.errors import GatewayError
from ..core.rate_limit import rate_limit
from ..schemas import CallTrace, LLMRequest, LLMResponse, Message
from ..schemas_openai import (
    ChatCompletion,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    CompletionUsage,
    OpenAIErrorResponse,
)
from ..services.gateway import call_llm
from ..services.streaming import stream_llm
from ..services.usage import get_traces


router = APIRouter()


def _openai_error_response(
    message: str,
    code: str,
    status_code: int,
) -> JSONResponse:
    error = OpenAIErrorResponse(
        error={
            "message": message,
            "type": "invalid_request_error",
            "code": code,
        }
    )
    return JSONResponse(status_code=status_code, content=error.model_dump())


def _to_internal_request(request: ChatCompletionRequest) -> LLMRequest:
    messages = []
    for message in request.messages:
        content: Any = message.content
        if isinstance(content, list):
            content = "".join(
                part.text for part in content if getattr(part, "type", None) == "text"
            )
        role = "system" if message.role == "developer" else message.role
        messages.append(Message(role=role, content=content))

    response_schema = None
    if request.response_format is not None:
        response_format = request.response_format.model_dump()
        if response_format.get("type") == "json_schema":
            response_schema = response_format["json_schema"].get("schema")

    return LLMRequest(
        model=request.model,
        messages=messages,
        response_schema=response_schema,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/llm", response_model=LLMResponse)
async def llm_endpoint(
    request: LLMRequest,
    _: None = Depends(verify_token),
    _rl: None = Depends(rate_limit),
) -> LLMResponse:
    return await call_llm(request)


@router.post("/v1/llm/stream")
async def stream_endpoint(
    request: LLMRequest,
    http_request: Request,
    _: None = Depends(verify_token),
    _rl: None = Depends(rate_limit),
) -> StreamingResponse:
	return await stream_llm(request, http_request)


@router.post("/v1/chat/completions", response_model=None)
async def openai_chat_completions(
    request: ChatCompletionRequest,
) -> ChatCompletion | JSONResponse:
    if request.stream is True:
        return _openai_error_response(
            "Streaming responses are not supported",
            "streaming_not_supported",
            400,
        )

    try:
        result = await call_llm(_to_internal_request(request))
        # 内部 Usage 使用 input_tokens/output_tokens/total_tokens 字段
        usage = getattr(result, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "input_tokens", 0)
            completion_tokens = getattr(usage, "output_tokens", 0)
            total_tokens = getattr(
                usage,
                "total_tokens",
                prompt_tokens + completion_tokens,
            )
        else:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
        return ChatCompletion(
            id=getattr(result, "trace_id", str(uuid4())),
            object="chat.completion",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=result.content,
                    ),
                    finish_reason=(
                        "length"
                        if getattr(result, "finish_reason", "stop") == "length"
                        else "stop"
                    ),
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            ),
        )
    except GatewayError as exc:
        return _openai_error_response(
            exc.message,
            exc.code,
            getattr(exc, "http_status", exc.status_code),
        )
    except Exception as exc:
        return _openai_error_response(str(exc), "internal_error", 500)


@router.get("/v1/traces", response_model=list[CallTrace])
async def traces_endpoint(
    limit: int = 20,
    _: None = Depends(verify_token),
) -> list[CallTrace]:
    return get_traces(limit)
