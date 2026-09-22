from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

UNKNOWN_MODEL = "unknown_model"
GATEWAY_MISCONFIGURED = "gateway_misconfigured"
UPSTREAM_ERROR = "upstream_error"
MODEL_UNAVAILABLE = "model_unavailable"
INVALID_JSON = "invalid_json"
SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
UNKNOWN_PROMPT_TEMPLATE = "unknown_prompt_template"
MISSING_PROMPT_VARIABLE = "missing_prompt_variable"

UNAUTHORIZED = "unauthorized"
RATE_LIMITED = "rate_limited"
UPSTREAM_TIMEOUT = "upstream_timeout"
UPSTREAM_RATE_LIMITED = "upstream_rate_limited"
UPSTREAM_CONNECTION_ERROR = "upstream_connection_error"
UPSTREAM_AUTH_ERROR = "upstream_auth_error"
UPSTREAM_BAD_REQUEST = "upstream_bad_request"
STRUCTURED_OUTPUT_VALIDATION_FAILED = "structured_output_validation_failed"
CONCURRENCY_TIMEOUT = "concurrency_timeout"


class GatewayError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def map_upstream_error(exc: Exception) -> tuple[str, int]:
    """把上游异常映射为 (error_code, http_status)。

    注意：openai 的 APITimeoutError 通常是 APIConnectionError 的子类，
    因此超时必须先于连接错误判断。
    """
    if isinstance(exc, (APITimeoutError, TimeoutError)):
        return UPSTREAM_TIMEOUT, 504
    if isinstance(exc, (APIConnectionError, ConnectionError)):
        return UPSTREAM_CONNECTION_ERROR, 502
    if isinstance(exc, RateLimitError):
        return UPSTREAM_RATE_LIMITED, 429
    if isinstance(exc, AuthenticationError):
        return UPSTREAM_AUTH_ERROR, 502

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        if 400 <= status_code < 500:
            return UPSTREAM_BAD_REQUEST, 400
        if status_code >= 500:
            return UPSTREAM_ERROR, 502
    return UPSTREAM_ERROR, 502
