# 自进化 Agent Harness：研究依据、边界与 OphAgent-Pro 实施

更新日期：2026-07-29

## 结论

OphAgent-Pro 不采用“模型在生产环境中根据几次反馈直接改 prompt、Skill 或代码”的做法。医疗场景中的合理闭环是：

1. 在线运行只采集去内容化质量信号；只有重复获得正反馈的已确认非临床偏好允许获得极小、可撤销的召回增益。
2. 重复失败形成失败簇和改进候选，不直接成为生产变更。
3. 候选在隔离 Git worktree 中生成和冻结。
4. 使用相同病例进行 baseline/candidate 配对评测；普通、复杂、高风险切片均不得退化，高风险单病例也不得降分。
5. 同时检查医疗安全、引用、任务完成度、Token、延迟和运行可靠性。
6. sealed test 结果由候选进程之外的可信控制器签名；通过后仍需人工审批，且审批绑定候选 commit。
7. 发布形成可审计 release；出现线上退化时只能回滚到已冻结 release。

这是一种“持续发现问题、持续产生候选、谨慎晋升”的受控进化，而不是无边界在线自修改。

## 主流方案共同结构

### 线上监测与离线评测必须分离

LangSmith 的官方评测文档把生产 trace 的 online evaluation 与基于固定数据集的 offline evaluation 明确分开：线上评测用于发现异常、质量模式与真实失败；失败 trace 再进入离线数据集，修复必须通过离线实验后重新部署。其 Engine 工作流进一步采用“重复失败检测 → 根因 → 修复候选 → 新 evaluator → 回归数据”的闭环。

- [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation)
- [Evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- [LangSmith Engine](https://docs.langchain.com/langsmith/engine)

OpenAI AgentKit 同样把 datasets、trace grading、grader 与 prompt optimization 组合为“先测量、再优化”的链路，而不是把线上反馈直接当作生产 prompt。参见 [Introducing AgentKit](https://openai.com/index/introducing-agentkit/)。

### 优化器需要显式 metric 与固定训练/验证数据

DSPy/GEPA 的官方接口要求开发者提供 trainset 和 scoring metric，再编译得到一个独立优化结果。这说明优化方向必须由可测量目标约束；不能仅使用点赞率这一个容易被短答案、迎合表达或分布偏差污染的指标。参见 [DSPy](https://dspy.ai/)。

### Skill 应当是有生命周期、可测试的资产

MUSE-Autoskill 把 Skill 作为长期资产，包含创建、记忆、管理、评测和迭代；EvoSkills 则强调 Skill 生成器之外还需要独立 verifier。两者共同支持“候选 + 验证”，不支持未经验证覆盖已启用 Skill。

- [MUSE-Autoskill](https://arxiv.org/abs/2605.27366)
- [EvoSkills](https://arxiv.org/abs/2604.01687)

### 医疗经验复用必须以效用和治理为核心

SkeMex 针对医疗 agent 提出基于环境反馈估计上下文相关效用，并通过 Read–Write–Assess–Govern 生命周期管理 Skill memory。它的关键启发不是“保存更多原始轨迹”，而是保留紧凑、可迁移、可治理的程序性经验。参见 [Experience Makes Skillful / SkeMex](https://arxiv.org/abs/2606.09365)。

MemSkill 也把 memory 写入、合并和剪枝视为可演化操作，并通过 hard cases 驱动 designer 提出改进；这支持把“用户拒绝了某类 memory 候选”聚合为 extraction-policy 候选，但不支持自动修改患者事实。参见 [MemSkill](https://arxiv.org/abs/2602.02474)。

### 安全评测本身也要持续演进

SafeEvalAgent 的实验显示，静态安全基准可能高估模型安全性，随着测试生成变难，暴露出的安全率会明显下降。因此 sealed 高风险集不应固定停滞，应由可信评测侧扩展 adversarial cases，但候选工作区不能读取这些用例。参见 [SafeEvalAgent](https://arxiv.org/abs/2509.26100)。

## OphAgent-Pro 的实现映射

| 环节 | 当前实现 | 防负优化边界 |
|---|---|---|
| 信号采集 | `ContinuousEvolutionController` 记录运行状态、错误码、插件/Skill ID、点赞/点踩和 memory 类别 | 不保存 query、answer、附件、证据正文、用户 ID 或临床字段 |
| Memory 效用 | 依据使用该 preference/workspace memory 的回答反馈，做 Bayesian smoothing 后的正向增益 | 需要最小样本且正反馈率达标；默认最高 +15%；临床病史、用药、过敏不参与；负反馈不降权；不能确认、改写、删除或屏蔽事实 |
| Memory 改进候选 | 重复拒绝某类候选或召回后重复负反馈，形成 extraction/retrieval 候选 | 候选只包含类别和聚合指标，不包含患者内容 |
| Skill 改进候选 | Skill 关联回答达到最小样本与负反馈率阈值后入队 | 线上不改 `SKILL.md`、不自动禁用；只能进入离线候选 |
| 技术失败候选 | 相同错误码重复出现后形成 runtime 候选 | 只允许白名单路径，禁止修改 tests、auth、db、evolution、observability、sealed data |
| 离线接续 | `create_from_continuous_candidate` 把候选转换为正式 `EvolutionProposal` | 只创建元数据；不会自动隔离、生成、评测、审批或晋升 |
| 隔离 | 每个候选单独 Git worktree 并冻结 commit | 候选不能接触 gate secret、sealed tests 和晋升代码 |
| 评测 | baseline/candidate 同病例配对；HMAC attestation | 结果必须绑定 baseline commit 或冻结后的 candidate HEAD |
| 非劣门禁 | 平均提升、95% CI、全切片、单病例通过状态、高风险单病例、Token、延迟 | 任一已通过病例变失败、任一切片回归或高风险病例降分均拒绝 |
| 审批与回滚 | 人工审批记录签名并绑定 candidate commit；release ref 冻结 | 不允许评测后改代码；只能回滚到冻结 release |

## 指标设计

点赞/点踩只是弱信号，不能单独成为晋升奖励。候选评测至少应组合：

- 任务完成：结构化字段完整度、插件输入输出契约、引用覆盖率、工具调用正确率。
- 医疗质量：事实一致性、证据质量、不确定性校准、红旗召回、危险建议率。
- 鲁棒性：普通、复杂、高风险、缺失输入、冲突病史、对抗提示、跨轮上下文。
- 系统效率：成功率、首次输出时间、总延迟、模型调用数、输入/输出 Token。
- 人因结果：用户反馈、修订率、重新生成率、停止率；只用于发现问题和构造候选。

## 尚需外部资源才能完成的部分

项目已经具备候选发现、隔离、评测认证、非劣门禁、审批和回滚代码。真正晋升一个医疗候选仍需要配置：

- 独立且候选不可见的 `EVOLUTION_SEALED_TEST_DIR`；
- `EVOLUTION_GATE_SECRET`；
- 有资质人员维护的眼科高风险病例与评分 rubric；
- 可选的官方 A-Evolve、GEPA 或 Adaptive Auto-Harness 生成器。

缺少这些资源时，系统会继续记录信号并生成候选，但必须保持 `ready_for_offline_evaluation`，不得假装已完成安全晋升。
