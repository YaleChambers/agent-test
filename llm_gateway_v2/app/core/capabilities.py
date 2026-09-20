"""模型能力注册表：从 gateway.yaml 的 models 段读取每个模型的能力。

capabilities 字段示例：
    general-primary:
      capabilities:
        streaming: true
        structured_output: true
        tool_calling: true
"""

import warnings
from pathlib import Path

import yaml


class CapabilityRegistry:
    """按模型别名管理能力集合。"""

    def __init__(
        self,
        capabilities_by_model: dict[str, set[str]] | None = None,
    ) -> None:
        # 内部映射：模型别名 -> 已启用能力集合
        self._capabilities_by_model: dict[str, set[str]] = capabilities_by_model or {}

    def get_capabilities(self, model_alias: str) -> set[str]:
        """返回模型已启用的能力集合；未知模型返回空集。"""
        return set(self._capabilities_by_model.get(model_alias, set()))

    def supports(self, model_alias: str, capability: str) -> bool:
        """判断模型是否支持指定能力。"""
        return capability in self.get_capabilities(model_alias)

    def filter_candidates(
        self,
        candidates: list[str],
        required: set[str],
    ) -> list[str]:
        """按 required 能力过滤候选，保持原顺序。"""
        return [
            alias
            for alias in candidates
            if required.issubset(self.get_capabilities(alias))
        ]


def load_registry_from_yaml(path: str | Path) -> CapabilityRegistry:
    """从 YAML 的 models 段加载能力注册表。

    - 模型带 capabilities 字段时，读入其中值为 true 的能力。
    - 模型没有 capabilities 字段且不是 candidates 结构时，默认所有能力为 False
      并发出告警。
    - candidates 结构（如 general：strategy + candidates）不参与能力注册，直接跳过，
      避免加载报错。
    """
    with open(path, encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)

    models = data.get("models", {})
    capabilities_by_model: dict[str, set[str]] = {}

    for alias, model_config in models.items():
        if not isinstance(model_config, dict):
            continue
        # candidates 结构（如 general）没有 capabilities，跳过
        if "candidates" in model_config:
            continue

        raw_capabilities = model_config.get("capabilities")
        if not isinstance(raw_capabilities, dict):
            warnings.warn(
                f"模型 {alias} 未配置 capabilities 字段，默认所有能力为 False",
                stacklevel=2,
            )
            capabilities_by_model[alias] = set()
            continue

        capabilities = {
            name
            for name, enabled in raw_capabilities.items()
            if isinstance(enabled, bool) and enabled
        }
        capabilities_by_model[alias] = capabilities

    return CapabilityRegistry(capabilities_by_model)
