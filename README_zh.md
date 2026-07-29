<p align="center">
  <img src="figures/system_logo.png" width="120" alt="OphAgent 系统 Logo">
</p>

<h1 align="center">OphAgent · “灵瞳”眼科智慧诊疗系统</h1>

<p align="center"><strong>可持久化、带安全门禁、支持流式响应的眼科 Agent 工作台</strong></p>

<p align="center">
  <a href="README.md">English</a> · <a href="README_zh.md">简体中文</a>
</p>

<p align="center">
  <a href="https://qizishi.github.io/OphVLM-R1/"><img src="https://img.shields.io/badge/项目-主页-2b6cb0?style=for-the-badge" alt="项目主页"></a>
  <a href="https://github.com/QiZishi/OphAgent/"><img src="https://img.shields.io/badge/代码-OphAgent-181717?style=for-the-badge&logo=github" alt="OphAgent 代码"></a>
</p>
<p align="center">
  <a href="https://huggingface.co/QiZishi/OphVLM-R1"><img src="https://img.shields.io/badge/🤗%20模型-Hugging%20Face-FFD21E?style=for-the-badge" alt="Hugging Face 模型"></a>
  <a href="https://www.modelscope.cn/models/MoonNight/OphVLM-R1"><img src="https://img.shields.io/badge/模型-ModelScope-624AFF?style=for-the-badge" alt="ModelScope 模型"></a>
</p>
<p align="center">
  <a href="https://huggingface.co/datasets/QiZishi/OphReason-Vision"><img src="https://img.shields.io/badge/🤗%20数据集-Hugging%20Face-FFD21E?style=for-the-badge" alt="Hugging Face 数据集"></a>
  <a href="https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision"><img src="https://img.shields.io/badge/数据集-ModelScope-624AFF?style=for-the-badge" alt="ModelScope 数据集"></a>
</p>

## 项目链接汇总

