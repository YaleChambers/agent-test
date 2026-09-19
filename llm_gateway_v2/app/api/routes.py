from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from ..core.auth import verify_token
from ..core.rate_limit import rate_limit
from ..schemas import CallTrace, LLMRequest, LLMResponse
from ..services.gateway import call_llm
from ..services.streaming import stream_llm
from ..services.usage import get_traces


router = APIRouter()


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


@router.get("/v1/traces", response_model=list[CallTrace])
async def traces_endpoint(
    limit: int = 20,
    _: None = Depends(verify_token),
) -> list[CallTrace]:
    return get_traces(limit)
