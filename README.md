# deepseek-search

把 DeepSeek 的联网搜索从模型里剥离出来——默认只取纯搜索结果，不等待 AI 总结；需要时也可以显式开启模型总结。

## 原理

DeepSeek API 的联网搜索是服务端执行的——模型收到你的问题，判断需要搜索，DeepSeek 服务器替你搜，然后把结果返回。正常流程下，搜完之后模型会写一大段总结，那部分**输出 token 是要收费的**。

这个工具默认用流式 API 发请求，在搜索结果抵达后、模型开始输出总结时把 HTTP 连接掐断，从而节省输出 token。传入 `--summary` 时则继续读取模型总结。

```
deepseek-search "你的问题"
       │
       ▼
POST api.deepseek.com/anthropic/v1/messages  (stream: true)
       │
       ├── thinking ───── 模型规划搜什么
       ├── tool_use  ───── 模型发起搜索
       ├── RESULTS  ───── 搜索结果返回
       ├── thinking ───── 模型思考怎么回复
       ├── text     ───── 默认在此断开；--summary 时继续读取
       │
       └── 默认返回纯搜索结果；可选返回模型总结
```

搜索是 DeepSeek 服务端做的。默认模式切断模型写总结的过程，主要产生输入 token；总结模式则会正常产生输出 token。真实费用以 DeepSeek 账单为准。

## 安装

```bash
# 全局安装
uv tool install git+https://github.com/KMnO4-zx/deepseek-search.git

# 更新到最新版
uv tool upgrade deepseek-search
```

源码安装：

```bash
git clone https://github.com/KMnO4-zx/deepseek-search.git
cd deepseek-search

# 首次安装
uv sync

# 更新
git pull && uv sync
```

## Agent Skill

如果希望 Claude Code、Codex 等 Agent 正确安装、调用、集成或调试 `deepseek-search`，可以安装仓库内置的 Skill：

```bash
npx skills add KMnO4-zx/deepseek-search -g -y
```

后续更新：

```bash
npx skills update deepseek-search -g -y
```

## 快速开始

```bash
# 第一步：登录（输入 API Key，不显示在屏幕上）
deepseek-search login

# 第二步：直接用
deepseek-search "Rust 教程"
```

API Key 保存在 `~/.config/deepseek-search/config.json`，文件权限 600，仅你自己可读。

不再需要每次 `export` 或传 `--api-key`。如果想换 Key：

```bash
deepseek-search login   # 会显示已有 Key，确认后替换
deepseek-search status  # 查看当前状态
deepseek-search logout  # 删除保存的 Key
```

如果还是想临时指定（比如用另一个团队的 Key）：

```bash
deepseek-search --api-key sk-xxx... "搜索词"
export DEEPSEEK_API_KEY=sk-xxx...
```

优先级：`--api-key` > 环境变量 > 配置文件。

## 使用

### 命令行

```bash
deepseek-search "Rust 教程"
```

需要模型根据搜索结果继续总结：

```bash
deepseek-search --summary "Rust 2026 年有哪些重要更新？"
```

`--summary` 模式会正常产生输出 token，终端只显示模型总结，不再重复打印原始搜索结果列表。结构化结果仍可通过 `--summary --json` 或 Python API 获取。

需要把搜索结果交给后续模型推理时，可以使用受约束的 Evidence 模式：

```bash
deepseek-search --evidence "The Ages of Lulu director"
```

该模式要求 DeepSeek 尽量只搜索一次，最多返回 8 条带来源标题的独立事实，不给出最终答案，也不在 Evidence 文本中加入 URL。`--evidence --json` 仍会保留带 URL 的结构化搜索结果和 `total_search_requests`。

输出：

```
🔍  Rust 教程
    10 条结果  ·  1 次搜索请求
    ~6 输入 token  ·  ~0 输出 token

   1. Learn Rust in a month of lunches
      https://find.library.duke.edu/...
   2. Rust Programming in easy steps
      https://ofppt.scholarvox.com/...
   ...
```

JSON 模式：

```bash
deepseek-search --json "最新 AI 新闻"
```

需要在 JSON 中同时返回总结：

```bash
deepseek-search --summary --json "最新 AI 新闻"
```

### Python

```python
from deepseek_search import search

resp = search("今天天气")
for r in resp.results:
    print(f"{r.title} — {r.url}")
```

开启总结：

```python
resp = search("Rust 2026 年有哪些重要更新？", summarize=True)
print(resp.summary)
```

提取证据：

```python
resp = search("The Ages of Lulu director", mode="evidence")
print(resp.evidence)
```

