# Offline Evolution

本模块包含两部分：`continuous.py` 在线记录去内容化结果与反馈，`harness.py` 离线负责候选隔离、不可变评测记录、确定性配对门禁、人工审批、release ref 与回滚。

在线环节不保存 query、answer、附件、证据正文、用户 ID 或临床字段。它只允许对重复获得正反馈的、已经确认的非临床偏好做默认最高 +15% 的 Bayesian-smoothed 召回增益；临床病史、用药和过敏不按粗粒度回答反馈重排，负反馈也不会降低任何 Memory 的权重。系统不能自动确认、改写、删除或屏蔽医疗事实。重复 Skill 负反馈、Memory 候选拒绝、召回负反馈和技术错误只会生成 `ready_for_offline_evaluation` 候选，不会在线改写代码、Prompt 或 `SKILL.md`。

离线候选必须声明失败簇、修改白名单、预期行为、风险和激活条件。每个候选使用独立 Git worktree；`tests/`、凭据、审计、sealed data、发布门禁、认证和可观测性均禁止修改。晋升只接受同病例配对的 sealed-test 结果，并检查 95% 置信区间、普通/复杂/高风险全切片非劣、已通过单病例不失败、高风险单病例不降分、Token 与延迟。

Acceptance/sealed 之前先调用 `freeze_candidate` 将白名单修改固定为 commit。结果必须绑定 baseline commit 或候选 HEAD，并由候选进程之外的可信评测控制器使用 `EVOLUTION_GATE_SECRET` 或仅控制器可读的 `EVOLUTION_GATE_SECRET_FILE` 生成 HMAC attestation；生产候选环境不得继承该 secret。晋升只读取已落盘且重新验签的 baseline/candidate 结果，拒绝调用参数临时注入的分数或评测后的未提交修改。默认还必须调用 `approve`，人工审批记录同样验签并绑定当前 candidate commit。

只有成功晋升后，系统才把“失败簇 + 通用策略 + release + 门禁指标”追加到离线 experience memory。该存储不进入患者运行时，也拒绝明显的电话、身份证、邮箱和患者姓名字段；不会保存可复制到其他患者的诊断答案。

sealed-test 必须位于仓库与候选 worktree 之外，并提供 `manifest.json` 与 JSONL 病例文件。控制器会强制校验未复用历史输出、完整病例集合、普通/复杂/高风险切片计数、强制指标以及候选不可访问策略；空目录不再被视为已配置。

生成器仅连接官方实现：

- [A-Evolve](https://github.com/A-EVO-Lab/a-evolve)，可选依赖 `a-evolve==0.1.0`
- [GEPA](https://github.com/gepa-ai/gepa)，可选依赖 `gepa==0.1.1`
- [Adaptive Auto-Harness](https://github.com/A-EVO-Lab/a-evolve/tree/release/adaptive-auto-harness)，通过独立 release branch 配置

本机可用 `scripts/install_official_evolution.sh` 从 `medical_agent_hust/evolution/upstream` 的固定官方源码安装；未安装时状态为 `unavailable`，不会启用同名简化优化器。可选依赖见 `requirements-evolution.txt`。

设计与研究依据见 [`docs/SELF_EVOLUTION_HARNESS_RESEARCH.md`](../../docs/SELF_EVOLUTION_HARNESS_RESEARCH.md)。
