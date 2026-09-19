UNKNOWN_MODEL = "unknown_model"
GATEWAY_MISCONFIGURED = "gateway_misconfigured"
UPSTREAM_ERROR = "upstream_error"
MODEL_UNAVAILABLE = "model_unavailable"
INVALID_JSON = "invalid_json"
SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
UNKNOWN_PROMPT_TEMPLATE = "unknown_prompt_template"
MISSING_PROMPT_VARIABLE = "missing_prompt_variable"


class GatewayError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
