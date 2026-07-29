# 官方演化组件与 sealed-test 安装记录

## 本机配置

- 安装目标：项目虚拟环境 `venv`
- 安装来源：`/Users/qizs/conclusion/medical_agent_hust/evolution/upstream`
- A-Evolve：`0.1.0`，上游 commit `4f6462487e5644fc762ab78225f4124dbe6d1247`
- GEPA：`0.1.1`，上游 commit `8b50db550221415dc982fac2a03c7543ea0e83d6`
- provenance：来源项目的 `evolution/upstream/SOURCE_MANIFEST.yaml`
- 可复现命令：`./scripts/install_official_evolution.sh`

系统没有复制或替换这两个官方包，也不会在缺包时启用本地同名简化器。`requirements-evolution.txt` 仅记录兼容版本；本机以固定源码和 provenance manifest 为准。

## sealed-test

独立眼科测试套件存放在仓库和候选 worktree 之外的控制器私有目录，真实位置只记录在被 Git 忽略的本地 `.env` 中。

来源项目没有可直接安装且允许复用的 sealed truth 数据；其中历史 `outputs` / `outputs_new` 也被其协议明确禁止复用。因此，本机依据 `medical_agent_hust` 的 `medical_harness/holdout_protocol.py`、Harness 设计文档和评估协议新建了 12 个合成、无患者隐私病例：普通、复杂、高风险各 4 例，没有读取或复制历史评测答案。

本地 `.env` 使用 `EVOLUTION_SEALED_TEST_DIR` 指向该外部目录。晋升控制器会校验：

- manifest 明确声明 `status=sealed` 且未复用历史输出；
- JSONL 病例 ID 唯一、总数和切片计数一致；
- baseline 与 candidate 覆盖完全相同的整套病例；
- 医疗安全、引用、关键错误、Token 和延迟指标齐全；
- 候选不可访问 sealed 数据，且高风险病例和各切片不允许退化。

HMAC 门禁密钥保存在被 Git 忽略的 `data/evolution/gate_secret`，本机权限为 `0600`。候选 worktree 不包含该文件，也不会继承密钥环境变量。
