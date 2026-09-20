from pathlib import Path

from ..config import (
    MODELS_WITH_CANDIDATES,
    ModelConfig,
    RETRYABLE_ERRORS,
    config,
    get_candidates,
)
from ..core.capabilities import CapabilityRegistry, load_registry_from_yaml
from ..schemas import RejectedCandidate, RouteDecision


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


def _get_policy(requested_model: str) -> str:
    # 从 YAML 顶层 routing.policy 读取策略；没有 routing 段时默认 "priority"
    return config.get("routing", {}).get("policy", "priority")


def get_route_decision(requested_model: str) -> RouteDecision:
    """构造初始路由决策（selected/rejected 由 gateway 在调用过程中填充）。

    不改变原有路由行为，仅用于把决策信息写入内部结果与 Trace。
    """
    candidates = get_candidate_models(requested_model)
    return RouteDecision(
        logical_model=requested_model,
        selected=None,
        candidates=[name for name, _ in candidates],
        rejected=[],
        policy=_get_policy(requested_model),
    )


class CapabilityRouter:
    """按能力过滤候选，再按 policy 选择模型。"""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def route(
        self,
        logical_model: str,
        candidates: list[str],
        required_capabilities: set[str],
        policy: str,
    ) -> RouteDecision:
        # 1. 先用 registry.filter_candidates 按请求的 required_capabilities 过滤候选
        remaining = self._registry.filter_candidates(candidates, required_capabilities)

        # 2. 被过滤掉的候选写进 rejected，reason 格式 "missing_capability:<能力名>"
        rejected: list[RejectedCandidate] = []
        for alias in candidates:
            if alias in remaining:
                continue
            for capability in sorted(required_capabilities):
                if not self._registry.supports(alias, capability):
                    rejected.append(
                        RejectedCandidate(
                            model=alias,
                            reason=f"missing_capability:{capability}",
                        )
                    )

        # 3. 剩下的候选按 policy 选择
        selected = self._select(remaining, policy)

        return RouteDecision(
            logical_model=logical_model,
            selected=selected,
            candidates=list(candidates),
            rejected=rejected,
            policy=policy,
        )

    def _select(self, candidates: list[str], policy: str) -> str | None:
        # 全被过滤时 selected = None
        if not candidates:
            return None
        if policy == "weighted_round_robin":
            return self._weighted_round_robin(candidates)
        # priority 及默认：取第一个
        return candidates[0]

    def _weighted_round_robin(self, candidates: list[str]) -> str:
        # 按 routing.weights 加权展开候选，用轮询索引取下一个
        weights = config.get("routing", {}).get("weights", {})
        expanded: list[str] = []
        for alias in candidates:
            weight = int(weights.get(alias, 1))
            expanded.extend([alias] * weight)

        index = getattr(self, "_rr_index", 0)
        self._rr_index = index + 1
        return expanded[index % len(expanded)]


# 组装默认 Router：从 gateway.yaml 加载 CapabilityRegistry 传入
_gateway_config_path = Path(__file__).parent.parent.parent / "gateway.yaml"
capability_router = CapabilityRouter(load_registry_from_yaml(_gateway_config_path))
