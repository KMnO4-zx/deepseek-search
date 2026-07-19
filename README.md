# deepseek-search

把 DeepSeek 的联网搜索从模型里剥离出来——**纯搜索结果，不要 AI 总结，几近零成本**。

## 原理

DeepSeek API 的联网搜索是服务端执行的——模型收到你的问题，判断需要搜索，DeepSeek 服务器替你搜，然后把结果返回。正常流程下，搜完之后模型会写一大段总结，那部分**输出 token 是要收费的**。

这个工具做的事情很简单：用流式 API 发请求，在搜索结果抵达的瞬间把 HTTP 连接掐断，模型来不及写总结，token 就省下来了。

```
deepseek-search "你的问题"
       │
       ▼
POST api.deepseek.com/anthropic/v1/messages  (stream: true)
       │
       ├── thinking ───── 模型规划搜什么
       ├── tool_use  ───── 模型发起搜索
       ├── RESULTS  ───── 搜索结果返回 ← 我们只收这个
       ├── thinking ───── 模型思考怎么回复
       ├── text     ───── 🔪 HTTP 连接在此断开
       │
       └── 纯搜索结果，output token = 0
```

搜索是 DeepSeek 服务端做的，搜索本身不收费。但我们切断了模型写总结的过程，所以只付输入 token 的钱（每次大约 10 个 token，几乎为零）。

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

### Python

```python
from deepseek_search import search

resp = search("今天天气")
for r in resp.results:
    print(f"{r.title} — {r.url}")
```

## 默认模型与成本

| 项目 | 说明 |
|---|---|
| 默认模型 | `deepseek-v4-flash`（DeepSeek 最便宜的模型） |
| 每次输入 token | ~9（仅 query + tool 定义） |
| 每次输出 token | **0**（在模型写总结前断开连接） |
| 每次费用 | 约 ¥0.0003（三万分之一元） |

下面是用 30 种不同查询实测后，外推到更大规模的数据：

| 搜索次数 | 输入 token | 输出 token | 总费用 |
|---|---|---|---|
| 100 | ~900 | ~0 | ¥0.03 |
| 200 | ~1,800 | ~0 | ¥0.07 |
| 500 | ~4,500 | ~0 | ¥0.17 |
| 1,000 | ~9,000 | ~0 | ¥0.33 |

> 即使每天搜 1000 次，一个月花费也不到 ¥10。

偶尔（约 5-10% 的概率）模型会不触发搜索直接用自身知识回答，此时会产生少量输出 token，纳入统计后几乎可以忽略。

## 命令一览

| 命令 | 说明 |
|---|---|
| `deepseek-search login` | 保存 API Key 到配置文件 |
| `deepseek-search logout` | 删除保存的 Key |
| `deepseek-search status` | 查看当前 Key 状态 |
| `deepseek-search "xxx"` | 搜索 |
| `deepseek-search --json "xxx"` | 搜索（JSON 输出） |

## API

### `search(query, *, api_key=None, model="deepseek-v4-flash", timeout=30.0, force_search=True)`

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | `str` | 必填 | 搜索关键词 |
| `api_key` | `str \| None` | 自动解析 | 不传则走配置文件。详见上方"快速开始" |
| `model` | `str` | `"deepseek-v4-flash"` | 模型名称 |
| `endpoint` | `str` | `"https://api.deepseek.com/anthropic/v1/messages"` | API 地址 |
| `timeout` | `float` | `30.0` | 超时时间（秒） |
| `force_search` | `bool` | `True` | 强制模型使用联网搜索 |

返回值 `SearchResponse`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `query` | `str` | 原始查询 |
| `results` | `list[SearchResult]` | 搜索结果列表 |
| `result_count` | `int` | 结果数量 |
| `search_queries` | `list[str]` | 模型实际使用的搜索词 |
| `total_search_requests` | `int` | 搜索 API 调用次数 |
| `usage` | `dict` | Token 用量 |

### `SearchResult`

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | `str` | 页面标题 |
| `url` | `str` | 页面 URL |
| `page_age` | `str \| None` | 页面时效（如有） |

## License

MIT
