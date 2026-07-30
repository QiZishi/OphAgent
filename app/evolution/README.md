# Offline Evolution

本模块包含两部分：`continuous.py` 在线记录去内容化结果与反馈，`harness.py` 离线负责候选隔离、不可变评测记录、确定性配对门禁、人工审批、release ref 与回滚。`tracks.py` 将偏好/策略类更新与安全、业务和 Harness 控制面分轨；混轨候选直接拒绝，不可变轨即使关闭普通候选审批也必须经过可信人工审批。

`config/immutable/harness_component_contracts.yaml` 定义每个 Harness 组件“是什么、必须做什么、哪些状态允许在线变化”。sealed suite 必须绑定该 contract set 和 schema；组件的身份、职责、权限、输入输出语义和失效保护属于不可变核心，候选即使总分更高，只要 `component_contract_passed` 未通过也禁止晋升。仓库内置 Skill 定义属于核心实现并走离线轨，运行时隔离区中的已验证低风险 Skill 生命周期与选择效用可以在线变化，危险能力仍需离线人工审核。

在线环节不保存 query、answer、附件、证据正文、用户 ID 或临床字段。用户明确表达的偏好/工作区 Memory 可在线新增、更新、删除和过期清理，其效用随显式反馈在有界范围内双向调整；已验证低风险 Skill 同样在线调整选择效用。临床病史、用药和过敏不按粗粒度回答反馈重排，也不能由模型自动确认或删除。Memory CRUD、来源、确认、冲突、临床保护与用户纠正能力属于不可变机制；Skill 内容、工具权限和高风险激活也不能在线改写，相关变更只生成 `ready_for_offline_evaluation` 候选。

离线候选必须声明失败簇、修改白名单、预期行为、风险和激活条件。每个候选使用独立 Git worktree；`tests/`、凭据、审计、sealed data、发布门禁、认证和可观测性均禁止修改。晋升只接受同病例配对的 sealed-test 结果，并检查 95% 置信区间、普通/复杂/高风险全切片非劣、已通过单病例不失败、高风险单病例不降分、Token 与延迟。

Acceptance/sealed 之前先调用 `freeze_candidate` 将白名单修改固定为 commit。结果必须绑定 baseline commit 或候选 HEAD，并由候选进程之外的可信评测控制器使用 `EVOLUTION_GATE_SECRET` 或仅控制器可读的 `EVOLUTION_GATE_SECRET_FILE` 生成 HMAC attestation；生产候选环境不得继承该 secret。晋升只读取已落盘且重新验签的 baseline/candidate 结果，拒绝调用参数临时注入的分数或评测后的未提交修改。默认还必须调用 `approve`，人工审批记录同样验签并绑定当前 candidate commit。

只有成功晋升后，系统才把“失败簇 + 通用策略 + release + 门禁指标”追加到离线 experience memory。该存储不进入患者运行时，也拒绝明显的电话、身份证、邮箱和患者姓名字段；不会保存可复制到其他患者的诊断答案。

sealed-test 必须位于仓库与候选 worktree 之外，并提供 `manifest.json` 与 JSONL 病例文件。控制器会强制校验未复用历史输出、完整病例集合、普通/复杂/高风险切片计数、强制指标以及候选不可访问策略；空目录不再被视为已配置。

生成器仅连接官方实现：

- [A-Evolve](https://github.com/A-EVO-Lab/a-evolve)，可选依赖 `a-evolve==0.1.0`
- [GEPA](https://github.com/gepa-ai/gepa)，可选依赖 `gepa==0.1.1`
- [Adaptive Auto-Harness](https://github.com/A-EVO-Lab/a-evolve/tree/release/adaptive-auto-harness)，通过独立 release branch 配置

本机可用 `scripts/install_official_evolution.sh` 从 `medical_agent_hust/evolution/upstream` 的固定官方源码安装；未安装时状态为 `unavailable`，不会启用同名简化优化器。可选依赖见 `requirements-evolution.txt`。

双轨边界以 `tracks.py`、不可变策略清单和回归测试为准；本地研究文档不进入 Git 仓库。

## 其他 Agent 系统如何检查双轨隔离

先为 Memory、Skill、Prompt、Tool、Router、Safety、Knowledge 和 Orchestrator 分别写出四项契约：组件定义、核心作用、允许在线变化的数据、禁止在线变化的机制。若只按文件路径分轨，却没有组件契约，仍可能让“可变策略代码”绕过不可变规则。

检查时至少确认：

1. 在线写入口是否只接受有 schema、来源、版本和所有者的低权限数据，而不能写 system prompt、安全规则、业务红线、工具权限或执行代码。
2. Memory 是否支持正常 CRUD、纠正、冲突和删除，同时永远不能提升为系统指令；禁止把 Memory 变成只读，否则组件也会失去核心作用。
3. 内置 Knowledge 与 Skill 是否默认可信可用；用户新导入内容才执行风险扫描。发现风险时向用户说明并允许显式强制加载，但运行时不可变安全边界仍拥有更高优先级。
4. 候选是否按 `mutable / immutable / mixed` 分类；`mixed` 不能拆掉不可变部分后偷偷上线，必须整体进入离线隔离评测。
5. 不可变候选是否绑定 sealed cases、候选 commit、评测器版本和可信人工审批；候选进程不能访问签名密钥，也不能自己提交分数。
6. 发布是否具有原子激活、审计和回滚路径；“创建 Git ref”不能冒充已经完成运行时发布。
7. 是否有负向测试证明 Memory/Skill 内容无法改写红旗、引用真实性、业务规则、认证、权限和工具边界。

本项目的检查入口：

```bash
python -m pytest tests/test_dual_track_governance.py \
  tests/test_online_memory_and_skill_evolution.py \
  tests/test_evolution.py
```

实现双轨时应先把核心契约放入独立、默认拒绝在线修改的 manifest，再让所有在线写入口统一调用同一个分类器和策略门。可变轨只存储记录、声明式偏好、有界权重和经验证的低风险状态；Python/TypeScript 等可执行代码、系统提示、安全/业务规则、Tool 权限与发布控制面一律进入不可变轨。任何组件优化都必须同时验证“性能变好”和“核心定义没有被改废”。