- **项目主页**：<https://qizishi.github.io/OphVLM-R1/>
- **OphAgent 系统代码**：[GitHub](https://github.com/QiZishi/OphAgent/)
- **OphVLM-R1 模型**：[Hugging Face](https://huggingface.co/QiZishi/OphVLM-R1) | [ModelScope](https://www.modelscope.cn/models/MoonNight/OphVLM-R1)
- **OphReason-Vision 数据集**：[Hugging Face](https://huggingface.co/datasets/QiZishi/OphReason-Vision) | [ModelScope](https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision)

## 新闻动态

- **2026.07.07** 🎉 论文 “OphVLM-R1: Efficient Ophthalmic Reasoning via Curriculum Reinforcement Learning” 被 **WAICA 2026** 接收！
  - 📖 会议官网：<https://waica2026.worldaic.com.cn/>

- **2025.12.09** 🎉 **重磅喜讯！** “灵瞳”眼科智慧诊疗系统获得上海人工智能实验室大力宣传推荐，并荣获**书生大模型实战营优秀项目**荣誉！衷心感谢上海人工智能实验室与书生大模型实战营的认可与支持！
  - 📖 宣传文章：<https://mp.weixin.qq.com/s/BTZPUrVtD8nCS_yMwDhhUQ>

- **2025.11.28** 📊 高质量眼科多模态推理数据集 **OphReason-Vision** 部分子集已在 ModelScope 平台正式开源发布！
  - 🔗 数据集链接：<https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision>

- **2025.11.23** 🎬 “灵瞳”眼科智慧诊疗系统初代五入口版本实机演示视频在 B 站发布。当前 OphAgent 已在此基础上完成全面架构重构。
  - 🎥 视频链接：<https://www.bilibili.com/video/BV1g4UTBZEEm/>

## 项目背景

**“灵瞳”眼科智慧诊疗系统**是基于自主研发的 **OphVLM-R1 眼科多模态推理模型**构建的专业化医疗 AI 平台。该项目由华中科技大学人工智能与自动化学院人工智能安全实验室团队开发，旨在缓解全球眼科优质医疗资源分布不均，以及基层医疗机构误诊、漏诊率较高等现实问题。

眼科多模态大语言模型面临三大挑战：训练数据缺乏结构化推理链、单阶段训练难以培养深度临床推理能力，以及模型规模过大制约资源受限环境中的部署。项目通过一体化的“数据—模型—智能体”技术栈解决这些问题：OphReason-Vision 将异构眼科数据转化为经过专家验证的推理轨迹；OphVLM-R1 通过 LoRA 冷启动和课程强化学习获得临床推理能力；OphAgent 则通过可持久化临床辅助运行时统一调度模型、检索与专科能力。

当前 OphAgent 结合 **AgentScope ReAct 智能体**、确定性医疗安全门禁、类型化 DAG 规划、多模态工具与带来源治理的知识检索。系统对外提供病灶定位、辅助评估和报告生成三个专业插件；对话、证据检索、文档解析、语音和记忆则作为核心能力统一编排。界面只呈现公开执行摘要，不展示隐藏 Chain-of-Thought。

**核心目标：**通过 AI 技术赋能临床医生，尤其是基层医疗工作者，提升眼科疾病的早期筛查与精准诊断能力。“灵瞳”目前定位为研究与临床辅助系统，不能替代专业医疗判断。

## OphReason-Vision 数据集流水线

三阶段闭环流水线将 100K+ 原始临床案例和 30+ 公开数据集转化为 15,418 条推理轨迹。

![OphReason-Vision 数据流水线](figures/data_pipeline.png)

### 1. 数据标准化

该阶段以双流策略整合 100K+ 临床案例与 30+ 公开数据集。**文本流**将非结构化电子病历解析为标准化 JSON，并通过人工整理的眼科同义词表解决术语不一致问题。**视觉流**为仅包含图像级标签的数据生成详细文本描述，补充后续推理合成所需的视觉证据。

### 2. 结构化推理合成

Intern-S1 生成覆盖病灶定位、多模态诊断和知识问答的多维指令，并为每条指令依照临床诊断工作流构建 Chain-of-Thought：

> 视觉体征识别 → 知识检索 → 病理分析 → 临床决策

质量控制采用基于 Intern-S1 的 LVLM-as-a-Judge，阈值 $\tau=0.7$ 由 500 条专家审核的试点样本确定，以最大化 F1。评判维度包括医学正确性、推理一致性、步骤完整性和清晰度，并识别虚构影像发现、疾病分类错误和逻辑不一致等问题。

### 3. 专家协作优化

三名认证眼科医生审核被标记为困难的 18% 样本，评估者间一致性达到 Cohen's $\kappa=0.82$，分歧通过讨论解决直至达成共识。样本难度依据基座模型困惑度划分，使训练课程能够从较简单的视觉感知逐步过渡到长文本临床推理。数据同时通过感知哈希、来源标识符交叉比对和人工来源审计降低与外部评测基准的数据污染风险。

| 划分 | 记录数 | 用途 |
|---|---:|---|
| 冷启动 SFT | 3,418 | 注入领域知识 |
| 四个课程阶段 | 10,000 | 渐进式推理训练 |
| 域内评估 | 2,000 | 留出临床评估 |
| **总计** | **15,418** | **训练 13,418 + 评估 2,000** |

## OphVLM-R1 模型训练框架与算法

OphVLM-R1 是以 InternVL3.5-2B 为基座的 2B 参数模型。其轻量化规模兼顾消费级 GPU 部署与多模态临床推理能力。整体训练分为两个阶段：第一阶段通过参数高效监督微调注入眼科领域知识，第二阶段通过课程强化学习逐步培养诊断推理能力。

![OphVLM-R1 两阶段训练框架](figures/two_stage_training.png)

### 阶段一：LoRA 监督微调

使用 3,418 条冷启动样本，通过 Low-Rank Adaptation（LoRA）注入广泛的眼科领域知识，并将权重更新约束为低秩分解。适配器在 $W_q$、$W_k$、$W_v$ 和 $W_o$ 注意力投影上使用 rank $r=64$、scaling $\alpha=128$；学习率从 $1\times10^{-4}$ 开始并采用余弦退火，批次大小为 32，共训练 3 epochs，可训练参数约占总参数的 0.5%。

### 阶段二：课程强化学习

四类任务按诊断复杂度递增排列：

1. 病灶定位。
2. 多图选择。
3. 报告生成。
4. 知识问答。

Group Sequence-level Policy Optimization（GSPO）通过在序列级计算重要性比率，缓解长推理链中 token-level 策略比率带来的训练不稳定。每个课程阶段优化规则可验证奖励与 Intern-S1-mini judge reward 的加权组合，权重为 $\lambda_1=0.6$ 和 $\lambda_2=0.4$。训练配置为 $G=8$、$\varepsilon=0.2$、学习率 $5\times10^{-6}$、$\beta_{\mathrm{KL}}=0.04$，每阶段训练 2 epochs。

### 困难样本动态回溯

on-policy 重采样机制跟踪最近 $k=5$ 轮中持续低于奖励阈值的 prompt，并依据连续失败次数提高困难样本的采样概率。系统仅保存 prompt 索引与失败统计，确保每次重新访问困难 prompt 时生成新的 on-policy rollout。重采样比例不超过单个 batch 的 30%，以维持对已掌握样本的覆盖。

## 模型实验性能

表中指标为准确率（%）。由于基准的任务形式、难度和随机基线不同，平均值仅供参考。

| 模型 | In-Domain | Fundus | Omni-Eye | 平均* |
|---|---:|---:|---:|---:|
| InternVL3.5-2B | 34.50 | 36.61 | 55.47 | 42.19 |
| InternVL3.5-4B | 36.23 | 42.10 | 77.51 | 51.95 |
| Lingshu-7B | **44.20** | 41.29 | 87.42 | **57.64** |
| OphthaReason-Qwen-3B | 36.60 | 38.87 | 86.86 | 54.11 |
| **OphVLM-R1-2B（本文）** | 38.40 | 42.58 | **88.24** | 56.41 |

在论文报告的对比中，OphVLM-R1 在域外 OmniMedVQA-Eye 和 Fundus-MMBench 上分别达到 88.24% 和 42.58%；56.41% 的参考平均值高于 InternVL3.5-4B 的 51.95% 和 OphthaReason-Qwen-3B 的 54.11%。在 Omni-Eye 消融实验中，仅 SFT、一次性 RL、将 GSPO 替换为 token-level GRPO、移除困难样本回溯分别下降 26.21、10.10、3.72 和 2.12 个百分点。所有结果来自单次运行，未提供置信区间或显著性检验；与 off-the-shelf 7B/8B 模型的比较还受到训练数据暴露与参数规模差异影响，需要谨慎解读。

## OphAgent 设计架构

OphAgent-Pro 3.0 不再是五个彼此隔离的聊天接口，而是一套有状态 Agent 运行时：每个请求都会先经过分诊与路由，再进入有预算的执行档位，以可恢复 Run 的形式持久化，并通过可重放事件交付给 React 工作台。

```mermaid
flowchart LR
    UI["React 工作台<br/>对话 · 文件 · 项目 · 记忆 · 技能"] --> API["FastAPI<br/>鉴权 · REST · SSE · WebSocket"]
    API --> GATE["确定性红旗门禁<br/>附件归属 · 运行预算"]
    GATE --> ROUTER["意图路由<br/>Quick · Standard · Deep"]
    ROUTER --> DAG["类型化 DAG 规划<br/>并行节点 + 显式依赖"]
    DAG --> AGENTS["AgentScope ReAct 角色<br/>监督 · 临床 · 证据 · 专科 · 审查 · 报告"]
    AGENTS --> TOOLS["真实外部能力<br/>多模态 · 搜索 · MinerU · ASR/TTS"]
    TOOLS --> STATE["ClinicalState + 证据账本<br/>产物 · 已确认记忆"]
    STATE --> STORE["SQLite WAL 运行时存储<br/>Run · 事件 · 附件 · 上下文快照"]
    STORE --> API
```

### 3.0 架构升级

- **可持久化 Run 协议**：每次状态迁移、工具结果、生成产物和公开进度事件都有稳定的 `run_id`、`trace_id` 与单调递增序号。
- **真实流式响应**：支持 Provider Streaming 的终端文本会以 `answer.delta` 通过 SSE 推送；客户端先按持久化游标补齐早期事件，断线后从游标恢复且不重复内容。
- **Quick / Standard / Deep 路由**：确定性的意图与风险规则选择有界计划；急症红旗可覆盖用户指定的 Quick 模式。
- **类型化临床状态**：用户事实、缺失信息、红旗、证据与模型观察彼此分离，模型推测不能静默升级为已确认病情。
- **可组合专业插件**：`lesion_localizer`、`aux_diagnosis`、`report_generator` 可由用户指定，也可由路由器组合调用。
- **受控记忆与技能**：记忆先进入 `proposed`；导入的 `SKILL.md` 先隔离，结构、依赖、医疗安全与 checksum 门禁通过后才能启用。
- **真实能力健康状态**：模型、搜索、解析或语音能力不可用时会明确报告，不使用预设医学结论冒充真实结果。
- **隐私型可观测性**：OpenTelemetry 只允许导出标识、状态、耗时与 Token 聚合；Prompt、患者原文、文件内容和密钥不会进入遥测。

## 产品能力

| 能力 | 当前实现 |
|---|---|
| 多轮眼科问答 | 持久化 Conversation、上下文快照、有界历史压缩和追问路由继承 |
| 多模态复核 | 经过鉴权的眼底照、OCT、眼前节影像上传，返回经校验的观察与像素/归一化区域 |
| 病灶定位 | 只渲染通过坐标校验的边界框；模型未返回有效区域时不会补造病灶框 |
| 辅助评估 | 给出定性鉴别的支持、反对与缺失证据；支持程度不等同于患病概率 |
| 报告生成 | 带引用的 Markdown 报告、可编辑产物以及 MD/PDF/DOCX/JPG 导出 |
| 知识检索 | 指南优先 BM25 + 可选 BGE-M3 Embedding/Rerank、来源生命周期、PDF 页图与轻量图谱扩展 |
| 语音与文档 | 可选服务端 ASR/TTS、鉴权音频上传、MinerU/本地文档解析 |
| 工作区管理 | 项目、私人文件、生成产物、个人 Provider 配置、记忆、技能、来源治理与能力健康状态 |

## 执行档位

| 档位 | 典型请求 | 运行行为 |
|---|---|---|
| **Quick** | 简单非医疗事实或算术 | 单次有界直接回答，不进入检索或报告流水线 |
| **Standard** | 知识问答、单张影像任务或常规临床请求 | 相关临床、证据与影像节点可并行执行，再统一整合 |
| **Deep** | 复杂多模态评估、高风险症状或报告组合 | 加入相关亚专科复核，并执行 draft → critic → final 安全链 |

界面只展示克制的阶段摘要、经校验结果和来源证据，不公开私有 Chain-of-Thought。

## 医疗安全与可靠性

- 模型路由前先执行确定性红旗规则，必要时强制升级急症提示。
- 附件只能通过鉴权 ID 引用；REST 与 WebSocket 公共接口均拒绝客户端直接提交服务器路径。
- 模型调用次数、Token、总耗时和节点并发均受预算约束；取消会持久化并向执行节点传播。
- 必需节点失败会生成结构化失败事件；可选能力失败会给出明确警告。
- 引用按“医学主张段落”检查，不会因全文只出现一个标记就通过。
- 过期或已被替代的来源默认不参与检索；低可信来源会降权并保留标签。
- 服务重启会把未完成任务标记为 `interrupted`，已完成步骤仍可用于恢复或重试。
- 本系统定位为研究级临床辅助工具，不能给出最终确诊，也不能替代急诊与专业医疗评估。

## 技术栈

| 层级 | 实现 |
|---|---|
| Web 客户端 | React 19、TypeScript 5.8、Vite 6，适配桌面与移动端 |
| API | FastAPI 0.138、鉴权 REST、Server-Sent Events 与 WebSocket 兼容接口 |
| Agent 运行时 | AgentScope 1.0 ReAct 角色、确定性路由与类型化异步 DAG |
| 持久化 | SQLModel 账号/对话数据库 + SQLite WAL 运行事件存储 |
| 知识系统 | BM25、NumPy 向量持久化、OpenAI-compatible Embedding/Rerank、PDF 页图、OphthaGraph |
| 可观测性 | 带导出时隐私白名单的 OpenTelemetry |
| 工程质量 | Pytest、Vitest、ESLint、Ruff、Playwright 与 axe 无障碍检查 |

## 项目结构

```text
OphAgent/
├── app/
│   ├── api/             # 鉴权 REST、SSE 与 WebSocket 接口
│   ├── auth/            # JWT Cookie、会话撤销与登录保护
│   ├── domain/          # Run、事件、证据与 ClinicalState 契约
│   ├── evolution/       # 去内容化在线信号与离线门禁 Harness
│   ├── knowledge/       # 来源生命周期、混合检索与 OphthaGraph
│   ├── observability/   # 隐私过滤遥测
│   ├── plugins/         # 对外专业插件注册表
│   ├── runtime/         # 路由、规划、AgentScope 角色、存储与导出
│   ├── services/        # 记忆、技能与加密 Provider 配置
│   ├── tools/           # 多模态、搜索、文档与语音客户端
│   └── main.py
├── data/knowledge_base/raw/
├── frontend/            # React 工作台、单元测试与 Playwright 场景
├── scripts/             # 可移植知识库 CLI 与可选演化安装脚本
├── skills/              # 内置受控 Agent 技能
├── tests/               # 后端契约、安全与编排测试
├── .env.example
├── init_db.py
└── run.py
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+ 与 npm
- OpenAI-compatible 主 Agent 模型和多模态 Sub-agent 模型
- 推荐 8 GB+ RAM；只有本地托管模型时才需要 GPU

### 安装步骤

```bash
git clone git@github.com:QiZishi/OphAgent.git
cd OphAgent

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

npm --prefix frontend ci
npm --prefix frontend run build

cp .env.example .env
# 在 .env 中配置 JWT_SECRET_KEY、AGENT_* 与 SUB_AGENT_*。

python init_db.py
python run.py
```

访问 <http://localhost:8013>，创建账号后即可开始对话。默认 `STRICT_STARTUP=true`，必需模型凭据缺失时会在启动阶段直接报错。

### 最小配置

```dotenv
JWT_SECRET_KEY=请替换为足够长的随机字符串

AGENT_URL=https://your-provider.example/v1
AGENT_API_KEY=...
AGENT_MODEL=...

SUB_AGENT_URL=https://your-provider.example/v1
SUB_AGENT_API_KEY=...
SUB_AGENT_MODEL=...
```

Embedding、Rerank、AnySearch/Tavily、ASR、TTS、MinerU 与 OTLP 均为可选能力。工作区会显示其真实状态，各能力可独立降级。

## 知识语料

系统会自动索引 `data/knowledge_base/raw/` 下的受支持文件。可移植 CLI 能导入其他目录，不再依赖开发者本机绝对路径：

```bash
python scripts/build_knowledge_base.py \
  --collect \
  --source local-guidelines=/absolute/path/to/guidelines

python scripts/build_knowledge_base.py --build-index --lexical-only
python scripts/build_knowledge_base.py --search "青光眼视野随访"
python scripts/build_knowledge_base.py --stats
```

请只处理和分发已获授权的资料。用户导入来源默认处于未核验状态，应在来源治理工作区完成复核。

## API 与流式事件

| 接口 | 用途 |
|---|---|
| `POST /auth/register`、`POST /auth/login` | 创建账号或登录 |
| `POST /api/v1/conversations/{id}/messages` | 幂等创建消息与后台 Run |
| `GET /api/v1/runs/{id}` | 读取持久化 Run 状态 |
| `GET /api/v1/runs/{id}/events` | 按游标重放有序事件 |
| `GET /api/v1/runs/{id}/events/stream` | 带游标恢复与 Heartbeat 的 SSE |
| `POST /api/v1/upload` | 鉴权类型化附件上传 |
| `GET /api/v1/artifacts`、`GET /api/v1/attachments` | 私有生成产物与上传文件 |
| `WS /ws/runs/{id}` | 鉴权 WebSocket 事件桥 |

交互式 OpenAPI 文档位于 `/docs`。

## 开发说明

```bash
source venv/bin/activate
pip install -r requirements-dev.txt

python -m ruff check app tests scripts run.py init_db.py
pytest

npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build

npm --prefix frontend exec playwright install chromium
npm --prefix frontend run test:e2e -- workspace.spec.ts
```

新增能力时：

1. 在 `app/domain/` 新增或扩展类型化输入输出契约。
2. 在 `app/tools/` 注册外部行为，并定义真实健康状态。
3. 在 `app/runtime/` 更新路由与规划，不能绕过风险门禁和运行预算。
4. 为公开事件、附件归属、失败和取消路径补充回归测试。
5. React 工作台只展示通过校验的公开摘要。

## 受控离线演化

线上反馈只保存有界、去内容化信号，不能自动改写生产 Prompt、代码、技能或医疗事实。候选修改在隔离 Git worktree 中运行，晋升前必须通过同病例配对评测、sealed-test attestation、切片非劣、成本/延迟门禁与人工审批。官方可选实现通过 `requirements-evolution.txt` 单独安装。

## 开源状态

### 已开源

- **系统代码**：前后端实现、API 路由、业务服务和数据库模型。
- **OphReason-Vision 子集**：Hugging Face 与 ModelScope 上的 3,418 条冷启动样本。
- **OphVLM-R1 模型**：Hugging Face 与 ModelScope 上的模型权重。

### 计划开源

- 完成隐私与伦理审查后的 OphReason-Vision 剩余数据。
- 冷启动 SFT 与课程强化学习训练脚本。
- 模型评估代码。

## 引用

```bibtex
@inproceedings{qi2026ophvlm,
  title={OphVLM-R1: Efficient Ophthalmic Reasoning via Curriculum Reinforcement Learning},
  author={Qi, Zishi and Hu, Xiaoya and Pan, Huilin and Gao, Ang and Hou, Jiaxin and Li, Jiankun and Qian, Yongao},
  booktitle={Proceedings of the World Artificial Intelligence Conference Academic (WAICA)},
  year={2026}
}
```

## 致谢

本项目的开发离不开书生大模型生态、OpenGVLab、书生大模型实战营和 Datawhale 开源社区提供的模型、工具与学习资源。我们诚挚感谢这些社区为项目提供的基础支持，并感谢参与数据审核与质量控制的眼科医生。

## 相关链接

- **InternVL**：<https://github.com/OpenGVLab/InternVL>
- **书生大模型在线体验**：<https://chat.intern-ai.org.cn/>
- **书生大模型实战营**：<https://colearn.intern-ai.org.cn/go>
- **Datawhale**：<https://www.datawhale.cn/>
