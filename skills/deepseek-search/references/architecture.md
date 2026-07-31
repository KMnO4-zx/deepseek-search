# 架构与维护契约

## 代码地图

| 路径 | 职责 |
|---|---|
| `src/deepseek_search/client.py` | 请求体、SSE 解析、结果收集、提前断流、可选总结、公开数据类型 |
| `src/deepseek_search/config.py` | XDG 配置路径、Key 保存/读取/删除、凭据优先级 |
| `src/deepseek_search/cli.py` | `login/logout/status` 分发、搜索参数、文本与 JSON 输出 |
| `src/deepseek_search/__init__.py` | 导出公开 Python API 和版本 |
| `pyproject.toml` | 包版本、依赖、`deepseek-search` 命令入口 |
| `benchmark.py` | 使用真实 API 的成本与耗时抽样，不属于离线测试 |

## 请求契约

`search()` 向 Anthropic 兼容 endpoint 发送流式 POST：

- 请求头使用 `x-api-key`，不是 Bearer token。
- `stream` 必须为 `true`。
- tools 中声明 `{ "type": "web_search_20260209", "name": "web_search" }`。
- `force_search=True` 时使用 `tool_choice: {"type": "any"}`；否则使用 `auto`。
- system prompt 要求模型先调用搜索工具。

这些字段属于远端协议，可能独立于本包版本变化。出现 4xx、未知工具或事件字段变化时，先用脱敏最小请求核实协议，再改解析器。

## SSE 状态流

当前客户端按下面的顺序处理事件：

```text
message_start
  -> content_block_start(server_tool_use)
  -> content_block_delta(input_json_delta)
  -> content_block_stop
  -> content_block_start(web_search_tool_result)
  -> content_block_delta(web_search_delta) *
  -> content_block_stop
  -> content_block_start(text)
       -> 默认模式：在这里断开
       -> summarize=True：收集 text_delta，直到 message_stop
```

关键状态：

- `current_block_type`：当前 block 的类型。
- `partial_query`：拼接分段到达的搜索 query JSON。
- `has_search_results`：确认至少进入过搜索结果 block 后，才允许在 text block 处断流。
- `search_request_count`：统计 `web_search_tool_result` block，而不是结果条数。
- `collecting_summary`：开启总结后，只收集最后一轮搜索之后的模型文本。

结果可能完整出现在 `content_block_start.content_block.content`，也可能通过 `web_search_delta.partial` 流式到达。修改时必须保留两条路径，并用捕获的协议样本检查是否需要去重。

`_parse_sse()` 只接受单行 `data: {JSON}`。`[DONE]`、空行和非 JSON 行会被忽略。若远端切换为多行 data 或不同 framing，需要先补离线样本再调整 parser。

## 不变量

- 在收到结果前不要因 text block 断流。
- 默认模式不要等待模型总结完成后再返回，否则失去该工具的成本和延迟优势。
- `summarize=True` 时必须读取完整文本和最终 usage，并明确该模式会产生输出 token。
- 不要把 thinking 或模型文本混入 `SearchResult`。
- 解析缺失字段时继续使用安全默认值，避免单条不完整结果终止整次搜索。
- 保持同步公开 API；新增异步 API 时使用新入口，不要悄悄改变 `search()` 的返回方式。
- 保持凭据解析和存储与 XDG 规则兼容。

## CLI 与版本同步

公开版本同时出现在 `pyproject.toml`、`src/deepseek_search/__init__.py` 和 CLI `--version`。发布版本变更时同步三处。

CLI 搜索模式把位置参数以空格拼成一个 query。`login/logout/status` 只在第一个参数完全匹配时走子命令分发。新增子命令时同时更新分发表、README 和 Skill reference。

## 验证命令

不访问外网的最小验证：

```bash
uv run python -m compileall -q src benchmark.py
uv run python -m unittest discover -s tests -v
uv run deepseek-search --help
uv run deepseek-search --version
```

构建包时运行：

```bash
uv build
```

benchmark 会产生真实 API 请求并可能计费，只在用户要求、凭据已经安全配置且确有必要时运行：

```bash
uv run python benchmark.py 30 --mode both --workers 5
```

`--mode` 支持 `raw`、`summary` 和 `both`。关闭 summary 时只能观测提前断流前的部分 usage；不要把它当作最终账单。协议修改应优先添加不访问网络的 SSE 事件样本测试，再选择一次最小端到端搜索验证。
