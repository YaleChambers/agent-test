import pytest

from app.schemas import LLMRequest, LLMResponse, Usage
from app.services import gateway
from app.services.adapters.types import UpstreamResult
from app.services.usage import get_traces


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


@pytest.fixture
def isolated_trace_db(tmp_path, monkeypatch):
    # 使用临时数据库，避免污染 traces.db
    db_path = tmp_path / "traces.db"
    monkeypatch.setattr("app.services.usage.DATABASE_PATH", db_path)
    yield db_path


@pytest.fixture
def gateway_stubs(monkeypatch):
    monkeypatch.setattr(gateway, "get_breaker", lambda key: AlwaysAvailableBreaker())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    yield


def make_request(model: str = "general") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[{"role": "user", "content": "hi"}],
    )


@pytest.mark.asyncio
async def test_non_streaming_trace_has_positive_ttft(
    isolated_trace_db, gateway_stubs, monkeypatch
):
    # 非流式请求后，Trace 里的 ttft_ms 应为正数。
    success = UpstreamResult(
        response=LLMResponse(
            content="ok",
            model="deepseek-flash",
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
            ttft_ms=42.0,
        )
    )

    async def fake_call_upstream(request, model_config):
        if model_config.model == "deepseek-chat":
            raise ValueError("first candidate down")
        return success

    monkeypatch.setattr(gateway, "get_adapter", lambda _mc: FakeAdapter(fake_call_upstream))

    await gateway.call_llm(make_request("general"))

    traces = get_traces(limit=5)
    assert traces, "expected a trace to be recorded"
    trace = traces[0]

    assert trace.ttft_ms is not None
    assert trace.ttft_ms > 0


@pytest.mark.asyncio
async def test_non_streaming_trace_usage_tokens_not_zero(
    isolated_trace_db, gateway_stubs, monkeypatch
):
    # usage 的 input/output token 不应为 0（不写死 0）。
    success = UpstreamResult(
        response=LLMResponse(
            content="ok",
            model="deepseek-flash",
            usage=Usage(input_tokens=123, output_tokens=45, total_tokens=168),
            ttft_ms=10.0,
        )
    )

    async def fake_call_upstream(request, model_config):
        if model_config.model == "deepseek-chat":
            raise ValueError("first candidate down")
        return success

    monkeypatch.setattr(gateway, "get_adapter", lambda _mc: FakeAdapter(fake_call_upstream))

    await gateway.call_llm(make_request("general"))

    trace = get_traces(limit=5)[0]

    assert trace.input_tokens == 123
    assert trace.output_tokens == 45
    assert trace.input_tokens != 0
    assert trace.output_tokens != 0
    assert trace.total_tokens == 168


@pytest.mark.asyncio
async def test_non_streaming_trace_cost_usd_calculated(
    isolated_trace_db, gateway_stubs, monkeypatch
):
    # cost_usd 按 input_tokens * input_price + output_tokens * output_price 计算。
    # general 的候选 1 是 deepseek-flash，单价见 gateway.yaml：
    #   input_price=0.00000007, output_price=0.00000014
    input_tokens = 100
    output_tokens = 50
    expected_cost = input_tokens * 0.00000007 + output_tokens * 0.00000014

    success = UpstreamResult(
        response=LLMResponse(
            content="ok",
            model="deepseek-flash",
            usage=Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            ttft_ms=10.0,
        )
    )

    async def fake_call_upstream(request, model_config):
        if model_config.model == "deepseek-chat":
            raise ValueError("first candidate down")
        return success

    monkeypatch.setattr(gateway, "get_adapter", lambda _mc: FakeAdapter(fake_call_upstream))

    result = await gateway.call_llm(make_request("general"))

    trace = get_traces(limit=5)[0]

    assert result.cost_usd == pytest.approx(expected_cost)
    assert trace.cost_usd == pytest.approx(expected_cost)


@pytest.mark.asyncio
async def test_non_streaming_trace_route_has_selected_and_rejected(
    isolated_trace_db, gateway_stubs, monkeypatch
):
    # route 里应包含 selected 和 rejected（含拒绝原因）。
    success = UpstreamResult(
        response=LLMResponse(
            content="ok",
            model="deepseek-flash",
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
            ttft_ms=10.0,
        )
    )

    async def fake_call_upstream(request, model_config):
        if model_config.model == "deepseek-chat":
            raise ValueError("first candidate down")
        return success

    monkeypatch.setattr(gateway, "get_adapter", lambda _mc: FakeAdapter(fake_call_upstream))

    result = await gateway.call_llm(make_request("general"))

    trace = get_traces(limit=5)[0]
    route = trace.route

    assert route is not None
    assert route["logical_model"] == "general"
    assert route["selected"] == "general__candidate_1"
    assert route["candidates"] == [
        "general__candidate_0",
        "general__candidate_1",
    ]
    assert route["policy"] == "priority"

    assert len(route["rejected"]) == 1
    rejected = route["rejected"][0]
    assert rejected["model"] == "general__candidate_0"
    assert "first candidate down" in rejected["reason"]

    # 内部结果上也应携带 route
    assert result.route is not None
    assert result.route.selected == "general__candidate_1"
