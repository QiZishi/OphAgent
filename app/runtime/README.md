# Runtime

运行时实现可恢复任务、DAG 执行、预算、事件流与 AgentScope Agent 构建。运行记录和事件以原子 JSON/JSONL 方式持久化；这是一阶段实现，生产多副本部署前需替换为事务数据库与消息总线。

任何外部服务失败都必须生成结构化错误事件，不得生成预设医学结论。

运行时检索已确认长期记忆时只把它作为带来源参考，不能绕过 `ClinicalState` 自动成为事实。模型、Agent 和节点 span 只记录标识、状态、耗时与 token 聚合，不记录 prompt 或患者原文。

同一 Conversation 的多轮历史由 `ConversationContextManager` 形成持久化 snapshot：最近轮次保留、旧轮次抽取式压缩，历史助手回答始终标为待核验。AgentScope 的隐式对话 memory 在每次显式调用前清空，避免候选稿与最终稿重复携带旧 prompt。
