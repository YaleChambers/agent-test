# LLM Gateway V2

一个基于 FastAPI 的 LLM Gateway。它统一封装多种上游 LLM 协议（OpenAI Chat Completions、OpenAI Responses、Anthropic Messages），对外提供一套**OpenAI 兼容接口**，并内置鉴权、按模型独立限流、重试/退避、fallback、熔断、能力路由、Structured Output、流式响应、成本估算和 Trace 落库。

## 支持的协议

通过适配器模式支持多种上游协议，在 `gateway.yaml` 的每个模型上用 `protocol` 字段指定；`app/services/adapters/registry.py` 按该字段分发，未知协议抛 `unknown_protocol` 错误。

| protocol             | 适配器                     | 上游端点                                                      |
| -------------------- | -------------------------- | ------------------------------------------------------------- |
| `openai_compatible`  | `OpenAICompatibleAdapter`  | `{base_url}/chat/completions`                                 |
| `openai_responses`   | `OpenAIResponsesAdapter`   | `{base_url}/v1/responses`                                     |
| `anthropic_messages` | `AnthropicMessagesAdapter` | `{base_url}/v1/messages`（`x-api-key` + `anthropic-version`） |

三个适配器都实现 `BaseAdapter` 的三个方法：`chat`（非流式）、`stream`（流式）、`translate_error`（异常码映射）。

## 安装依赖

```bash
pip install -r requirements.txt
```

依赖清单：`fastapi`、`uvicorn`、`pydantic`、`openai`、`httpx`、`jsonschema`、`pytest`、`pytest-asyncio`。

## 环境变量

| 变量                | 是否必须               | 说明                                    |
| ------------------- | ---------------------- | --------------------------------------- |
| `GATEWAY_API_KEY`   | 否                     | 服务鉴权 token，未配置时默认 `test-key` |
| `DEEPSEEK_API_KEY`  | 是（使用 DeepSeek 时） | OpenAI 兼容 / Responses 适配器所用密钥  |
| `ANTHROPIC_API_KEY` | 否（可选）             | Anthropic Messages 适配器所用密钥       |

可通过 shell 导出，或复制 `gateway.example.yaml` 中 provider 对应的 `api_key_env` 提示来设置对应变量。配置读取使用 `os.getenv`（未内置 dotenv 加载；若希望用 `.env` 文件，可自行创建 `env.example` 并 source）。

```bash
export GATEWAY_API_KEY="test-key"
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
export ANTHROPIC_API_KEY="你的 Anthropic API Key"
```

## 配置

配置文件为项目根目录的 `gateway.yaml`（本地实际配置，建议加入 `.gitignore`），团队共享示例见 `gateway.example.yaml`。结构如下：

```yaml
providers:
  deepseek:
    base_url: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
  anthropic:
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY

models:
  general-primary:
    provider: deepseek # 对应 providers 下的名称
    model: deepseek-chat
    protocol: openai_responses # openai_compatible / openai_responses / anthropic_messages
    input_price: 0.00000014 # 单价，单位 美元/token
    output_price: 0.00000028
    capabilities: # 能力注册表，用于按能力过滤候选
      streaming: true
      structured_output: true
      tool_calling: true
  general-backup:
    provider: anthropic
    model: claude-3-5-haiku-latest
    protocol: anthropic_messages
    input_price: 0.00000007
    output_price: 0.00000014
    capabilities:
      streaming: true
      structured_output: false
      tool_calling: false
  general: # 多候选模型：strategy + candidates
    strategy: priority
    candidates:
      - provider: deepseek
        model: deepseek-chat
      - provider: anthropic
        model: claude-3-5-haiku-latest

retry:
  max_retries: 3
  base_delay_seconds: 0.1
  max_delay_seconds: 5
  jitter: true

routing:
  policy: priority # priority / weighted_round_robin
  fallback_order:
    - general-primary
    - general-backup
  weights:
    general-primary: 80
    general-backup: 20
```

说明：

- `providers`：上游供应商的 `base_url` 与密钥环境变量名。
- `models`：每个模型的别名、供应商、协议、单价、capabilities；`candidates` 形式用于多候选模型。
- `retry`：重试次数、基础退避延迟、最大延迟与是否开启抖动（无此段时使用默认值）。
- `routing`：顶层路由策略（`policy`）、fallback 顺序、加权轮询权重；`CapabilityRouter` 先按请求的 `required_capabilities` 过滤候选（被过滤者写入 `route.rejected`，原因 `missing_capability:<能力名>`），再按策略选模型。

