# 多轮上下文、压缩缓存与记忆 Harness 调研及落地

更新日期：2026-07-29

## 1. 自查结论

改造前的前端会把同一 Conversation 下的多个 Run 连续展示，但后端生成下一轮时只使用 `run.input.query`。因此它在数据与界面层面是多轮，在模型上下文层面仍是单轮。另一个相反的问题是：同一 Run 内复用同角色 AgentScope Agent 时，`InMemoryMemory` 会隐式保留此前的 prompt 和回答；高风险任务的候选稿、复核、最终稿可能重复携带大块上下文。

长期记忆原实现已有用户隔离、确认门禁、过期时间、去重和冲突标记，但存在两个缺口：

- 会话内历史回答、长期用户事实和 Agent 程序性知识没有明确分层；
- 两条互相冲突且都被确认的医疗记忆仍可能同时进入 prompt，让模型自行猜测。

## 2. 主流实现的共同方向

### 2.1 短期状态与长期记忆分离

LangGraph 将 thread-scoped short-term memory 放在 checkpoint state，将跨线程 long-term memory 放在 store，并把长期记忆区分为 semantic、episodic、procedural。长历史即使尚未超过模型窗口，也会降低质量、增加成本，所以需要 trim 或 summarize，而不是把全部消息长期回放。

参考：

