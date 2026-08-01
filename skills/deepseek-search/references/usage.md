# 使用与集成

## 安装与升级

全局安装 CLI：

```bash
uv tool install git+https://github.com/KMnO4-zx/deepseek-search.git
```

升级已安装版本：

```bash
uv tool upgrade deepseek-search
```

在源码仓库中开发：

```bash
uv sync
uv run deepseek-search --help
```

仓库内的 `uv run deepseek-search` 直接运行当前工作树，包括尚未 commit 的修改。直接调用全局安装的 `deepseek-search` 可能仍是旧版本。

## 凭据管理

优先使用交互式登录，避免 API Key 进入 shell 历史：

```bash
deepseek-search login
deepseek-search status
deepseek-search logout
```

`login` 把 Key 写入 `${XDG_CONFIG_HOME:-~/.config}/deepseek-search/config.json`，并把文件权限设为 `600`。解析优先级为：

1. Python API 或 CLI 显式传入的 `api_key` / `--api-key`
2. `DEEPSEEK_API_KEY` 环境变量
3. 配置文件

注意：当前 `status` 只显示配置文件中保存的 Key，不检查环境变量或命令行参数。不要通过读取配置文件来“验证”凭据，也不要在输出中展示完整 Key。

## 命令行搜索

人类可读输出：

```bash
deepseek-search "Python 3.14 新特性"
```

结构化输出：

```bash
deepseek-search --json "Python 3.14 新特性"
```

搜索并让模型总结：

```bash
deepseek-search --summary "Python 3.14 新特性"
deepseek-search --summary --json "Python 3.14 新特性"
```

总结模式会继续读取模型输出并产生输出 token。人类可读输出只显示总结，不追加原始搜索结果列表；`--summary --json` 和 Python API 仍保留结构化 `results`。默认模式仍然只返回原始搜索结果。

为 Search-R1 或其他后续推理方提取受约束证据：

```bash
deepseek-search --evidence "The Ages of Lulu director"
deepseek-search --evidence --json "The Ages of Lulu director"
```

Evidence 模式通过 `max_uses=1` 将每次调用限制为最多一次 Web Search，并在客户端拒绝多个搜索结果块。Evidence 文本最多包含 8 条带来源标题的独立事实，要求不回答原问题、不跨来源推理、不输出 URL；首轮证据不足时返回 `Insufficient evidence from this search.`。普通文本输出只显示 Evidence；JSON 同时保留 `results` 中的 URL、`total_search_requests`、最终 `usage` 和 `evidence`。`--summary`、`--summarize` 与 `--evidence` 互斥。

常用覆盖参数：

```bash
deepseek-search \
  --model deepseek-v4-flash \
  --timeout 60 \
  --json \
  "查询内容"
```

`--endpoint` 可用于兼容代理或测试服务器。不要在共享命令、日志或文档示例中使用 `--api-key` 写入真实 Key。

JSON 输出结构：

```json
{
  "query": "用户输入",
  "search_queries": ["服务端实际搜索词"],
  "total_search_requests": 1,
  "result_count": 10,
  "results": [
    {
      "title": "页面标题",
      "url": "https://example.com/page",
      "page_age": "可选时效信息"
    }
  ],
  "usage": {
    "input_tokens": 9
  }
}
```

默认 JSON 输出不包含 `summary` 或 `evidence`，以保持原有 schema。使用 `--summary` 时增加 `"summary": "..."`；使用 `--evidence` 时增加 `"evidence": "[1] Source: ..."`。提前断流意味着 Raw 的 `usage` 可能只有请求早期已经返回的统计。

## Python API

最小调用：

```python
from deepseek_search import search

response = search("Python 3.14 新特性")
for item in response.results:
    print(item.title, item.url, item.page_age)
```

完整签名：

```python
search(
    query,
    *,
    api_key=None,
    model="deepseek-v4-flash",
    endpoint="https://api.deepseek.com/anthropic/v1/messages",
    timeout=30.0,
    force_search=True,
    summarize=False,
    mode=None,
)
```

返回 `SearchResponse`：

- `query: str`：原始用户查询。
- `results: list[SearchResult]`：原始搜索结果。
- `search_queries: list[str]`：模型实际提交给搜索工具的查询。
- `total_search_requests: int`：收到的搜索结果 block 数量。
- `usage: dict`：客户端已收到的 token 统计；默认断流模式下可能不完整。
- `result_count: int`：`len(results)` 的只读属性。
- `summary: str | None`：Summary 模式组装出的模型总结。
- `evidence: str | None`：Evidence 模式从搜索后最终文本组装出的来源化事实。

`SearchResult` 包含 `title`、`url` 和可选 `page_age`。

模式兼容规则：

| 调用 | 模式 | 生成字段 |
|---|---|---|
| `search(query)`、`summarize=False`、`mode="raw"` | Raw | `summary=None`、`evidence=None` |
| `summarize=True`、`mode="summary"` | Summary | `summary` |
| `mode="evidence"` | Evidence | `evidence` |

未传 `mode` 时继续由 `summarize` 决定，保证旧调用兼容。`summarize=True` 与 `mode="raw"` 或 `mode="evidence"` 同时出现时抛出 `ValueError`；与 `mode="summary"` 同时出现合法。

Evidence Python 示例：

```python
response = search("The Ages of Lulu director", mode="evidence")
print(response.evidence)

# 供程序记录和监控
print(response.total_search_requests)
for item in response.results:
    print(item.title, item.url)
```

Summary 和 Evidence 都会继续读取到响应结束并获得更完整的 output token 统计；Raw 保持原来的提前断流行为。Evidence 的搜索次数同时受 `max_uses=1` 和客户端计数校验约束，其他语义边界由专用 system prompt 实现；调用方仍应按需要验证证据质量。

## 错误处理

未找到凭据、模式名称无效或参数冲突时，`search()` 抛出 `ValueError`。HTTP 非成功状态通过 `httpx` 抛出异常，流内 DeepSeek `error` 事件抛出 `RuntimeError`。库调用方应按自己的重试策略处理网络异常，不要默认无限重试或吞掉鉴权错误。
