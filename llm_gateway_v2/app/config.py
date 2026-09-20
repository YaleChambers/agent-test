import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import yaml

from openai import (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)

@dataclass(frozen=True)
class ModelConfig:
    model: str
    base_url: str
    # 单价，单位：美元 / token（USD per token）。
    # 例如 0.00000014 表示 $0.14 / 1M tokens。
    input_price: float = 0.0
    output_price: float = 0.0


CandidateModel: TypeAlias = tuple[str, ModelConfig]


RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    TimeoutError,
    ConnectionError,
)
MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 0.1


def _replace_env_vars(value):
    if isinstance(value, str):
        return re.sub(
            r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
            lambda match: os.getenv(match.group(1), match.group(0)),
            value,
        )
    if isinstance(value, dict):
        return {key: _replace_env_vars(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_env_vars(item) for item in value]
    return value


config_path = Path(__file__).parent.parent / "gateway.yaml"
if not config_path.exists():
    raise FileNotFoundError("请复制 gateway.example.yaml 为 gateway.yaml")

with config_path.open(encoding="utf-8") as config_file:
    config = _replace_env_vars(yaml.safe_load(config_file) or {})

providers = config.get("providers", {})
models = config.get("models", {})
MODEL_CONFIGS: dict[str, ModelConfig] = {}
MODELS_WITH_CANDIDATES: dict[str, list[CandidateModel]] = {}

for name, model_config in models.items():
    if "candidates" in model_config:
        candidates: list[CandidateModel] = []
        for index, candidate in enumerate(model_config["candidates"]):
            candidate_config = ModelConfig(
                model=candidate["model"],
                base_url=providers[candidate["provider"]]["base_url"],
                input_price=float(candidate.get("input_price", 0.0)),
                output_price=float(candidate.get("output_price", 0.0)),
            )
            candidate_name = f"{name}__candidate_{index}"
            candidates.append((candidate_name, candidate_config))
            MODEL_CONFIGS[candidate_name] = candidate_config
        MODELS_WITH_CANDIDATES[name] = candidates
        continue

    MODEL_CONFIGS[name] = ModelConfig(
        model=model_config["model"],
        base_url=providers[model_config["provider"]]["base_url"],
        input_price=float(model_config.get("input_price", 0.0)),
        output_price=float(model_config.get("output_price", 0.0)),
    )


def get_candidates(alias: str) -> list[ModelConfig]:
    if alias in MODELS_WITH_CANDIDATES:
        return [config for _, config in MODELS_WITH_CANDIDATES[alias]]
    if alias in MODEL_CONFIGS:
        return [MODEL_CONFIGS[alias]]
    return []
