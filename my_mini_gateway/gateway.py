import os
import json
import asyncio
import logging
import time
from dataclasses import dataclass
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from openai import (
	APIConnectionError,
	APITimeoutError,
	AsyncOpenAI,
	RateLimitError,
)
from pydantic import BaseModel
from starlette.responses import StreamingResponse


logger = logging.getLogger(__name__)
RETRYABLE_ERRORS = (
	APIConnectionError,
	APITimeoutError,
	RateLimitError,
	TimeoutError,
	ConnectionError,
)
MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 0.1


class LLMRequest(BaseModel):
	model: str
	messages: list[dict[str, Any]]


class LLMResponse(BaseModel):
	content: str
	model: str


@dataclass(frozen=True)
class ModelCallResult:
	response: LLMResponse
	input_tokens: int
	output_tokens: int


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


CALL_TRACES: list[CallTrace] = []


@dataclass(frozen=True)
class ModelConfig:
	model: str
	base_url: str


MODEL_CONFIGS = {
	"general-primary": ModelConfig(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
    ),
    "general-backup": ModelConfig(
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
    ),
}

app = FastAPI(title="Minimal LLM Gateway")


@app.get("/health")
async def health() -> dict[str, str]:
	return {"status": "ok"}


@app.post("/v1/llm", response_model=LLMResponse)
async def call_llm(request: LLMRequest) -> LLMResponse:
	request_id = str(uuid4())
	timestamp = datetime.now(timezone.utc)
	start_time = time.perf_counter()
	attempts = 0

	def record_trace(
		status: Literal["success", "failed"],
		actual_model: str | None,
		input_tokens: int = 0,
		output_tokens: int = 0,
		error_code: str | None = None,
	) -> None:
		CALL_TRACES.append(
			CallTrace(
				request_id=request_id,
				timestamp=timestamp,
				requested_model=request.model,
				actual_model=actual_model,
				input_tokens=input_tokens,
				output_tokens=output_tokens,
				latency_ms=round((time.perf_counter() - start_time) * 1000),
				attempts=attempts,
				status=status,
				error_code=error_code,
			)
		)

	config = MODEL_CONFIGS.get(request.model)
	if config is None:
		record_trace("failed", None, error_code="unknown_model")
		raise HTTPException(
			status_code=400,
			detail={"code": "unknown_model", "message": "Unknown model"},
		)

	api_key = os.getenv("DEEPSEEK_API_KEY")
	if not api_key:
		record_trace("failed", None, error_code="gateway_misconfigured")
		raise HTTPException(
			status_code=500,
			detail={
				"code": "gateway_misconfigured",
				"message": "DEEPSEEK_API_KEY is not configured",
			},
		)

	async def call_model(model_name: str, model_config: ModelConfig) -> ModelCallResult:
		nonlocal attempts
		client = AsyncOpenAI(
			api_key=api_key,
			base_url=model_config.base_url,
			max_retries=0,
		)
		try:
			for attempt in range(MAX_RETRIES + 1):
				try:
					attempts += 1
					completion = await client.chat.completions.create(
						model=model_config.model,
						messages=request.messages,
					)
					content = completion.choices[0].message.content or ""
					usage = completion.usage
					return ModelCallResult(
						response=LLMResponse(content=content, model=model_config.model),
						input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
						output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
					)
				except RETRYABLE_ERRORS as exc:
					if attempt >= MAX_RETRIES:
						raise
					logger.warning(
						"模型 %s 第 %d 次调用失败，将在 %.1f 秒后重试: %s",
						model_name,
						attempt + 1,
						RETRY_DELAY_SECONDS,
						exc,
					)
					await asyncio.sleep(RETRY_DELAY_SECONDS)
				except Exception:
					raise
		finally:
			await client.close()

	try:
		result = await call_model(request.model, config)
		record_trace(
			"success",
			result.response.model,
			result.input_tokens,
			result.output_tokens,
		)
		return result.response
	except Exception as primary_exc:
		if request.model == "general-backup":
			record_trace("failed", None, error_code="upstream_error")
			raise HTTPException(
				status_code=502,
				detail={"code": "upstream_error", "message": str(primary_exc)},
			) from primary_exc

		logger.warning(
			"主模型 %s 调用失败，切换到备用模型 %s: %s",
			request.model,
			"general-backup",
			primary_exc,
		)

		try:
			result = await call_model("general-backup", MODEL_CONFIGS["general-backup"])
			record_trace(
				"success",
				result.response.model,
				result.input_tokens,
				result.output_tokens,
			)
			return result.response
		except Exception as backup_exc:
			record_trace("failed", None, error_code="model_unavailable")
			raise HTTPException(
				status_code=502,
				detail={"code": "model_unavailable", "message": str(backup_exc)},
			) from backup_exc


@app.get("/v1/traces", response_model=list[CallTrace])
async def get_traces(limit: int = 20) -> list[CallTrace]:
	return list(reversed(CALL_TRACES))[:limit]


@app.post("/v1/llm/stream")
async def stream_llm(request: LLMRequest) -> StreamingResponse:
	config = MODEL_CONFIGS.get(request.model)
	if config is None:
		raise HTTPException(
			status_code=400,
			detail={"code": "unknown_model", "message": "Unknown model"},
		)

	api_key = os.getenv("DEEPSEEK_API_KEY")
	if not api_key:
		raise HTTPException(
			status_code=500,
			detail={
				"code": "gateway_misconfigured",
				"message": "DEEPSEEK_API_KEY is not configured",
			},
		)

	client = AsyncOpenAI(
		api_key=api_key,
		base_url=config.base_url,
		max_retries=0,
	)

	async def event_stream() -> AsyncIterator[str]:
		try:
			stream = await client.chat.completions.create(
				model=config.model,
				messages=request.messages,
				stream=True,
			)
			async for chunk in stream:
				delta = chunk.choices[0].delta.content if chunk.choices else None
				if delta:
					yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
		except Exception as exc:
			yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
		finally:
			await client.close()

		yield "data: [DONE]\n\n"

	return StreamingResponse(event_stream(), media_type="text/event-stream")
