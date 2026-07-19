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

字段可能为空，但键名应保持稳定。提前断流意味着 `usage` 可能只有请求早期已经返回的统计。

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
)
```

返回 `SearchResponse`：

- `query: str`：原始用户查询。
- `results: list[SearchResult]`：原始搜索结果。
- `search_queries: list[str]`：模型实际提交给搜索工具的查询。
- `total_search_requests: int`：收到的搜索结果 block 数量。
- `usage: dict`：断流前已收到的 token 统计。
- `result_count: int`：`len(results)` 的只读属性。

`SearchResult` 包含 `title`、`url` 和可选 `page_age`。

## 错误处理

未找到凭据时，`search()` 抛出 `ValueError`。HTTP 非成功状态通过 `httpx` 抛出异常，流内 DeepSeek `error` 事件抛出 `RuntimeError`。库调用方应按自己的重试策略处理网络异常，不要默认无限重试或吞掉鉴权错误。