## 启动

先确认根目录存在 `gateway.yaml` 并设置好环境变量，然后：

```bash
cd ~/code/llm_gateway_v2
uvicorn app.main:app --reload --port 8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/health
```

## API 示例

所有接口（除 `/health`）都需要鉴权头 `Authorization: Bearer <token>`（默认 `test-key`）。

### GET /health

```bash
curl http://127.0.0.1:8001/health
```

预期返回：

```json
{ "status": "ok" }
```

### POST /v1/llm

带鉴权、非流式、基础文本请求：

```bash
curl -X POST http://127.0.0.1:8001/v1/llm \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{"model":"general-primary","messages":[{"role":"user","content":"你好"}]}'
```

预期返回（`LLMResponse`）：

```json
{
  "content": "你好！有什么可以帮你的吗？",
  "model": "deepseek-chat",
  "parsed": null,
  "usage": {
    "input_tokens": 5,
    "output_tokens": 11,
    "total_tokens": 16,
    "cached_tokens": 0,
    "reasoning_tokens": 0
  },
  "ttft_ms": 842.3,
  "cost_usd": 3.78e-6,
  "route": {
    "logical_model": "general-primary",
    "selected": "general-primary",
    "candidates": ["general-primary"],
    "rejected": [],
    "policy": "priority"
  }
}
```

字段说明：

- `parsed`：结构化输出时模型返回的 JSON 解析结果，普通请求为 `null`。
- `usage`：真实 token 用量（input/output/total/cached/reasoning），从上游响应提取。
- `ttft_ms`：首 token 延迟（非流式近似为发出请求到收到完整响应的耗时）。
- `cost_usd`：`input_tokens * input_price + output_tokens * output_price` 计算的美元成本。
- `route`：本次实际路由决策，`selected` 等于真正调用的模型别名，`rejected` 为被跳过的候选及原因。

### POST /v1/chat/completions（OpenAI 兼容）

```bash
curl -X POST http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{
    "model": "general-primary",
    "messages": [
      {"role": "system", "content": "你是一个简洁的助手"},
      {"role": "user", "content": "说一句话"}
    ]
  }'
```

预期返回（OpenAI ChatCompletion 结构）：

```json
{
  "id": "chatcmpl-xxxxxxxx",
  "object": "chat.completion",
  "model": "deepseek-chat",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "你好！" },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18 }
}
```

错误时返回 OpenAI 兼容错误体：

```json
{
  "error": {
    "message": "Rate limit exceeded",
    "type": "invalid_request_error",
    "code": "rate_limited"
  }
}
```

### POST /v1/llm/stream（流式）

```bash
curl -N -X POST http://127.0.0.1:8001/v1/llm/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{"model":"general-primary","messages":[{"role":"user","content":"逐字输出：你好世界"}]}'
```

预期返回为 SSE 格式：

```
data: {"delta": "你"}
data: {"delta": "好"}
data: {"delta": "世"}
data: {"delta": "界"}
data: [DONE]
```

### 结构化输出（Structured Output）

在请求体带 `response_schema`（JSON Schema），网关会注入 system 提示并要求模型只返回合法 JSON，返回后做 Schema 校验：

```bash
curl -X POST http://127.0.0.1:8001/v1/llm \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{
    "model": "general-primary",
    "messages": [{"role": "user", "content": "给我一个 3 个词的标题"}],
    "response_schema": {
      "type": "object",
      "properties": {"title": {"type": "string"}},
      "required": ["title"]
    }
  }'
```

预期返回 `LLMResponse.content` 为合法 JSON 字符串，可解析到 `parsed` 字段：

```json
{
  "content": "{\"title\": \"你好世界\"}",
  "model": "deepseek-chat",
  "parsed": { "title": "你好世界" },
  "usage": {
    "input_tokens": 9,
    "output_tokens": 7,
    "total_tokens": 16,
    "cached_tokens": 0,
    "reasoning_tokens": 0
  },
  "ttft_ms": 620.1,
  "cost_usd": 3.62e-6,
  "route": {
    "logical_model": "general-primary",
    "selected": "general-primary",
    "candidates": ["general-primary"],
    "rejected": [],
    "policy": "priority"
  }
}
```

