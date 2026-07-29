# 通用与医疗 Agent Harness 研究备忘录

> 检索日期：2026-07-28
> 检索方式：DeepXiv 快速检索 + 论文原文页与官方文档复核
> 用途：为 OphAgent-Pro 的后续架构、评测和迭代提供可复用依据。本文不使用 `harness-dev` 技能。

## 1. 结论

OphAgent-Pro 不应把“多 Agent”本身当成目标。更稳妥的设计是：

1. 以一个可审计、可恢复、预算受控的通用 harness 为底座；
2. Quick/Standard 默认使用单 Agent 或少量按需组件；
3. 仅在医疗复杂度、风险或多模态输入确实需要时，动态加入专科复核；
4. 红旗规则、引用核验、权限、预算和终态持久化由确定性运行时负责，不能只写在 prompt 中；
5. 评测必须覆盖交互轨迹、工具调用、恢复、成本、时延和安全，而不只看最终答案。

本轮实现将以上结论映射为：确定性路由、Quick/Standard/Deep 分层、医疗风险强制升级、按疾病选择亚专科、独立专科上下文、Critic 门禁、Manifest 约束、SQLite WAL 事件账本、预算预检和公开 SSE 事件。

## 2. 通用 Harness 研究

### 2.1 Natural-Language Agent Harnesses

