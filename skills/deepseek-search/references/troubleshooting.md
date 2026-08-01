# 故障排查

## 先收集安全信息

只收集以下信息：

- 安装方式和 `deepseek-search --version`。
- Python 版本和包版本。
- endpoint 域名、模型名、HTTP 状态码。
- 脱敏后的异常类型、消息和 SSE 事件类型序列。
- `result_count`、`total_search_requests`、`search_queries` 和 `usage` 的键名。

不要收集请求头、完整 API Key、配置文件原文或包含凭据的 shell 历史。

## 未配置 API Key

症状：`ValueError: DEEPSEEK_API_KEY is required`。

处理：

1. 优先运行 `deepseek-search login`。
2. 用 `deepseek-search status` 检查配置文件是否存在；它不会检查环境变量。
3. 如果使用 `XDG_CONFIG_HOME`，确认登录和运行命令处在相同环境。
4. 不要把 Key 作为诊断输出的一部分。

## HTTP 401 或 403

优先按鉴权问题处理：

1. 确认 endpoint 是否是预期的 DeepSeek 或兼容代理。
2. 确认请求使用 `x-api-key`，代理若要求其他 header 必须显式适配。
3. 确认没有被更高优先级的 `--api-key` 或 `DEEPSEEK_API_KEY` 覆盖。
4. 用平台侧 Key 状态确认额度和权限，不要通过打印 Key 比对。

## HTTP 400、未知模型或未知工具

检查默认模型、endpoint 和 `web_search_20260209` 是否仍受服务端支持。远端协议可能变化；先保存脱敏后的响应错误和最小请求字段，再更新常量或请求结构。不要靠改 prompt 掩盖协议级错误。

## 超时或连接中断

1. 适当提高 `--timeout` 或 Python `timeout`。
2. 区分“结果返回后的预期主动断流”和“结果到达前的网络失败”。
3. 只有在没有收到结果时才自动重试，并设置有界次数与退避。
4. 代理环境下确认它支持 SSE 长连接且不会缓冲完整响应。

## `result_count == 0`

按以下顺序判断：

1. `total_search_requests == 0`：模型或服务端没有进入搜索结果 block，检查 tool choice、工具类型和协议事件。
2. `total_search_requests > 0` 但结果为空：检查结果是放在 block start 的 `content`，还是 `web_search_delta.partial`。
3. 有结果事件但字段为空：记录脱敏字段名，确认远端 schema 是否变化。
4. 仅部分查询为空：把它视为搜索质量或内容可用性问题，不要伪造结果补齐。

## `search_queries` 为空或不完整

服务端可能在 `server_tool_use` 开始事件中给完整 input，也可能通过多个 `input_json_delta` 分段发送。确认 `partial_query` 在对应 block stop 时被拼接和清空。JSON 不完整时保持为空，不要猜测查询词。

## `usage` 缺字段或输出 token 为零

这是提前断流的预期结果之一：客户端通常在最终 `message_delta` 前退出。把 `usage` 当作部分观测，不要据此断言服务端最终账单。需要计费结论时查看 DeepSeek 平台账单或在明确授权下做受控 benchmark。

使用 Summary 或 Evidence 时客户端会读取到响应结束，通常能拿到最终 output token；如果 `summary` / `evidence` 仍为空，检查搜索结果之后是否出现 `text` block、`text_delta` 和 `message_stop`。

## Evidence 为空或违反约束

按以下顺序检查：

1. 确认使用 CLI `--evidence` 或 Python `mode="evidence"`，并确认版本至少为 `0.3.1`。
2. `result_count > 0` 但 `evidence is None`：检查搜索结果之后是否存在最终 text block，客户端是否完整消费到 `message_stop`。
3. `total_search_requests == 0`：客户端允许返回这一异常状态，检查服务端是否执行了强制工具调用；不要伪造搜索结果。
4. `RuntimeError: Evidence mode allows at most one web search, but received N`：服务端或测试 fixture 违反了 `max_uses=1` 契约。Evidence 不返回多轮结果；Raw 和 Summary 不受此校验影响。
5. Evidence 出现 URL、最终答案、实体比较或跨来源推理：先确认请求使用专用 Evidence system prompt，再保存脱敏文本作为回归样本。语义边界依赖模型遵循提示词，不能声称绝对保证。
6. 确认 URL 仍存在于 `response.results` 或 Evidence JSON 的 `results` 中；不要为了清理 Evidence 文本删除结构化 URL。

参数冲突 `summarize=True cannot be combined with mode='raw'/'evidence'` 属于预期校验。删除 `summarize=True`，或改用 `mode="summary"`。

## CLI 与 Python 行为不同

- CLI 默认使用强制搜索，没有暴露 `force_search` 开关。
- CLI 默认是 Raw；`--summary` 和 `--evidence` 都会继续读取模型文本并产生输出 token。
- CLI 会捕获异常、输出到 stderr 并以状态码 1 退出；Python API 直接抛异常。
- CLI `status` 只读取配置文件；Python `resolve_api_key()` 还会检查显式参数和环境变量。
- CLI Raw JSON 不增加生成文本字段；Summary JSON 增加 `summary`，Evidence JSON 增加 `evidence`，两者都保留结构化 `results`。
