# LLM Gateway V2

一个基于 FastAPI 的 LLM Gateway，负责统一处理模型路由、鉴权、限流、重试、fallback、熔断、流式响应、Structured Output 和调用记录。

## 项目结构

```text
llm_gateway_v2/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── core/
│   │   ├── auth.py
│   │   ├── capabilities.py
│   │   ├── circuit_breaker.py
│   │   ├── errors.py
│   │   └── rate_limit.py
│   └── services/
│       ├── __init__.py
│       ├── gateway.py
│       ├── prompts.py
│       ├── router.py
│       ├── streaming.py
│       ├── upstream.py
│       └── usage.py
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_capabilities.py
│   ├── test_openai_compat.py
│   ├── test_retry_backoff.py
│   ├── test_router.py
│   ├── test_schemas.py
│   └── test_trace_fields.py
├── gateway.example.yaml
├── gateway.yaml
├── pytest.ini
├── requirements.txt
├── test_cancel.py
├── test_check_openai.py
├── test_client.py
├── test_prompt.py
├── test_stream.py
└── test_structured.py
```

## 文件职责

### 应用入口和配置

- `app/main.py`：创建 FastAPI 应用，挂载路由，并注册全局 `GatewayError` 异常处理器。
- `app/config.py`：读取 `gateway.yaml`，解析供应商、普通模型和多候选模型配置，包括每个模型的单价（input_price/output_price）和顶层 routing 配置；同时定义重试相关配置。
- `app/schemas.py`：定义请求、响应、消息、Prompt 选择、Token 用量（Usage）、路由决策（RouteDecision）和 Trace 的 Pydantic 模型，并负责基础请求校验；Trace 包含 ttft_ms、cost_usd、route 等字段。

### API 路由

- `app/api/routes.py`：定义 HTTP 路由和依赖注入。
  - `GET /health`
  - `POST /v1/llm`
  - `POST /v1/llm/stream`
  - `GET /v1/traces`

### 核心能力

- `app/core/auth.py`：Bearer Token 鉴权。密钥从 `GATEWAY_API_KEY` 读取，未配置时默认使用 `test-key`。
- `app/core/rate_limit.py`：基于内存令牌桶的限流器。每个 Token 独立限流。
- `app/core/circuit_breaker.py`：三态熔断器，支持 `closed`、`open` 和 `half_open`。
- `app/core/capabilities.py`：模型能力注册表，从 YAML 的 models 段读取每个模型的 capabilities（streaming / structured_output / tool_calling），支持按能力过滤候选。
- `app/core/errors.py`：定义统一的 `GatewayError` 异常和错误码常量。

### 服务层

- `app/services/gateway.py`：非流式请求编排，包括 Prompt 渲染、候选模型遍历、重试、fallback、熔断器和 Structured Output 校验，并计算 cost_usd 与记录路由决策。
- `app/services/upstream.py`：调用 DeepSeek 上游 API，负责单次非流式模型请求、真实 Token 用量提取（含 cached / reasoning tokens）和 ttft_ms 计时。
- `app/services/router.py`：判断错误是否可重试、获取候选模型列表；`CapabilityRouter` 按请求的能力要求过滤候选（被过滤的候选写入 rejected 并标注 `missing_capability`），再按 `routing.policy` 选择模型（priority 取第一个 / weighted_round_robin 加权轮询）。
- `app/services/streaming.py`：处理 DeepSeek 流式响应，转换为 SSE；记录首个业务 delta 的 ttft_ms，流式结束后落 Trace。
- `app/services/prompts.py`：管理版本化 Prompt 模板，并使用变量渲染 system Prompt。
- `app/services/usage.py`：使用 SQLite 保存和查询调用 Trace，数据库文件为项目根目录的 `traces.db`；Trace 含 input/output/cached/reasoning/total tokens、ttft_ms、cost_usd 和 route（JSON 序列化）。

### 配置和依赖

- `gateway.example.yaml`：团队共享的配置示例，包含供应商、模型单价、capabilities、retry 和 routing 配置。
- `gateway.yaml`：本地实际配置，包含供应商和模型路由；不应提交到 Git。
- `requirements.txt`：运行和测试所需的 Python 依赖。
- `pytest.ini`：pytest 配置，指定异步模式和测试目录。

### 测试文件

- `tests/test_api.py`：使用 FastAPI `TestClient` 测试健康检查、鉴权、请求校验和未知模型错误，不调用真实模型。
- `tests/test_router.py`：测试可重试错误判断、候选模型路由、路由策略读取，以及 CapabilityRouter 的能力过滤与选中逻辑。
- `tests/test_schemas.py`：测试 Pydantic 模型字段约束和非法输入。
- `tests/test_capabilities.py`：测试 CapabilityRegistry 从 YAML 加载能力、supports 和 filter_candidates 过滤。
- `tests/test_trace_fields.py`：测试非流式请求后 Trace 里的 ttft_ms、usage tokens、cost_usd 和 route 字段。
- `tests/test_retry_backoff.py`：测试重试次数和指数退避（含抖动和上限）。
- `tests/test_openai_compat.py`：测试 OpenAI 兼容接口的响应结构、错误转换和 usage 映射。
- `test_client.py`：发送一次非流式 HTTP 测试请求。
- `test_stream.py`：逐行读取流式 SSE 响应。
- `test_prompt.py`：测试 Prompt 模板请求。
- `test_structured.py`：测试 Structured Output 请求。
- `test_check_openai.py`：手动验证 OpenAI 兼容接口的 usage 字段。
- `test_cancel.py`：收到前几个流式 chunk 后主动断开，用于验证上游取消。

## 启动

先确认项目根目录存在本地配置文件 `gateway.yaml`，并设置 API Key：

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
export GATEWAY_API_KEY="test-key"
```

启动服务：

```bash
cd ~/code/llm_gateway_v2
uvicorn app.main:app --reload --port 8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/health
```

## 测试

使用项目虚拟环境运行完整测试：

```bash
python3 -m pytest -v
```

项目测试不会调用真实模型。根目录下的 `test_*.py` 是手动请求脚本，需要 Gateway 服务运行后再执行。

## 认证请求示例

受保护接口需要携带：

```http
Authorization: Bearer test-key
```

例如：

```bash
curl -X POST http://127.0.0.1:8001/v1/llm \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{"model":"general-primary","messages":[{"role":"user","content":"你好"}]}'
```
