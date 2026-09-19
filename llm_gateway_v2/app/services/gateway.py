import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from jsonschema import ValidationError, validate

from app.core.circuit_breaker import get_breaker
from app.core.errors import GatewayError, MODEL_UNAVAILABLE

from ..core.errors import (
    GATEWAY_MISCONFIGURED,
    INVALID_JSON,
    MISSING_PROMPT_VARIABLE,
    SCHEMA_VALIDATION_FAILED,
    UNKNOWN_MODEL,
    UNKNOWN_PROMPT_TEMPLATE,
    UPSTREAM_ERROR,
)
from ..config import MAX_RETRIES, RETRY_DELAY_SECONDS
from ..schemas import CallTrace, LLMRequest, LLMResponse, Message
from .router import get_candidate_models, is_retryable
from .prompts import render_prompt
from .upstream import UpstreamResult, call_upstream
from .usage import record_trace


logger = logging.getLogger(__name__)


class StructuredOutputError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


async def call_llm(request: LLMRequest) -> LLMResponse:
    request_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)
    start_time = time.perf_counter()
    attempts = 0

    def save_trace(
        status: Literal["success", "failed"],
        actual_model: str | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_code: str | None = None,
    ) -> None:
        record_trace(
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

    candidates = get_candidate_models(request.model)
    if not candidates:
        save_trace("failed", None, error_code=UNKNOWN_MODEL)
        raise GatewayError(UNKNOWN_MODEL, "Unknown model", status_code=400)

    if not os.getenv("DEEPSEEK_API_KEY"):
        save_trace("failed", None, error_code=GATEWAY_MISCONFIGURED)
        raise GatewayError(
            GATEWAY_MISCONFIGURED,
            "DEEPSEEK_API_KEY is not configured",
            status_code=500,
        )

    upstream_request = request
    if request.prompt is not None:
        try:
            system_prompt = render_prompt(
                request.prompt.name,
                request.prompt.version,
                request.prompt.variables,
            )
        except ValueError as exc:
            error_message = str(exc)
            if error_message.startswith("unknown_prompt_template"):
                error_code = UNKNOWN_PROMPT_TEMPLATE
            elif error_message.startswith("missing_prompt_variable"):
                error_code = MISSING_PROMPT_VARIABLE
            else:
                raise
            save_trace("failed", None, error_code=error_code)
            raise GatewayError(error_code, error_message, status_code=400) from exc

        upstream_request = request.model_copy(
            update={
                "messages": [
                    Message(role="system", content=system_prompt),
                    *request.messages,
                ]
            }
        )

    last_error: Exception | None = None
    all_candidates_skipped = True

    def validate_structured_output(result: UpstreamResult) -> UpstreamResult:
        if request.response_schema is None:
            return result

        try:
            parsed = json.loads(result.response.content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(INVALID_JSON, str(exc)) from exc

        try:
            validate(instance=parsed, schema=request.response_schema)
        except ValidationError as exc:
            raise StructuredOutputError(SCHEMA_VALIDATION_FAILED, str(exc)) from exc

        if not isinstance(parsed, dict):
            raise StructuredOutputError(
				SCHEMA_VALIDATION_FAILED,
                "Structured output must be a JSON object",
            )
        result.response.parsed = parsed
        return result

    for index, (model_name, model_config) in enumerate(candidates):
        breaker = get_breaker(model_name)
        for attempt in range(MAX_RETRIES + 1):
            if not breaker.is_available():
                break

            all_candidates_skipped = False
            attempts += 1
            try:
                result = validate_structured_output(
                    await call_upstream(upstream_request, model_config)
                )
                breaker.record_success()
                save_trace(
                    "success",
                    result.response.model,
                    result.input_tokens,
                    result.output_tokens,
                )
                return result.response
            except Exception as exc:
                breaker.record_failure()
                last_error = exc
                if isinstance(exc, StructuredOutputError):
                    save_trace("failed", None, error_code=exc.code)
                    raise GatewayError(exc.code, str(exc)) from exc
                if is_retryable(exc) and attempt < MAX_RETRIES:
                    logger.warning(
                        "模型 %s 第 %d 次调用失败，将在 %.1f 秒后重试: %s",
                        model_name,
                        attempt + 1,
                        RETRY_DELAY_SECONDS,
                        exc,
                    )
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue
                break

        if index < len(candidates) - 1:
            next_model_name = candidates[index + 1][0]
            logger.warning(
                "模型 %s 调用失败，切换到候选模型 %s: %s",
                model_name,
                next_model_name,
                last_error,
            )

    if all_candidates_skipped:
        save_trace("failed", None, error_code=MODEL_UNAVAILABLE)
        raise GatewayError(
            MODEL_UNAVAILABLE,
            "All candidates are circuit-broken",
        )

    if request.model == "general-backup":
        save_trace("failed", None, error_code=UPSTREAM_ERROR)
        error_code = UPSTREAM_ERROR
    else:
        save_trace("failed", None, error_code=MODEL_UNAVAILABLE)
        error_code = MODEL_UNAVAILABLE
    raise GatewayError(error_code, str(last_error)) from last_error
