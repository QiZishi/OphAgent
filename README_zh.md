<p align="center">
  <img src="figures/模型图标.png" width="120" alt="OphVLM-R1 项目图标">
</p>

<h1 align="center">OphAgent · “灵瞳”眼科智慧诊疗系统</h1>

<p align="center"><strong>基于 ReAct 的眼科多模态推理与临床辅助平台</strong></p>

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

- **2025.11.23** 🎬 “灵瞳”眼科智慧诊疗系统实机演示视频已在 B 站正式发布，展示五大智能体全流程诊疗能力！
  - 🎥 视频链接：<https://www.bilibili.com/video/BV1g4UTBZEEm/>

## 项目背景

**“灵瞳”眼科智慧诊疗系统**是基于自主研发的 **OphVLM-R1 眼科多模态推理模型**构建的专业化医疗 AI 平台。该项目由华中科技大学人工智能与自动化学院人工智能安全实验室团队开发，旨在缓解全球眼科优质医疗资源分布不均，以及基层医疗机构误诊、漏诊率较高等现实问题。

眼科多模态大语言模型面临三大挑战：训练数据缺乏结构化推理链、单阶段训练难以培养深度临床推理能力，以及模型规模过大制约资源受限环境中的部署。项目通过一体化的“数据—模型—智能体”技术栈解决这些问题：OphReason-Vision 将异构眼科数据转化为经过专家验证的推理轨迹；OphVLM-R1 通过 LoRA 冷启动和课程强化学习获得临床推理能力；OphAgent 则以模块化临床辅助系统对外提供这些能力。

系统基于书生大模型生态，包括 InternVL3.5 和 Intern-S1，采用 **ReAct（Reasoning + Acting）智能体架构**，集成智能问答、病灶定位、辅助诊断、报告生成与眼科知识库五大专业 AI 智能体。通过数据集构建流水线、两阶段模型训练和 ReAct 智能体系统，“灵瞳”推动眼科智能诊疗从“感知识别”走向“认知推理”，并使中间决策和工具操作保持可检查、可追溯。

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

“灵瞳”系统基于 ReAct 架构构建，实现 **Reasoning → Acting → Observation** 的闭环。每个智能体首先分析临床请求和现有多模态证据，然后选择并执行适当操作，最后将返回观察结果纳入下一步推理。该设计使任务拆解、工具执行和返回证据保持可检查、可追溯。

```text
OphAgent/
├── app/
│   ├── main.py              # FastAPI 主应用
│   ├── agents/              # ReAct 智能体
│   ├── api/                 # API 路由
│   ├── services/            # 业务服务
│   └── static/              # Web 界面
├── figures/                 # 文档资源
├── requirements.txt
└── run.py
```

- **后端**：基于 FastAPI 搭建，支持异步处理与自动 API 文档；通过 SQLModel 统一数据验证和数据库模型，并使用 SQLite 提供轻量级持久化。
- **前端**：采用原生 JavaScript ES6+ 开发，无框架依赖，并通过响应式布局适配桌面和移动设备。
- **通信**：集成 WebSocket，实现实时通信与模型响应流式输出。
- **智能体层**：五个模块化智能体均遵循 ReAct 工作流，并分别对应不同的临床辅助任务。

## 项目核心亮点

- **🧠 OphVLM-R1 模型驱动**：轻量级 2B 参数眼科推理模型支持眼底照片、OCT 和眼前节影像等多种眼科图像。
- **🔄 ReAct 架构设计**：每个智能体将推理与行动分离，相比单次黑盒式模型响应，更便于检查中间决策过程。
- **🎯 五大专业智能体**：覆盖影像交互、病灶分析、候选诊断、报告撰写和知识查询。
- **💡 模块化与可解释性**：不同临床能力由相互独立的功能组件承载，便于分别配置、维护和扩展。

## 核心功能

### 智能问答

支持上传眼科影像进行开放式问答和多轮追问，使用户能够根据新发现持续细化问题。

![智能问答演示](figures/demo_interactive_vqa.png)

### 病灶定位

自动识别并标注眼科影像中的疑似病灶区域，返回标准化边界框供后续检查。

![病灶定位演示](figures/demo_lesion_localization.png)

### 辅助诊断

提供多个候选疾病诊断建议，并给出置信信息和支持诊断的依据，辅助临床复核。

![辅助诊断演示](figures/demo_aux_diagnosis.png)

### 报告生成

自动生成结构化眼科影像报告，包含影像所见和诊断意见。

![报告生成演示](figures/demo_report_generation.png)

### 眼科知识库

提供专业眼科医学知识问答，并在检索服务完成配置后返回支持来源。

![知识库演示](figures/demo_knowledge_base.png)

## 快速开始

### 环境要求

- Python 3.8+
- 推荐 8 GB+ RAM
- 本地模型部署时可选用 GPU

### 安装步骤

1. 克隆项目：

   ```bash
   git clone https://github.com/QiZishi/OphAgent.git
   cd OphAgent
   ```

2. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. 配置环境变量：

   ```bash
   cp .env.example .env
   # 编辑 .env，配置模型服务。
   ```

4. 初始化数据库并启动系统：

   ```bash
   python init_db.py
   python run.py
   ```

5. 访问 <http://localhost:8012>，注册账号并开始使用。

## 开发说明

### 添加新智能体

1. 在 `app/agents/` 下创建智能体模块。
2. 在 `app/api/` 下注册对应 API 路由。
3. 在 `app/static/js/agents/` 下添加对应前端模块。

部署相关设置通过 `app/core/config.py` 与 `.env` 管理。

## 常见问题

1. **模型服务连接失败**
   - 检查 `.env` 中的 `OPENAI_API_BASE` 及相关凭据。
   - 确认所配置的模型服务正常运行且网络可达。
2. **文件上传问题**
   - 检查 `app/static/uploads/` 的目录权限。
3. **数据库问题**
   - 运行 `python init_db.py` 重新初始化本地数据库。

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