## 错误码

所有内部错误统一为 `GatewayError`，携带 `code` / `message` / `status_code`；OpenAI 兼容接口会转换成 `{"error": {...}}`。完整错误码表格（含是否应重试的说明）见 [docs/error_codes.md](docs/error_codes.md)。

## 测试

```bash
pytest -v
```

项目测试不调用真实上游（通过 mock 完成），包括：API 与鉴权、路由与能力过滤、限流、重试退避、Trace 字段、错误映射、OpenAI 兼容层、适配器注册与 Anthropic 适配器等。

根目录下的 `test_*.py`（`test_client.py`、`test_stream.py` 等）是需要先启动 Gateway 服务再手动执行的真实请求脚本，不属于 pytest 测试集。

## 端到端验证

`scripts/verify.py` 是一份不依赖 pytest、真实调用本地服务的验证脚本，逐项核对六大功能并输出 PASS/FAIL/SKIP：

1. 两个模型调用（general-primary 走 `openai_responses`，general-backup 走 `anthropic_messages`）
2. 流式输出（SSE）
3. 结构化输出（`response_schema`）
4. 模板引用（`prompt.name` + `prompt.version`）
5. 可观测数据（`usage.input_tokens` / `output_tokens` / `ttft_ms` 非 0）
6. 重试与限流（限流打满配额后返回 429）

先启动服务：

```bash
uvicorn app.main:app --reload --port 8001
```

再运行脚本（注意设置 `GATEWAY_API_KEY`、以及所需上游密钥，缺 `ANTHROPIC_API_KEY` 时对应项会标 SKIP 而非 FAIL）：

```bash
python scripts/verify.py
```

如果要验证限流（`RATE_LIMIT_CAPACITY` / `RATE_LIMIT_REFILL_RATE` 控制默认配额，默认 60 / 10.0），用下面的命令以小配额启动服务。**推荐容量 20**：前 5 项功能测试合计不足 10 次请求，不会触发限流，而限流测试会连发 30 次把容量打满：

```bash
RATE_LIMIT_CAPACITY=20 RATE_LIMIT_REFILL_RATE=0.01 uvicorn app.main:app --reload --port 8001
```

**每次跑验证脚本前先重启服务**：限流测试会把服务端配额打满，而小容量配额（如 capacity=20、refill_rate=0.01）恢复极慢（约 10 秒才回补 0.1 个 token），若桶没恢复，下一次跑脚本时前面的功能测试也会全被限流成 429。执行顺序：

1. 在服务终端按 `Ctrl+C` 停掉当前服务；
2. 用小配额重新启动服务：

```bash
RATE_LIMIT_CAPACITY=20 RATE_LIMIT_REFILL_RATE=0.01 uvicorn app.main:app --reload --port 8001
```

3. 另开一个终端运行验证脚本：`python scripts/verify.py`

否则（服务端是默认大配额时）限流项会标 SKIP 并提示用小配额重启服务，不会误判为失败。

预期输出格式：

```
============================================================
LLM Gateway 端到端验证
============================================================
[PASS] 模型调用（两个模型）
       general-primary OK
       general-backup OK
[PASS] 流式输出（SSE）
       收到 12 个 delta，末尾 [DONE]
[PASS] 结构化输出（response_schema）
       parsed={'title': '...'}
[PASS] 模板引用（prompt）
       prompt=knowledge_decision/v1 渲染成功
[PASS] 可观测数据（usage/ttft）
       input=9 output=7 ttft_ms=321.4
[PASS] 重试
       unknown model 优雅返回 status=400
[PASS] 限流（429）
       状态序列 [200×20, 429×10]（含 429）
============================================================
汇总：7 项通过 / 0 项失败（0 项 SKIP）
============================================================
```

说明：

- 每项独立函数，返回 True/False（规格失败输出 `(status, detail)`，`skip` 表示因环境未配置而跳过）。
- 失败时打印响应体，方便排查。
- 限流判定在服务端进程内完成，脚本通过连发多次同模型请求观察是否出现 429；未触发时标 SKIP 并提示用小配额（`RATE_LIMIT_CAPACITY`/`RATE_LIMIT_REFILL_RATE`）重启服务验证。
