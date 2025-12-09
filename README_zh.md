# <img src="figures/system_logo.png" width="40" /> "灵瞳"眼科智慧诊疗系统

[English](README.md) | [简体中文](README_zh.md)

## 📰 新闻动态

- **2025.12.09** 🎉 **重磅喜讯！** "灵瞳"眼科智慧诊疗系统获得上海人工智能实验室力宣传推荐，并荣获**书生大模型实战营优秀项目**荣誉！衷心感谢上海人工智能实验室与书生大模型实战营的认可与支持！
  - 📖 宣传文章：https://mp.weixin.qq.com/s/BTZPUrVtD8nCS_yMwDhhUQ

- **2025.11.28** 📊 高质量眼科多模态推理数据集 **OphReason-Vision** 部分子集已在ModelScope平台正式开源发布！
  - 🔗 数据集链接：https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision

- **2025.11.23** 🎬 "灵瞳"眼科智慧诊疗系统实机演示视频已在B站正式发布，展示五大智能体全流程诊疗能力！
  - 🎥 视频链接：https://www.bilibili.com/video/BV1g4UTBZEEm/

## 1. 项目简介

**"灵瞳"眼科智慧诊疗系统**是基于自主研发的**OphVLM-R1眼科多模态推理大模型**构建的专业化医疗AI平台。该项目由华中科技大学人工智能与自动化学院人工智能安全实验室团队开发，旨在破解全球眼科优质医疗资源分布不均、基层医疗机构误诊漏诊率居高不下的行业困境。

系统基于书生大模型生态（InternVL3、Intern-S1），采用**ReAct (Reasoning + Acting) 智能体架构**，集成了五大专业AI智能体——智能问答、病灶定位、辅助诊断、报告生成与眼科知识库。通过创新的数据集构建方法、两阶段训练架构与ReAct智能体系统，实现了眼科智能诊疗从“感知识别”向“认知推理”的跨越，为临床提供了高效、透明且可信的辅助诊疗方案。

**核心目标**：通过AI技术赋能临床医生，尤其是基层医疗工作者，提升眼科疾病的早期筛查与精准诊断能力。

## 2. 快速入门

### 环境要求

- Python 3.8+
- 8GB+ RAM（推荐）
- GPU 支持（可选，用于本地模型部署）

### 安装步骤

1. **克隆项目**

   ```bash
   git clone [项目地址]
   cd OphAgent
   ```
2. **安装依赖**

   ```bash
   pip install -r requirements.txt
   ```
3. **配置环境变量**

   ```bash
   cp .env.example .env
   # 编辑.env文件，配置模型服务信息
   ```
4. **初始化数据库**

   ```bash
   python init_db.py
   ```
5. **启动系统**

   ```bash
   python run.py
   ```
6. **访问系统**

   - 浏览器访问：http://localhost:8012
   - 注册账号并开始使用

## 3. 系统架构

“灵瞳”系统基于ReAct架构构建，实现了“推理-行动”的闭环循环，让AI决策过程可解释、可追溯。

- **后端**：基于FastAPI框架搭建，支持异步高并发处理与自动API文档生成；通过SQLModel统一数据验证与数据库模型管理，选用SQLite作为轻量级数据库。
- **前端**：采用原生JavaScript ES6+开发，无框架依赖确保系统稳定性，响应式设计适配桌面与移动设备。
- **通信**：集成WebSocket实现实时通信，支持AI响应的流式输出。
- **智能体**：五大智能体均遵循ReAct工作模式，接收指令后先进入推理阶段（Reasoning），再进入行动阶段（Acting）。

```
OphAgent/
├── app/
│   ├── main.py              # FastAPI主应用
│   ├── agents/              # AI智能体 (ReAct架构)
│   ├── api/                 # API路由
│   ├── services/            # 业务服务
│   └── static/              # 前端资源
├── figures/                 # 项目演示图片
├── requirements.txt         # Python依赖
└── run.py                   # 启动脚本
```

## 4. 项目核心亮点

- **🧠 OphVLM-R1 模型驱动**：采用轻量化设计（2B参数），仅2B参数量却具备深度的眼科专业推理能力，支持眼底照片、OCT、眼前节照片等多种眼科影像类型的解析。
- **🔄 ReAct 架构设计**：每个智能体的决策过程分为 Reasoning (思考) 和 Acting (行动) 两个阶段，医生可清晰了解 AI 的推理路径，打破传统AI模型“黑箱操作”的局限。
- **🎯 五大专业智能体**：覆盖从影像分析、疾病诊断到报告撰写、知识查询的全流程诊疗需求。
- **💡 模块化与可解释性**：模块化设计符合医生的临床思维模式，降低了AI系统的使用门槛，实现了诊疗决策的可解释性与可追溯性。

## 5. 项目技术细节

### 5.1 数据集构建：高质量推理数据的生成闭环

为解决眼科多模态数据异构性强、推理逻辑缺失的问题，我们设计了“数据标准化-结构化推理合成-专家协同优化”的三阶段闭环管线。

![数据训练管线](figures/data_training_pipeline.png)

