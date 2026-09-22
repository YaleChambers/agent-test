import pytest
from openai import APITimeoutError

from app.config import MAX_RETRIES
from app.core.errors import UPSTREAM_TIMEOUT, GatewayError
from app.schemas import LLMRequest
from app.services import gateway


class AlwaysAvailableBreaker:
    def is_available(self) -> bool:
        return True

    def record_success(self) -> None:
        pass

    def record_failure(self) -> None:
        pass


class FakeAdapter:
    def __init__(self, call_fn) -> None:
        self._call_fn = call_fn

    async def chat(self, request, model_config):
        return await self._call_fn(request, model_config)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch, tmp_path):
    # 避免污染真实 traces.db
    monkeypatch.setattr("app.services.usage.DATABASE_PATH", tmp_path / "traces.db")
    monkeypatch.setattr(gateway, "get_breaker", lambda key: AlwaysAvailableBreaker())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    yield


@pytest.mark.asyncio
async def test_max_retries_exhausts_upstream_and_sleep(monkeypatch):
    """MAX_RETRIES=3 → range(4)，call_upstream 最多调 4 次、_sleep 调 3 次。"""

    call_count = 0
    sleep_count = 0

    async def counting_call_upstream(request, model_config):
        nonlocal call_count
        call_count += 1
        raise APITimeoutError("upstream timed out")

    async def fake_sleep(_delay):
        nonlocal sleep_count
        sleep_count += 1

    monkeypatch.setattr(gateway, "get_adapter", lambda _mc: FakeAdapter(counting_call_upstream))
    monkeypatch.setattr(gateway, "_sleep", fake_sleep)

    request = LLMRequest(
        model="general-primary",
        messages=[{"role": "user", "content": "hi"}],
    )

    with pytest.raises(GatewayError) as excinfo:
        await gateway.call_llm(request)

    # call_upstream 被调用了 4 次（首次 + 3 次重试）
    assert call_count == MAX_RETRIES + 1
    assert call_count == 4

    # _sleep 被调用了 3 次
    assert sleep_count == MAX_RETRIES
    assert sleep_count == 3

    # 最终抛 GatewayError，按异常类型映射为 upstream_timeout / 504，原始错误保留在 __cause__
    error = excinfo.value
    assert isinstance(error, GatewayError)
    assert error.code == UPSTREAM_TIMEOUT
    assert error.status_code == 504
    assert isinstance(error.__cause__, APITimeoutError)