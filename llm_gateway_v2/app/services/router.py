from ..config import (
    MODELS_WITH_CANDIDATES,
    ModelConfig,
    RETRYABLE_ERRORS,
    get_candidates,
)


def is_retryable(error: Exception) -> bool:
    return isinstance(error, RETRYABLE_ERRORS)


def get_candidate_models(requested_model: str) -> list[tuple[str, ModelConfig]]:
    configs = get_candidates(requested_model)
    if not configs:
        return []

    if requested_model in MODELS_WITH_CANDIDATES:
        names = [
            name
            for name, _ in MODELS_WITH_CANDIDATES[requested_model]
        ]
    else:
        names = [requested_model] * len(configs)

    return list(zip(names, configs))