1. **数据标准化**：整合10万余例真实临床病例与30多个公开眼科数据集。利用MinerU解析电子病历，利用InternVL3-78B生成视觉描述。
2. **结构化推理合成**：引入Intern-S1作为核心推理引擎，生成涵盖“病灶定位”、“多模态诊断”、“医学知识问答”的多维指令数据及思维链（CoT）。引入“LVLM-as-a-Judge”机制校验质量。
3. **专家协同优化**：眼科专家对困难样本进行二次审查修正，构建难度感知的动态数据池。

### 5.2 模型训练：两阶段渐进式强化学习架构

我们以InternVL3-2B为基座模型，采用“冷启动监督微调+渐进式课程强化学习”的两阶段架构。

![两阶段训练](figures/two_stage_training.png)

1. **冷启动监督微调 (Cold-Start SFT)**：采用LoRA技术注入眼科领域知识。
2. **渐进式课程强化学习 (Progressive Curriculum RL)**：引入DAPO算法，通过由易到难的四阶段课程（病灶定位 -> 多图选择 -> 开放式图文问答 -> 眼科知识问答）激发深度推理能力。

## 6. 模型性能说明

基于最新的性能评估结果，"慧眼·灵析"眼科多模态推理大模型(OphVLM-R1 / Ours-2B-Preview)在 OmniMedVQA-Eye 眼科医学问答数据集上展现出了卓越的性能。

![模型性能结果](figures/model_performance.svg)

- **综合性能**：OmniMedVQA-Eye 得分 **76.34%**，在所有参与对比的模型中排名第一。
- **参数效率**：以2B参数量超越了更大参数量的模型（如HuatuoGPT-V-7B）。
- **专业优势**：域内准确率67.60%，域外准确率76.34%，显示出良好的泛化能力和医学专业性。

## 7. 数据集示例

项目构建了高质量眼科多模态推理数据集 **OphReason-Vision**，为模型训练提供了坚实支撑。

![数据集示例](figures/dataset_example.png)

该数据集首次实现了眼科多模态数据的深度对齐与结构化推理链的标准化生成。

## 8. 项目效果演示

系统集成了五大智能体，以下是各智能体的实际运行效果：

### 8.1 智能问答 (Interactive VQA)

支持上传眼科影像进行自由问答交互，支持多轮追问。
![智能问答演示](figures/demo_interactive_vqa.png)

### 8.2 病灶定位 (Lesion Localization)

自动识别并标注眼科影像中的病灶区域，输出标准化边界框。
![病灶定位演示](figures/demo_lesion_localization.png)

### 8.3 辅助诊断 (Diagnostic Assistant)

提供多种可能的疾病诊断建议，包含置信度和诊断依据。
![辅助诊断演示](figures/demo_aux_diagnosis.png)

### 8.4 报告生成 (Report Generation)

自动生成结构化的眼科影像诊断报告，包含影像所见和诊断意见。
![报告生成演示](figures/demo_report_generation.png)

### 8.5 眼科知识库 (Knowledge Base)

专业眼科医学知识问答系统，引用权威来源。
![知识库演示](figures/demo_knowledge_base.png)

## 9. 开发指南

### 添加新智能体

1. **创建智能体模块** (`app/agents/new_agent.py`)
2. **注册智能体** (`app/api/router.py`)
3. **创建前端 UI** (`app/static/js/agents/new_agent.js`)

### 自定义配置

编辑 `app/core/config.py` 以适应不同部署环境。

## 10. 常见问题说明

1. **模型服务连接失败**

   - 检查 `.env` 中的 `OPENAI_API_BASE` 配置。
   - 确认模型服务是否正常运行。
2. **文件上传问题**

   - 检查 `app/static/uploads/` 目录权限。
3. **数据库问题**

   - 运行 `python init_db.py` 重新初始化。

## 11. 开源说明

### ✅ 已开源内容
- **系统架构代码**：完整的前后端代码、API 接口、数据库模型
- **部分数据集**：OphReason-Vision 数据集部分子集
- **系统演示视频**：完整系统功能演示

### 🔄 计划开源内容
- **完整数据集**：OphReason-Vision 完整数据集
- **模型权重**：OphVLM-R1 模型权重
- **模型训练脚本**：冷启动微调训练脚本和课程强化学习训练脚本
- **模型测试评估代码**：模型性能评估代码

> **说明**：完整数据集、模型权重及训练代码将在完成医学数据隐私与伦理审查后分批开源。

## 12. 鸣谢

本项目的顺利推进离不开书生大模型实战营、书生Intern大模型生态以及Datawhale开源社区的关键支撑与技术支持。我们诚挚感谢这些开源社区为本项目提供的坚实基础，共同推动眼科AI领域的发展。

## 13. 相关链接

- **灵瞳眼科智慧诊疗系统应用演示视频**：https://www.bilibili.com/video/BV1g4UTBZEEm/
- **项目开源代码**：https://github.com/QiZishi/OphAgent/
- **OphReason-Vision数据集**：https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision
- **InternVL 开源链接**：https://github.com/OpenGVLab/InternVL
- **书生大模型在线体验**：https://chat.intern-ai.org.cn/
- **书生大模型实战营**：https://colearn.intern-ai.org.cn/go
- **Datawhale开源社区**：https://www.datawhale.cn/
