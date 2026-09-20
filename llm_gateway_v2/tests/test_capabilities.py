import pytest

from app.core.capabilities import CapabilityRegistry, load_registry_from_yaml


def test_load_example_yaml_no_error():
    # 加载 gateway.example.yaml 不报错（general 为 candidates 结构会被跳过）。
    registry = load_registry_from_yaml("gateway.example.yaml")

    assert registry is not None


def test_general_primary_supports_structured_output():
    registry = load_registry_from_yaml("gateway.example.yaml")

    assert registry.supports("general-primary", "structured_output")


def test_general_backup_does_not_support_structured_output():
    registry = load_registry_from_yaml("gateway.example.yaml")

    assert not registry.supports("general-backup", "structured_output")


def test_filter_candidates_by_structured_output():
    registry = load_registry_from_yaml("gateway.example.yaml")

    filtered = registry.filter_candidates(
        ["general-primary", "general-backup"],
        {"structured_output"},
    )

    assert filtered == ["general-primary"]


def test_unknown_model_returns_empty_capabilities():
    # 未知模型或未注册模型，能力集合为空。
    registry = CapabilityRegistry({"general-primary": {"streaming"}})

    assert registry.get_capabilities("unknown-model") == set()
    assert not registry.supports("unknown-model", "streaming")


def test_model_without_capabilities_defaults_to_empty(tmp_path):
    # 没有 capabilities 字段的普通模型，默认所有能力为 False 并告警。
    config_file = tmp_path / "gateway.yaml"
    config_file.write_text(
        "models:\n"
        "  no-cap:\n"
        "    provider: deepseek\n"
        "    model: deepseek-x\n",
        encoding="utf-8",
    )

    with pytest.warns(UserWarning):
        registry = load_registry_from_yaml(str(config_file))

    assert registry.get_capabilities("no-cap") == set()
    assert not registry.supports("no-cap", "streaming")
    assert not registry.supports("no-cap", "structured_output")
