import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import TokenBucket, rate_limiter
from app.main import app
from app.schemas import LLMResponse


client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer test-key"}

MODEL_A = "model-a"
MODEL_B = "model-b"


async def _fake_call_llm(request):
    """不发真实上游调用，直接返回成功。"""
    return LLMResponse(content="ok", model=request.model)


@pytest.fixture(autouse=True)
def _isolate_rate_limit(monkeypatch):
    """每测一个干净的单例状态 + mock 掉上游调用，避免测试间耦合。"""
    monkeypatch.setattr(rate_limiter, "buckets", {})
    monkeypatch.setattr("app.api.routes.call_llm", _fake_call_llm)
    yield


def _set_bucket(model: str, capacity: int, refill_rate: float = 0.0) -> None:
    """预设该模型的独立小桶，refill_rate 默认 0 便于精确控制容量。"""
    rate_limiter.buckets[model] = TokenBucket(capacity=capacity, refill_rate=refill_rate)


def _llm_request(model: str) -> dict:
    return {"model": model, "messages": [{"role": "user", "content": "hi"}]}


def test_same_model_over_capacity_returns_429():
    """同一模型连续请求超过容量(capacity=3)后返回 429。"""
    _set_bucket(MODEL_A, capacity=3)

    # 前 3 次通过
    for _ in range(3):
        response = client.post("/v1/llm", json=_llm_request(MODEL_A), headers=AUTH_HEADERS)
        assert response.status_code == 200

    # 第 4 次被限流
    response = client.post("/v1/llm", json=_llm_request(MODEL_A), headers=AUTH_HEADERS)
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "rate_limited"


def test_different_models_are_independent():
    """模型 A 打满后，模型 B 仍返回 True（互不影响）。"""
    _set_bucket(MODEL_A, capacity=1)

    # 模型 A 第一次通过即打满
    first = client.post("/v1/llm", json=_llm_request(MODEL_A), headers=AUTH_HEADERS)
    assert first.status_code == 200
    # 模型 A 第二次被限流
    second = client.post("/v1/llm", json=_llm_request(MODEL_A), headers=AUTH_HEADERS)
    assert second.status_code == 429

    # 模型 B 不受影响，仍可正常请求
    response = client.post("/v1/llm", json=_llm_request(MODEL_B), headers=AUTH_HEADERS)
    assert response.status_code == 200


def test_shared_quota_within_same_model():
    """同一模型连续请求共享同一桶配额（按模型分桶，不看请求身份）。

    鉴权层只认单一 test-key，架构上限流 key 即 model，
    因此桶由 model 持有并跨请求共享：打满后下一次调用立即 429。
    """
    _set_bucket(MODEL_A, capacity=1)

    # 第一次通过打满桶
    first = client.post("/v1/llm", json=_llm_request(MODEL_A), headers=AUTH_HEADERS)
    assert first.status_code == 200

    # 第二次同一个模型（相同 request 身份）立即被限流 → 配额属于 model 且共享
    second = client.post("/v1/llm", json=_llm_request(MODEL_A), headers=AUTH_HEADERS)
    assert second.status_code == 429