- [LangGraph Memory overview](https://docs.langchain.com/oss/python/concepts/memory)
- [LangGraph Add memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

AgentScope 的基础 Memory 支持 message mark、过滤和 compressed summary，但压缩策略仍应由 Agent/harness 控制；长期记忆则可选择静态控制或 Agent 控制。医疗场景不能把“Agent 自己认为值得记住”直接等同于患者事实，因此本项目继续采用静态门禁：模型只能提出候选，用户确认后才能进入可检索长期记忆。

参考：

- [AgentScope Basic memory](https://doc.agentscope.io/tutorial/task_memory.html)
- [AgentScope Long-term memory](https://doc.agentscope.io/tutorial/task_long_term_memory.html)

### 2.2 Session compaction 与服务端 conversation 只能选清晰的一条状态链

OpenAI Agents SDK 的 Sessions 会自动读取历史并在 Run 后写回；`OpenAIResponsesCompactionSession` 可在阈值后自动压缩，也支持在流式输出空闲阶段手动 compact。官方同时提醒，不应把本地 session history 与 `conversation_id` / `previous_response_id` 等服务端状态延续机制混用，否则会重复历史。

本项目必须兼容任意 OpenAI 协议供应商，不能依赖某一家服务端保存状态，因此采用本地持久化 snapshot，并将每次模型请求视为 stateless。

参考：

- [OpenAI Agents SDK Sessions](https://openai.github.io/openai-agents-python/sessions/)
- [OpenAI Agents SDK Models and context management](https://openai.github.io/openai-agents-python/models/)
- [OpenAI Agents SDK Context management](https://openai.github.io/openai-agents-python/context/)
- [OpenAI Conversations API](https://platform.openai.com/docs/api-reference/conversations)

### 2.3 Prompt cache 不等于上下文压缩

Anthropic 将四种机制分开说明：tool search 减少预载工具定义，programmatic tool calling 减少回合，prompt caching 降低重复前缀成本，context editing 则真正移除旧 tool result。Prompt caching 不会减少上下文 token；频繁截断最旧消息还会破坏前缀缓存。

本项目因此遵循：

- system prompt、工具 schema、固定安全原则放在稳定前缀；
- 时间、用户问题、会话历史、检索结果放在动态后缀；
- 不把 provider 特有的 cache 参数强塞给第三方 OpenAI-compatible 服务；
- 用本地 `source_hash` 缓存压缩结果，但 token 上限仍由代码实际约束。

参考：

- [Anthropic Manage tool context](https://platform.claude.com/docs/en/agents-and-tools/tool-use/manage-tool-context)
- [Anthropic Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [OpenAI API data controls and retention](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)

## 3. 本项目采用的上下文模型

### 3.1 Thread-scoped conversation snapshot

每个新 Run 在开始前，从同一 `user_id + conversation_id` 读取已完成 Run：

1. 重新生成链只保留最新有效版本；重试时排除正在替换的回答及其祖先版本。
2. 最近若干轮保留用户与助手原文。
3. 较早轮次由代码抽取用户任务和回答前部的关键段落，不额外调用模型。
4. 所有历史助手内容明确标注“待核验”，不能自动写入 `ClinicalState`。
5. 历史用户陈述另生成 clinical view，供结构化抽取使用，避免把旧助手诊断混进事实抽取。
6. snapshot 随 Run 持久化；服务重启恢复时继续使用同一份 snapshot。

Run 只公开不含患者原文的统计量：来源轮数、原文保留轮数、压缩轮数、压缩前后 token 和 cache hit。完整 snapshot 只存于运行时数据库，并受 Run 所有权与会话删除级联约束。

### 3.2 代码负责预算，模型负责工作

没有要求模型计算字数、反复校验长度或输出固定字数。Harness 使用 tokenizer 在送入模型前完成：

- 会话历史预算；
- 节点输入预算；
- 证据片段预算；
- 最终输出预留预算；
- 实际 token 超预算后的“保留已生成正文、停止追加调用”策略。

这避免把长度管理变成模型的推理负担，也避免因为后处理超预算丢弃已生成正文。

### 3.3 医疗记忆分层

| 层 | 内容 | 写入方式 | 注入规则 |
|---|---|---|---|
| Short-term / episodic | 当前 Conversation 的用户问答、附件关系、Run 结果 | 运行时自动持久化 | 仅同一用户、同一会话；旧助手回答标为待核验 |
| Long-term semantic | 用户偏好、病史、用药、过敏、随访信息 | 模型只可提议，用户确认后生效 | 按任务与类别检索；过期、restricted 或双确认冲突内容不注入 |
| Procedural | Skill、工具、固定诊疗流程 | 经过校验的 Skill registry | 按 Agent 角色、能力和插件选择，不与患者记忆混存 |
| ClinicalState | 本次任务可追踪的临床事实和未知项 | 只从用户输入与可信工具结果结构化写入 | 诊断候选不会变成长期事实；跨轮继承仍保留 confirmed/source |

### 3.4 冲突与安全

相同 `key` 的不同内容会互相标记冲突。若冲突双方都处于 confirmed 状态，检索层将两者都暂时扣留，直到用户明确纠正或拒绝其中一条。系统不把冲突判断外包给模型。

## 4. 已落地文件

- `app/runtime/context.py`：会话版本选择、抽取式压缩、临床视图和 snapshot cache。
- `app/runtime/store.py`：会话 Run 查询与 `runtime_context_snapshots` 持久化。
- `app/runtime/orchestrator.py`：上下文准备、恢复、角色级注入、ClinicalState 衔接和记忆召回事件。
- `app/runtime/routing.py`：省略式追问识别及上一轮任务类型衔接。
- `app/runtime/agents.py`：每次显式请求前清空 AgentScope 隐式 chat memory，避免重复上下文。
- `app/services/state.py`：冲突确认记忆扣留与类别相关召回。

## 5. 后续可演进方向

- 当可用供应商明确支持 Responses API 时，可增加 provider capability negotiation，再选择 server-side compaction；不得与本地 session 重复启用。
- 当会话达到数百轮时，可把抽取式旧摘要升级为异步、可校验的结构化摘要任务；原始 Run 仍保留以便重建。
- Embedding 记忆检索只应作为召回候选，最终仍需 category、状态、冲突、时效和用户权限过滤。
- 为 context token、压缩比例、cache hit、被扣留冲突记忆建立仪表盘，但可观测性不得记录患者原文。
