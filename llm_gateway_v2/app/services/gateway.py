import asyncio
import json
import logging
import os
import random
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
from ..schemas import (
    CallTrace,
    LLMRequest,
    LLMResponse,
    Message,
    RejectedCandidate,
    RouteDecision,
    Usage,
)
from .router import get_candidate_models, get_route_decision, is_retryable
from .prompts import render_prompt
from .upstream import UpstreamResult, call_upstream
from .usage import record_trace


logger = logging.getLogger(__name__)
_sleep = asyncio.sleep
MAX_DELAY_SECONDS = 30.0


def set_sleep_fn(fn) -> None:
    global _sleep
    _sleep = fn


def _is_retryable_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    return is_retryable(error) or status_code == 429 or status_code in range(500, 600)


def _calculate_backoff(attempt: int) -> float:
    delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
    delay *= random.uniform(0.5, 1.5)
    return min(delay, MAX_DELAY_SECONDS)


class StructuredOutputError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


async def call_llm(request: LLMRequest) -> LLMResponse:
    request_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)
    start_time = time.perf_counter()
    attempts = 0

    candidates = get_candidate_models(request.model)
    # 路由决策：不改变路由行为，仅记录决策信息供内部结果与 Trace 使用
    route_decision: RouteDecision = get_route_decision(request.model)

    def save_trace(
        status: Literal["success", "failed"],
        actual_model: str | None,
        usage: Usage | None = None,
        ttft_ms: float | None = None,
        cost_usd: float | None = None,
        error_code: str | None = None,
    ) -> None:
        record_trace(
            CallTrace(
                request_id=request_id,
                timestamp=timestamp,
                requested_model=request.model,
                actual_model=actual_model,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                cached_tokens=usage.cached_tokens if usage else None,
                reasoning_tokens=usage.reasoning_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                latency_ms=round((time.perf_counter() - start_time) * 1000),
                ttft_ms=ttft_ms,
                cost_usd=cost_usd,
                # route 以 JSON 可序列化形式写入 Trace
                route=route_decision.model_dump(mode="json"),
                attempts=attempts,
                status=status,
                error_code=error_code,
            )
        )

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
        candidate_tried = False
        for attempt in range(MAX_RETRIES + 1):
            if not breaker.is_available():
                break

            candidate_tried = True
            all_candidates_skipped = False
            attempts += 1
            try:
                result = validate_structured_output(
                    await call_upstream(upstream_request, model_config)
                )
                breaker.record_success()

                # 选中该候选模型
                route_decision.selected = model_name
                usage = result.response.usage

                # 按单价计算成本：input_tokens * input_price + output_tokens * output_price
                # 单价单位：美元 / token
                cost_usd: float | None = None
                if usage is not None:
                    cost_usd = (
                        usage.input_tokens * model_config.input_price
                        + usage.output_tokens * model_config.output_price
                    )

                result.response.route = route_decision
                result.response.cost_usd = cost_usd

                save_trace(
                    "success",
                    result.response.model,
                    usage=usage,
                    ttft_ms=result.response.ttft_ms,
                    cost_usd=cost_usd,
                )
                return result.response
            except Exception as exc:
                breaker.record_failure()
                last_error = exc
                if isinstance(exc, StructuredOutputError):
                    save_trace("failed", None, error_code=exc.code)
                    raise GatewayError(exc.code, str(exc)) from exc
                if _is_retryable_error(exc) and attempt < MAX_RETRIES:
                    retry_attempt = attempt + 1
                    delay = _calculate_backoff(retry_attempt)
                    logger.warning(
                        "模型 %s 第 %d 次调用失败，将在 %.3f 秒后重试: %s",
                        model_name,
                        retry_attempt,
                        delay,
                        exc,
                    )
                    await _sleep(delay)
                    continue
                break

        # 该候选模型已耗尽重试，记入 rejected（含拒绝原因）
        if candidate_tried and last_error is not None:
            route_decision.rejected.append(
                RejectedCandidate(model=model_name, reason=str(last_error))
            )

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
