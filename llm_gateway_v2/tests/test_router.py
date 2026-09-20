import pytest
import yaml

from app.core.capabilities import load_registry_from_yaml
from app.services.router import (
    CapabilityRouter,
    get_candidate_models,
    get_route_decision,
    is_retryable,
)


def test_timeout_error_is_retryable():
    # 测试 TimeoutError 属于可重试错误。
    assert is_retryable(TimeoutError()) is True


def test_connection_error_is_retryable():
    # 测试 ConnectionError 属于可重试错误。
    assert is_retryable(ConnectionError()) is True


def test_value_error_is_not_retryable():
    # 测试 ValueError 不属于可重试错误。
    assert is_retryable(ValueError("test")) is False


def test_primary_model_returns_one_candidate():
    # 测试普通模型别名返回一个候选模型。
    candidates = get_candidate_models("general-primary")

    assert len(candidates) == 1


def test_general_model_returns_two_candidates():
    # 测试多候选模型别名返回两个候选模型。
    candidates = get_candidate_models("general")

    assert len(candidates) == 2


def test_unknown_model_returns_no_candidates():
    # 测试未知模型别名返回空列表。
    candidates = get_candidate_models("unknown-model")

    assert candidates == []


def test_route_decision_policy_from_example_yaml():
    # 加载 gateway.example.yaml 后，routing.policy 应为 "priority"。
    with open("gateway.example.yaml", encoding="utf-8") as config_file:
        example_config = yaml.safe_load(config_file)

    assert example_config["routing"]["policy"] == "priority"

    # RouteDecision.policy 从 YAML 的 routing.policy 读取，不应是硬编码。
    decision = get_route_decision("general-primary")
    assert decision.policy == "priority"


@pytest.fixture
def capability_registry():
    return load_registry_from_yaml("gateway.example.yaml")


def test_capability_router_filters_by_structured_output(capability_registry):
    # required_capabilities={"structured_output"} 时，general-backup 被拒绝，
    # 选中 general-primary，rejected 里有 missing_capability:structured_output。
    router = CapabilityRouter(capability_registry)
    decision = router.route(
        logical_model="general",
        candidates=["general-primary", "general-backup"],
        required_capabilities={"structured_output"},
        policy="priority",
    )

    assert decision.selected == "general-primary"
    assert (
        "general-backup",
        "missing_capability:structured_output",
    ) in [(r.model, r.reason) for r in decision.rejected]


def test_capability_router_priority_takes_first_when_all_support(
    capability_registry,
):
    # required_capabilities={"streaming"} 时两个候选都支持，按 priority 取第一个。
    router = CapabilityRouter(capability_registry)
    decision = router.route(
        logical_model="general",
        candidates=["general-primary", "general-backup"],
        required_capabilities={"streaming"},
        policy="priority",
    )

    assert decision.selected == "general-primary"
    assert decision.rejected == []


def test_capability_router_all_filtered_selected_none(capability_registry):
    # 所有候选都不满足时 selected = None，rejected 保留全部原因。
    router = CapabilityRouter(capability_registry)
    decision = router.route(
        logical_model="general",
        candidates=["general-primary", "general-backup"],
        required_capabilities={"video"},
        policy="priority",
    )

    assert decision.selected is None
    assert len(decision.rejected) == 2
    assert all(
        r.reason == "missing_capability:video" for r in decision.rejected
    )