## 默认模型与成本

默认模型为 `deepseek-v4-flash`。下面的数据于 2026-07-31 使用
[`benchmark.py`](benchmark.py) 中相同的 30 种查询分别实测，summary 最大输出
为 2,048 token，两组均成功 30/30：

| 模式 | 平均输入 token | 平均输出 token | 平均耗时 | 平均搜索请求 | 平均结果数 | 单次估算费用 |
|---|---:|---:|---:|---:|---:|---:|
| 关闭 summary | 123.9* | 0* | 4.8s | 1.90 | 17.13 | ¥0.000124* |
| 开启 summary | 23,442.5 | 1,298.7 | 13.4s | 2.17 | 20.27 | ¥0.026040 |

按相同均值外推：

| 模式 | 搜索次数 | 输入 token | 输出 token | 估算费用 |
|---|---:|---:|---:|---:|
| 关闭 summary | 100 | ~12,393* | ~0* | ¥0.0124* |
| 关闭 summary | 200 | ~24,787* | ~0* | ¥0.0248* |
| 关闭 summary | 500 | ~61,967* | ~0* | ¥0.0620* |
| 关闭 summary | 1,000 | ~123,933* | ~0* | ¥0.1239* |
| 开启 summary | 100 | ~2,344,250 | ~129,870 | ¥2.6040 |
| 开启 summary | 200 | ~4,688,500 | ~259,740 | ¥5.2080 |
| 开启 summary | 500 | ~11,721,250 | ~649,350 | ¥13.0199 |
| 开启 summary | 1,000 | ~23,442,500 | ~1,298,700 | ¥26.0399 |

费用按 DeepSeek 当前公布的 `deepseek-v4-flash` 缓存未命中价格估算：
输入 ¥1/百万 token、输出 ¥2/百万 token，真实扣费以平台账单为准。
详见 [DeepSeek 模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)。

\* 关闭 summary 时，客户端会在最终 `usage` 到达前主动断流，因此这里只是
客户端截流前可见的 token 与费用，不能视为完整账单。开启 summary 会读到
最终响应，usage 更完整。

## 命令一览

| 命令 | 说明 |
|---|---|
| `deepseek-search login` | 保存 API Key 到配置文件 |
| `deepseek-search logout` | 删除保存的 Key |
| `deepseek-search status` | 查看当前 Key 状态 |
| `deepseek-search "xxx"` | 搜索 |
| `deepseek-search --json "xxx"` | 搜索（JSON 输出） |
| `deepseek-search --summary "xxx"` | 搜索并让模型总结 |
| `deepseek-search --summary --json "xxx"` | 搜索并以 JSON 返回结果和总结 |
| `deepseek-search --evidence "xxx"` | 搜索并提取受约束的独立证据 |
| `deepseek-search --evidence --json "xxx"` | 返回 Evidence 和带 URL 的结构化结果 |

## API

### `search(query, *, api_key=None, model="deepseek-v4-flash", timeout=30.0, force_search=True, summarize=False, mode=None)`

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | `str` | 必填 | 搜索关键词 |
| `api_key` | `str \| None` | 自动解析 | 不传则走配置文件。详见上方"快速开始" |
| `model` | `str` | `"deepseek-v4-flash"` | 模型名称 |
| `endpoint` | `str` | `"https://api.deepseek.com/anthropic/v1/messages"` | API 地址 |
| `timeout` | `float` | `30.0` | 超时时间（秒） |
| `force_search` | `bool` | `True` | 强制模型使用联网搜索 |
| `summarize` | `bool` | `False` | 是否继续读取模型基于搜索结果生成的总结 |
| `mode` | `"raw" \| "summary" \| "evidence" \| None` | `None` | 显式选择模式；省略时继续按 `summarize` 决定 |

返回值 `SearchResponse`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `query` | `str` | 原始查询 |
| `results` | `list[SearchResult]` | 搜索结果列表 |
| `result_count` | `int` | 结果数量 |
| `search_queries` | `list[str]` | 模型实际使用的搜索词 |
| `total_search_requests` | `int` | 搜索 API 调用次数 |
| `usage` | `dict` | Token 用量 |
| `summary` | `str \| None` | 开启 `summarize` 后返回的模型总结 |
| `evidence` | `str \| None` | Evidence 模式返回的来源化事实文本 |

### `SearchResult`

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | `str` | 页面标题 |
| `url` | `str` | 页面 URL |
| `page_age` | `str \| None` | 页面时效（如有） |

## License

MIT
