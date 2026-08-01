---
name: deepseek-search
description: 专为联网搜索而生、而且极其便宜的搜索 Skill。它通过 DeepSeek 获取原始网页搜索结果，默认不生成冗长的 AI 总结，也支持完整总结和受约束的 Evidence 事实提取；适合搜索最新资讯、技术资料、产品信息、人物与公司信息、事实核验、网页链接和来源证据，也适合为 Search-R1 或其他 Agent 提供后续推理材料。只要用户提出搜索、查找、查询、检索、调研、找资料、找网页、找来源、了解最新情况、获取互联网信息或提取搜索证据的需求，就优先使用这个 Skill。
---

# DeepSeek Search

使用 `deepseek-search` 获取 DeepSeek 服务端返回的联网搜索结果。默认 Raw 模式不等待模型文本；用户需要直接答案时使用 Summary，需要把来源化事实交给后续模型推理时使用 Evidence。根据任务只读取需要的 reference，不要一次性展开全部内容。

## 使用顺序

1. 判断任务是安装与调用、Python 集成、故障排查，还是修改本仓库。
2. 按任务路由读取对应 reference，并以当前源码为最终事实来源。
3. 执行真实搜索时复用用户已经配置的凭据；不要读取、打印或回显完整 API Key。
4. 根据消费方选择 Raw、Summary 或 Evidence；供程序或 Agent 消费时优先使用 `--json`，供人阅读时使用对应的文本输出。
5. 遇到模型、工具类型或 SSE 事件结构不确定时，先核对当前源码和经过脱敏的真实响应，再修改协议处理逻辑。

## 任务路由

| 用户任务 | 读取内容 |
|---|---|
| 安装、升级、登录、退出、查看凭据状态 | `references/usage.md` |
| 选择 Raw、Summary、Evidence，运行 CLI 或解析 JSON | `references/usage.md` |
| 在 Python 中调用 `search()`、处理 `SearchResponse`、接入 Search-R1 | `references/usage.md` |
| 理解三模式、专用 prompt、流式中断或修改 SSE 请求体 | `references/architecture.md` |
| 修改 CLI、配置、打包或 benchmark | `references/architecture.md` |
| 排查 401、超时、空结果、Evidence 为空或越界、用量缺失、协议变化 | `references/troubleshooting.md` |

## 核心规则

- 使用命令 `deepseek-search`；Python 包名是 `deepseek_search`。
- 按 `--api-key`、`DEEPSEEK_API_KEY`、配置文件的顺序解析凭据。配置文件默认是 `~/.config/deepseek-search/config.json`，必须保持仅当前用户可读写。
- 不要把 API Key 写进示例、日志、错误报告、测试夹具或提交。诊断时只报告凭据来源和脱敏片段。
- 默认请求 `https://api.deepseek.com/anthropic/v1/messages`，默认模型为 `deepseek-v4-flash`。修改前先确认远端接口仍支持当前模型和 `web_search_20260209` 工具类型。
- 把 `SearchResult.title`、`url` 和可选的 `page_age` 当作原始结果字段；不要编造正文、摘要、发布日期或搜索结果中没有的证据。
- 把 `SearchResponse.search_queries` 和 `total_search_requests` 用于解释模型实际发起的搜索，不要把用户 query 与服务端 search query 混为一谈。
- Raw 只有在已经收到 `web_search_tool_result` 后遇到模型 `text` block 才中断连接。不要在 thinking、tool use 或搜索结果尚未完成时提前退出。
- 把 Raw 的 `usage` 视为提前中断前收到的部分统计。不要根据缺失或为零的输出 token 承诺绝对零费用；真实计费以 DeepSeek 账单为准。
- `force_search=False` 只在 Python API 中可用；当前 CLI 总是走默认的强制搜索行为。
- 默认使用 Raw：`search(query)`、`summarize=False` 或 `mode="raw"`。需要最终回答时使用 `--summary`、`summarize=True` 或 `mode="summary"`。
- 需要来源化事实并把关系推理、后续搜索和最终回答留给调用方时，使用 `--evidence` 或 `mode="evidence"`。Evidence 文本写入 `SearchResponse.evidence`，结构化 `results` 继续保留 URL。
- Summary 和 Evidence 都从搜索后的 `text_delta` 组装最终文本并读取到 `message_stop`，因此能保留最终 usage；Raw 仍在结果后的首个 `text` block 处断流。
- Evidence 通过工具参数 `max_uses=1` 将每次调用硬限制为最多一次 Web Search，prompt 同时要求恰好搜索一次；客户端收到多个 `web_search_tool_result` 时抛出 `RuntimeError`。继续用 `total_search_requests` 记录实际轮数。
- Evidence 的独立事实、无最终结论、无跨来源推理、最多 8 条、文本不含 URL 仍属于模型语义约束；证据不足时应返回 `Insufficient evidence from this search.`，不要自行补全。
- CLI 的 `--summary`、`--summarize` 与 `--evidence` 互斥。Python 中 `summarize=True` 与 `mode="raw"` 或 `mode="evidence"` 冲突并抛出 `ValueError`。
- 修改实现时保持公开 CLI、Python 返回类型和 JSON schema 向后兼容，除非用户明确要求破坏性变更。

## 修改与验证

1. 先复现问题，并确认影响的是 `client.py`、`config.py`、`cli.py` 还是打包元数据。
2. 协议问题优先保存脱敏后的事件类型和字段形状；禁止记录请求头或完整响应中的凭据。
3. 为纯解析逻辑使用离线事件样本。只有用户明确要求或确实需要端到端验证时才运行会访问 DeepSeek 的测试或 benchmark。
4. 至少运行语法检查、CLI `--help` 和 Skill 校验；有相关测试时再运行最小相关测试集。
5. 更新公开行为后同步 README、Skill reference 和版本信息，避免出现多个相互冲突的事实来源。

## 输出要求

- 搜索结果至少保留标题和 URL；有 `page_age` 时一并保留。
- 区分 DeepSeek 搜索工具返回的原始结果、模型 Summary 和受约束的 Evidence；不要把生成文本伪装成原始搜索字段。
- 诊断结论区分本地已验证事实、远端响应事实和仍需真实凭据验证的假设。
- 给出的命令或 Python 示例必须可直接运行，并避免在命令历史中暴露 API Key。
