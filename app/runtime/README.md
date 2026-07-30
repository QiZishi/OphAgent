# Runtime

运行时实现可恢复任务、DAG 执行、预算、事件流与 AgentScope Agent 构建。运行记录、节点状态、上下文 snapshot、事件和 artifact 持久化在 SQLite WAL；生产多副本部署前仍需替换为共享事务数据库与消息总线。

任何外部服务失败都必须生成结构化错误事件，不得生成预设医学结论。

运行时检索已确认长期记忆时只把它作为带来源参考，不能绕过 `ClinicalState` 自动成为事实。模型、Agent 和节点 span 只记录标识、状态、耗时与 token 聚合，不记录 prompt 或患者原文。

同一 Conversation 的多轮历史由 `ConversationContextManager` 形成持久化 snapshot：最近轮次保留、旧轮次抽取式压缩，历史助手回答始终标为待核验。AgentScope 的隐式对话 memory 在每次显式调用前清空，避免候选稿与最终稿重复携带旧 prompt。

## 执行上下文与恢复契约

- `ExecutionContextManager` 只向节点传递其 DAG 依赖祖先的已完成输出，不传无关并行节点，也不传失败节点的未验证正文。
- 上下文预计达到节点 token 上限的 82% 时，在调用模型前执行确定性压缩。压缩优先保留红旗、用药、过敏、未决问题、证据 ID/来源/定位和影像坐标；checkpoint 只保存来源节点、hash 和 token 统计，不重复保存患者正文。
- 安全或引用后处理异常先在同一原始输出上重试；仍失败才回滚终端节点并重新生成。重生成 prompt 必须包含结构化失败阶段、问题代码和可执行修正要求。
- 用户取消或进程中断后，resume 保留未受影响的 completed 节点，只重开 pending/failed/cancelled 节点及其下游。恢复时重新计算依赖上下文 hash；一致则从原检查点继续，不一致则重建上下文。
- 对外只发布通过安全、引用和结构校验的 `answer.delta`。失败尝试、内部 prompt、异常正文和隐藏推理不进入公开事件。
