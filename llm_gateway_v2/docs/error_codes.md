# 错误码参考

本表列出 LLM Gateway 所有错误码。来源：

- [app/core/errors.py](../app/core/errors.py) 中定义的全部常量
- [app/services/gateway.py](../app/services/gateway.py) 中 `map_upstream_error` 映射出的错误码

HTTP 状态码为网关返回给客户端的状态码（`GatewayError.status_code`）。

| 错误码 | HTTP 状态码 | 含义 | 客户端是否应重试 |
| --- | --- | --- | --- |
| `unknown_model` | 400 | 请求的模型不存在 | 否（请求错误） |
| `unknown_prompt_template` | 400 | 引用了不存在的 prompt 模板 | 否（请求错误） |
| `missing_prompt_variable` | 400 | prompt 模板缺少必需变量 | 否（请求错误） |
| `upstream_bad_request` | 400 | 上游拒绝了请求（其他 4xx） | 否（请求错误） |
| `upstream_auth_error` | 502 | 上游鉴权失败（AuthenticationError） | 否（需先修正凭据，重试无意义） |
| `unauthorized` | 401 | 缺少或无效的 API key | 否（需先提供有效凭据） |
| `rate_limited` | 429 | 网关层限流（按模型分桶） | 是（等待后重试） |
| `upstream_rate_limited` | 429 | 上游限流（RateLimitError） | 是（采用退避等待后重试） |
| `gateway_misconfigured` | 500 | 网关配置缺失（如 DEEPSEEK_API_KEY 未设置） | 否（需先修复配置） |
| `upstream_error` | 502 | 上游返回 5xx 或未知错误 | 是（短暂故障，可退避重试） |
| `model_unavailable` | 502 | 所有候选模型不可用或熔断 | 是（稍后重试） |
| `upstream_connection_error` | 502 | 无法连接上游（ConnectionError） | 是（退避重试） |
| `invalid_json` | 502 | 结构化输出无法解析为合法 JSON | 否（模型输出问题，重试常规无帮助） |
| `schema_validation_failed` | 502 | 结构化输出未通过 JSON Schema 校验 | 否（模型输出问题） |
| `structured_output_validation_failed` | 502 | 结构化输出校验失败（通用码） | 否（模型输出问题） |
| `upstream_timeout` | 504 | 上游调用超时（TimeoutError） | 是（退避重试） |
| `concurrency_timeout` | 504 | 并发/整体调用超时 | 是（稍后重试） |

## 备注

- 客户端重试建议：返回 `401`、`400`、`429`（网关限流）按语义处理；`5xx` 系列（`upstream_error`、`upstream_timeout`、`upstream_connection_error`、`upstream_rate_limited`、`model_unavailable`）适合指数退避重试。
- 上游错误码通过 `map_upstream_error` 从异常类型映射得出，详见 [app/core/errors.py](../app/core/errors.py)。