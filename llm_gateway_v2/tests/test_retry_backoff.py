import random
from types import SimpleNamespace

import pytest

from app.schemas import LLMRequest
from app.services import gateway
from app.services.upstream import UpstreamResult


class AlwaysAvailableBreaker:
    def is_available(self) -> bool:
        return True

    def record_success(self) -> None:
        pass

    def record_failure(self) -> None:
        pass


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture
def retry_context(monkeypatch):
    sleeps = []
    calls = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def fake_call_upstream(request, model_config):
        calls.append(model_config.model)
        raise TimeoutError("temporary failure")

    monkeypatch.setattr(gateway, "set_sleep_fn", gateway.set_sleep_fn)
    gateway.set_sleep_fn(fake_sleep)
    monkeypatch.setattr(gateway, "get_breaker", lambda key: AlwaysAvailableBreaker())
    monkeypatch.setattr(gateway, "MAX_RETRIES", 1)
    monkeypatch.setattr(gateway, "RETRY_DELAY_SECONDS", 0.1)
    monkeypatch.setattr(gateway, "call_upstream", fake_call_upstream)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    yield sleeps, calls
    gateway.set_sleep_fn(gateway.asyncio.sleep)


def make_request() -> LLMRequest:
    return LLMRequest(
        model="general-primary",
        messages=[{"role": "user", "content": "test"}],
    )


@pytest.mark.asyncio
async def test_retry_count_matches_max_attempts(retry_context):
    # 测试每个模型按配置最多执行首次调用加一次重试。
    sleeps, calls = retry_context

    with pytest.raises(Exception):
        await gateway.call_llm(make_request())

    assert len(calls) == gateway.MAX_RETRIES + 1
    assert len(sleeps) == gateway.MAX_RETRIES


@pytest.mark.asyncio
async def test_exponential_backoff_with_jitter(retry_context, monkeypatch):
    # 测试指数退避和 jitter 的等待时间范围。
    sleeps, _ = retry_context
    monkeypatch.setattr(gateway, "MAX_RETRIES", 3)
    random.seed(1)

    with pytest.raises(Exception):
        await gateway.call_llm(make_request())

    assert len(sleeps) == 3
    assert 0.05 <= sleeps[0] <= 0.15
    assert 0.10 <= sleeps[1] <= 0.30
    assert 0.20 <= sleeps[2] <= 0.60


@pytest.mark.asyncio
async def test_backoff_is_capped(retry_context, monkeypatch):
    # 测试退避时间超过上限后会被 max_delay_seconds 封顶。
    sleeps, _ = retry_context
    monkeypatch.setattr(gateway, "MAX_RETRIES", 3)
    monkeypatch.setattr(gateway, "MAX_DELAY_SECONDS", 0.25)

    with pytest.raises(Exception):
        await gateway.call_llm(make_request())

    assert len(sleeps) == 3
    assert all(delay <= 0.25 for delay in sleeps)
    assert sleeps[-1] == 0.25


@pytest.mark.asyncio
async def test_non_retryable_error_does_not_sleep(retry_context, monkeypatch):
    # 测试认证或参数类错误不会触发重试。
    sleeps, calls = retry_context

    async def fail_once(request, model_config):
        calls.append(model_config.model)
        raise ValueError("invalid parameter")

    monkeypatch.setattr(gateway, "call_upstream", fail_once)

    with pytest.raises(Exception):
        await gateway.call_llm(make_request())

    assert len(calls) == 1
    assert sleeps == []


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError("timeout"), StatusError(429), StatusError(503)])
async def test_retryable_errors_trigger_retry(retry_context, monkeypatch, error):
    # 测试超时、429 和 5xx 错误都会触发重试。
    sleeps, calls = retry_context

    async def fail_twice(request, model_config):
        calls.append(model_config.model)
        raise error

    monkeypatch.setattr(gateway, "call_upstream", fail_twice)

    with pytest.raises(Exception):
        await gateway.call_llm(make_request())

    assert len(calls) == 2
    assert len(sleeps) == 1
