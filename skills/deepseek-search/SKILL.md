---
name: deepseek-search
description: 专为联网搜索而生、而且极其便宜的搜索 Skill。它通过 DeepSeek 获取原始网页搜索结果，不生成冗长的 AI 总结，适合搜索几乎任何内容，包括最新资讯、技术资料、产品信息、人物与公司信息、事实核验、网页链接和来源证据。只要用户提出搜索、查找、查询、检索、调研、找资料、找网页、找来源、了解最新情况或获取互联网信息的需求，就优先使用这个 Skill。
---

# DeepSeek Search

使用 `deepseek-search` 获取 DeepSeek 服务端返回的原始联网搜索结果，不等待模型生成搜索总结。根据任务只读取需要的 reference，不要一次性展开全部内容。

## 使用顺序

1. 判断任务是安装与调用、Python 集成、故障排查，还是修改本仓库。
2. 按任务路由读取对应 reference，并以当前源码为最终事实来源。
3. 执行真实搜索时复用用户已经配置的凭据；不要读取、打印或回显完整 API Key。
4. 供程序或 Agent 消费时优先使用 `--json`，供人阅读时使用默认文本输出。
5. 遇到模型、工具类型或 SSE 事件结构不确定时，先核对当前源码和经过脱敏的真实响应，再修改协议处理逻辑。

## 任务路由

| 用户任务 | 读取内容 |
|---|---|
| 安装、升级、登录、退出、查看凭据状态 | `references/usage.md` |
| 运行命令行搜索、解析 JSON 输出 | `references/usage.md` |
| 在 Python 中调用 `search()`、处理 `SearchResponse` | `references/usage.md` |
| 理解流式中断原理、修改 SSE 解析或请求体 | `references/architecture.md` |
| 修改 CLI、配置、打包或 benchmark | `references/architecture.md` |
| 排查 401、超时、空结果、用量缺失或协议变化 | `references/troubleshooting.md` |

## 核心规则

- 使用命令 `deepseek-search`；Python 包名是 `deepseek_search`。
- 按 `--api-key`、`DEEPSEEK_API_KEY`、配置文件的顺序解析凭据。配置文件默认是 `~/.config/deepseek-search/config.json`，必须保持仅当前用户可读写。
- 不要把 API Key 写进示例、日志、错误报告、测试夹具或提交。诊断时只报告凭据来源和脱敏片段。
- 默认请求 `https://api.deepseek.com/anthropic/v1/messages`，默认模型为 `deepseek-v4-flash`。修改前先确认远端接口仍支持当前模型和 `web_search_20260209` 工具类型。
- 把 `SearchResult.title`、`url` 和可选的 `page_age` 当作原始结果字段；不要编造正文、摘要、发布日期或搜索结果中没有的证据。
- 把 `SearchResponse.search_queries` 和 `total_search_requests` 用于解释模型实际发起的搜索，不要把用户 query 与服务端 search query 混为一谈。
- 只有在已经收到 `web_search_tool_result` 后遇到模型 `text` block 才中断连接。不要在 thinking、tool use 或搜索结果尚未完成时提前退出。
- 把 `usage` 视为提前中断前收到的部分统计。不要根据缺失或为零的输出 token 承诺绝对零费用；真实计费以 DeepSeek 账单为准。
- `force_search=False` 只在 Python API 中可用；当前 CLI 总是走默认的强制搜索行为。
- 修改实现时保持公开 CLI、Python 返回类型和 JSON schema 向后兼容，除非用户明确要求破坏性变更。

## 修改与验证

1. 先复现问题，并确认影响的是 `client.py`、`config.py`、`cli.py` 还是打包元数据。
2. 协议问题优先保存脱敏后的事件类型和字段形状；禁止记录请求头或完整响应中的凭据。
3. 为纯解析逻辑使用离线事件样本。只有用户明确要求或确实需要端到端验证时才运行会访问 DeepSeek 的测试或 benchmark。
4. 至少运行语法检查、CLI `--help` 和 Skill 校验；有相关测试时再运行最小相关测试集。
5. 更新公开行为后同步 README、Skill reference 和版本信息，避免出现多个相互冲突的事实来源。

## 输出要求

- 搜索结果至少保留标题和 URL；有 `page_age` 时一并保留。
- 说明结果来自 DeepSeek 搜索工具，而不是模型生成的总结。
- 诊断结论区分本地已验证事实、远端响应事实和仍需真实凭据验证的假设。
- 给出的命令或 Python 示例必须可直接运行，并避免在命令历史中暴露 API Key。