[Natural-Language Agent Harnesses（arXiv:2603.25723）](https://arxiv.org/abs/2603.25723)把高层控制逻辑视为可移植、可编辑、可比较的执行产物，并强调显式契约、durable artifacts 和轻量适配器。

对项目的启示：

- Plugin Manifest 要成为真实执行契约，而不是只用于展示；
- 控制逻辑与具体模型提供商解耦；
- Run、Event、Artifact 要能持久化和复放；
- harness 变更应可单独评测和消融。

项目映射：

- `PluginManifest` 已增加 activation、latency budget、fallback、permission、required/optional nodes；
- planner 会拒绝清单外能力；
- provider 通过 OpenAI-compatible 接口适配，运行状态落入事务数据库。

### 2.2 From Model Scaling to System Scaling

[From Model Scaling to System Scaling: Scaling the Harness in Agentic AI（arXiv:2605.26112）](https://arxiv.org/abs/2605.26112)把 memory、context construction、skill routing、orchestration、verification 和 governance 视为共同决定 Agent 表现的系统层。

对项目的启示：

- 不能用“换更强模型”代替记忆卫生、上下文治理和动态路由；
- token、时延、验证成本与任务成功率应一起度量；
- memory 必须区分候选、确认、冲突、来源与敏感级别；
- skill 必须经过候选隔离、评测和 checksum 门禁。

项目映射：

- 长期记忆只有 confirmed 记录可进入临床上下文；
- Quick/Standard/Deep 分别使用 1/3/8 次模型调用预算；
- Skill 导入、验证、启停和治理审计已接入前端与后端；
- OpenTelemetry span 不记录患者原文，只记录 route、token、时长和状态。

### 2.3 AgentScope、OpenAI Agents SDK 与 LangGraph

- [AgentScope 官方文档](https://doc.agentscope.io/)覆盖 routing、handoff、并发 Agent、memory、Skill、Plan、RAG、tracing 和 evaluation；项目继续以 AgentScope 作为结构化医疗 Agent 的实现层。
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)把 Agent、handoff、guardrail、session、human-in-the-loop 和 tracing 作为少量核心原语。其经验支持“少量原语 + Python 显式编排”，也支持在昂贵调用前使用 blocking guardrail。
- [LangGraph Interrupts](https://langchain-ai.github.io/langgraph/concepts/breakpoints/)强调 checkpoint 后暂停并等待外部输入；这与本项目的 `waiting_for_user`、`run.question`、`/runs/{id}/input` 和恢复语义一致。

采用原则：

- 不为了框架统一而整体迁移；
- 复用其经过验证的设计原则：显式状态、checkpoint、输入/输出 guardrail、持久会话、公开事件与可恢复执行；
- 当前 AgentScope 负责 Agent/Tool/Skill，OphAgent runtime 负责状态机、预算、权限、事件和医疗安全。

## 3. 医疗 Agent 研究

### 3.1 MDAgents：按复杂度选择协作结构

[MDAgents（arXiv:2404.15155）](https://arxiv.org/abs/2404.15155)根据任务医疗复杂度选择 solo 或 group collaboration。论文报告其在十项评测中有七项表现最佳，并显示 moderator review 与外部医学知识的组合有明显收益。

采用：

- routine 简单任务不启用专科团队；
- HIGH/EMERGENCY 强制 Deep；
- Deep 根据关键词选择最多两个亚专科；
- 专科意见先进入 Critic，再进入最终回答。

不直接照搬：

- 不固定启动多 Agent；
- 不允许专科 Agent 共享可变 memory；
- 不以多数投票替代证据和安全规则。

### 3.2 AgentClinic：静态问答不足以代表临床 Agent

[AgentClinic（arXiv:2405.07960）](https://arxiv.org/abs/2405.07960)把患者交互、多模态信息收集、工具使用和不完整信息纳入模拟临床环境。其结果说明静态 QA 成绩不能直接代表连续临床决策能力。

采用：

- 多轮 Conversation 与 Run 分离但关联；
- 无影像的定位请求进入 `waiting_for_user`；
- 用户可在运行中补资料、恢复或取消；
- ClinicalState 明确保留未知项、未确认事实和 unresolved questions。

### 3.3 MedAgentBench 与 HealthAgentBench：评测真实工具轨迹

- [MedAgentBench（arXiv:2501.14654）](https://arxiv.org/abs/2501.14654)提供 FHIR-compatible 虚拟 EHR 环境和 300 个由医生编写的任务；其最佳模型成功率仍未饱和。
- [HealthAgentBench（arXiv:2606.31179）](https://arxiv.org/abs/2606.31179)覆盖患者旅程、多模态和端到端医疗工作流；论文报告前沿 Agent 的总体成功率仍较低，尤其是影像与大搜索空间组合推理。

采用：

- 后续评测增加工具正确性、轨迹质量、恢复、权限和成本；
- 影像任务必须验证真实坐标和输入类型；
- 不用最终文本“看起来合理”代替任务成功判定。

### 3.4 MAM 与 AgentRx：专科分工有价值，但朴素多 Agent 可能更差

- [MAM（arXiv:2506.19835）](https://arxiv.org/abs/2506.19835)使用全科、专科团队、影像、医疗助理和 Director 等角色，支持多模态专科协作。
- [AgentRx（arXiv:2605.10286）](https://arxiv.org/abs/2605.10286)的结论更谨慎：在其多模态临床预测任务中，单 Agent 优于朴素多 Agent，且校准更好。

综合决策：

- 专科 Agent 必须“按需、少量、隔离”，不能默认 fan-out；
- 最多选择两个相关亚专科；
- 专科输出限制长度，复用已经检索到的上下文；
- 只有复杂度或风险足够高时才支付额外 token 和时延；
- 后续必须以单 Agent 基线做消融，不假设多 Agent 天然更好。

## 4. OphAgent-Pro 目标 Harness

```text
用户输入
  ├─ 本地红旗门禁 ──> 立即 safety.alert
  ├─ 确定性 TaskRouter
  │    ├─ Quick ──> DirectAnswer（1 call）
  │    ├─ Standard ──> Clinical / Retrieval / Imaging 按需并行
  │    └─ Deep ──> 按需组件 + 1~2 个隔离专科复核
  ├─ HIGH / EMERGENCY ──> 候选稿 ──> Critic ──> 修订后终稿
  ├─ Answer 或 Report terminal
  └─ Citation validation / Artifact / durable Event
```

核心约束：

- `ClinicalState` 是医疗事实源；
- 用户上传、模型抽取和长期记忆都必须保留来源与确认状态；
- 公开进度只包含 `public_summary` 和结构化状态，不输出 hidden chain-of-thought；
- 引用不足时明确降级，不补造来源；
- capability 不可用时 fail closed 或 partial success；
- 终态事件 exactly-once，事件 sequence 单调递增；
- 患者文件不经 `/static` 暴露。

## 5. 性能、成本与安全策略

| 层级 | 最大模型调用 | token 预算 | 时间预算 | 医疗策略 |
|---|---:|---:|---:|---|
| Quick | 1 | 2,000 | 15 秒 | 先过本地红旗门，禁检索/报告 |
| Standard | 3 | 12,000 | 60 秒 | 按需并行组件，无默认专科团队 |
| Deep | 8 | min(32,000, 全局 24,000) | 300 秒 | 最多两个专科，高风险候选稿必须经 Critic 后修订 |
| Emergency 首屏 | 0 | 0 | 200 ms 目标 | 本地规则立即提示，不等待模型 |

进一步优化方向：

1. 为 provider 请求设置明确的 `max_output_tokens`；
2. 对重复证据和稳定知识增加安全缓存；
3. 以 TTFT、总耗时、模型调用、token、引用通过率和恢复成功率分层统计；
4. 对 specialist fan-out 做消融：0/1/2 专科；
5. 建立眼科医生评审集，评估红旗遗漏、过度确定、证据一致性和行动建议。

## 6. 2026-07-28 实装审计与语音供应商复核

本轮真实服务调用暴露出三类必须由 harness 兜底、不能只靠提示词的问题：

1. `mode=quick` 曾可覆盖红旗风险，使 `emergency` 直接进入单次模型回答。现改为风险门禁优先：只有 `routine` 才能进入 Quick。
2. Critic 原先位于最终生成之前，但没有候选答案可审。现改为 `draft → critic → answer/report`，终稿必须带入审稿意见重新生成。
3. Deep token 分层值曾可绕过全局 `RUN_MAX_TOKENS`。现所有创建、补充输入与恢复路径均受全局上限约束。

语音部分不能把所有厂商都假设成 OpenAI `/audio/*`。当前配置的阿里云模型分别使用 DashScope 原生协议：

- [Fun-ASR-Flash 官方 API](https://help.aliyun.com/en/model-studio/non-real-time-speech-recognition-for-fun-asr-flash)要求调用 `/api/v1/services/aigc/multimodal-generation/generation`，以 Base64 Data URI 传入录音；
- [Qwen3-TTS 官方 API](https://help.aliyun.com/en/model-studio/qwen-tts-api)使用同一 generation endpoint，返回短期音频 URL；系统只接受阿里云受信域名，并将文档示例中的 HTTP URL 强制升级为 HTTPS 后下载；
- Qwen3-TTS-Flash 单次输入上限为 600 字符，因此界面会清洗引用标记、按句切分为符合服务端限制的片段并顺序播放；用户停止后取消当前音频和剩余片段，文字终稿始终完整保留。

真实链路验证结果：

- TTS 返回 `audio/x-wav`，103,724 字节，24 kHz、16-bit、mono；
- 将该 WAV 再送入 ASR，成功还原“这是一段语音链路测试。”；
- 真实登录、创建会话、发送消息返回 202，Run 完成且 SSE 事件完整；
- 明确传 `mode=quick` 的清洁剂入眼案例仍被强制路由为 `emergency + deep`，计划节点为 `clinical → specialist → draft → critic → answer`。

## 7. 研究边界

- 2026 年论文较新，引用与复现成熟度有限，应视为研究方向而非临床有效性证明。
- benchmark 表现不能直接推导真实诊疗安全。
- 当前项目是本地研究原型，不是医疗器械，也不替代医生诊断、急诊评估或临床责任链。
- 所有医疗 Agent 设计都应经过本地数据治理、医生评审、前瞻性验证和合规审查后再考虑真实临床部署。
