# "灵瞳"眼科智慧诊疗系统

![慧眼·灵析Logo](app/static/icons/system_logo.png)


## 📋 To Do List - 开源路线图

### ✅ 已开源内容
- [x] **系统应用代码**：完整的前后端代码、API 接口、数据库模型
- [x] **ReAct Agent 架构实现**：五大智能体的完整实现代码与提示工程
- [x] **部署文档**：环境配置、安装指南、API 文档
- [x] **开发指南**：智能体开发规范、系统架构说明

### 🔄 计划开源内容
- [ ] **模型权重**：OphVLM-R1 眼科多模态推理大模型权重文件
- [ ] **训练数据集**：眼科影像标注数据、多模态训练语料
- [ ] **测试数据集**：OmniMedVQA-Eye 评估数据、性能基准测试集
- [ ] **模型训练代码**：预训练与微调脚本、训练配置文件

> **说明**：模型权重和数据集将在完成医学数据隐私与伦理审查后分批开源，预计在后续版本中发布。请关注本仓库的 Release 页面获取最新进展。

## 🎯 项目简介

**"灵瞳"眼科智慧诊疗系统**是基于自主研发的"慧眼·灵析"眼科多模态推理大模型(OphVLM-R1)构建的专业化医疗 AI 平台。系统采用**ReAct (Reasoning + Acting) 智能体架构**作为核心技术框架，集成了五大专业 AI 智能体，专门针对眼科影像分析和诊断任务进行深度优化，为医生提供高效、精准的智能诊疗支持。

**系统实机演示视频链接**：
https://www.bilibili.com/video/BV1g4UTBZEEm/
欢迎各位同仁批评指正！

**核心技术亮点**：
- 🧠 **OphVLM-R1 模型驱动**：2B 参数的眼科专用多模态推理大模型
- 🔄 **ReAct 架构设计**：每个智能体均采用"推理-行动"循环机制，实现可解释的诊疗决策
- 🎯 **五大专业智能体**：覆盖问答、定位、诊断、报告、知识库等全流程诊疗需求

### 🧠 核心技术优势

本系统采用"慧眼·灵析"眼科多模态推理大模型(OphVLM-R1\)作为底层 AI 引擎，结合ReAct智能体架构，实现了可解释、可追溯的智能诊疗决策流程。

#### 模型层面优势
- **模型规模**：2B 参数量的轻量化设计，在保证性能的同时大幅降低部署成本
- **专业性强**：专门针对眼科领域进行预训练和微调，具备深度的眼科医学知识
- **多模态理解**：支持眼底照片、OCT、眼前节照片等多种眼科影像类型
- **推理效率**：优化的模型架构确保快速响应，满足临床实时应用需求

#### ReAct 架构优势
- **可解释性**：每个智能体的决策过程分为 Reasoning \(思考\) 和 Acting \(行动\) 两个阶段，医生可清晰了解 AI 的推理路径
- **迭代优化**：通过思考-行动循环，智能体能够自我修正和优化诊断建议
- **模块化设计**：统一的 ReAct 框架使得智能体易于扩展和维护
- **临床适配**：符合医生的临床思维模式，降低 AI 系统的使用门槛

## 📊 模型性能对比分析

### "慧眼·灵析"眼科多模态推理大模型的显著优势

基于最新的性能评估结果，"慧眼·灵析"眼科多模态推理大模型(Ours-2B-Preview)在 OmniMedVQA-Eye 眼科医学问答数据集上展现出了卓越的性能：

| 模型类别           | 模型名称            | 域内（判断题）准确率 | 域内（选择题）准确率 | 域外（OmniMedVQA-Eye）准确率 |
| ------------------ | ------------------- | -------------------- | -------------------- | ---------------------------- |
| **通用多模态模型** | InternVL3-1B        | 41.60%               | 26.60%               | 48.78%                       |
|                    | InternVL3-2B        | 56.40%               | 34.70%               | 64.07%                       |
|                    | InternVL3-8B        | 65.40%               | 34.70%               | 71.06%                       |
|                    | Qwen2.5VL-3B        | 51.70%               | 34.40%               | 56.26%                       |
|                    | Qwen2.5VL-7B        | 69.20%               | 42.10%               | 60.24%                       |
|                    | MiMo-VL-7B-RL       | **75.30%**           | 44.60%               | 67.56%                       |
| **医学专用模型**   | MedVLM-R1-2B        | 22.00%               | 31.40%               | 64.31%                       |
|                    | Med-R1-2B-Fundus    | 24.00%               | 26.10%               | 69.11%                       |
|                    | MedGemma-4B-IT      | 39.20%               | 40.20%               | 62.85%                       |
|                    | HuatuoGPT-V-7B      | 59.50%               | 51.90%               | 73.66%                       |
| **我们的模型**     | **Ours-2B-Preview** | 67.60%               | **59.50%**           | **76.34%**                   |

### 关键性能指标分析

#### 1. 综合性能表现

- **OmniMedVQA-Eye 得分 76.34%**：在所有参与对比的模型中排名第一，相比同规模模型有显著提升
- **相比最接近的竞争对手 HuatuoGPT-V-7B(73.66%)**：尽管参数量仅为其 1/3，但性能提升了 2.68 个百分点

#### 2. 参数效率优势

- **2B 参数量**：在保持轻量化的同时实现最优性能
- **与 InternVL3-2B 对比**：同为 2B 参数量，我们的模型在 OmniMedVQA-Eye 上的表现超出 12.27 个百分点(76.34% vs 64.07%)
- **与 Qwen2.5VL-3B 对比**：用更少的参数量(2B vs 3B)实现了 20.08 个百分点的性能提升(76.34% vs 56.26%)

#### 3. 专业化优势

- **域内外均衡表现**：域内准确率 67.60%，域外准确率 76.34%，显示出良好的泛化能力
- **医学专业性**：相比通用多模态模型，在医学专业任务上表现更加优异
- **眼科专门优化**：针对眼科影像特点进行专门训练，在眼科相关任务上表现突出

#### 4. 实用性分析

- **部署友好**：2B 参数量使得模型可以在相对较低的硬件配置上部署
- **推理速度**：轻量化设计保证了快速的推理响应时间
- **成本效益**：在达到最佳性能的同时，大幅降低了计算资源需求

## 🎯 五大 AI 智能体功能

> 所有智能体均基于 **ReAct (Reasoning + Acting) 架构**设计，每次响应包含 `<think>` (推理过程) 和 `<answer>` (行动结果) 两个部分，确保诊疗决策的可解释性和可追溯性。

### 1. 💬 智能问答 (Interactive VQA)

- **功能描述**：支持上传眼科影像进行自由问答交互
- **ReAct 实现**：
  - *Reasoning*：分析影像特征，理解医生问题意图，调用医学知识库
  - *Acting*：生成精准的专业解答，支持多轮追问和深度交互
- **应用场景**：医生可以针对影像提出任意问题，获得专业解答

### 2. 🎯 病灶定位 (Lesion Localization)

- **功能描述**：自动识别并标注眼科影像中的病灶区域
- **ReAct 实现**：
  - *Reasoning*：逐步扫描影像区域，识别异常特征，评估病灶类型和严重程度
  - *Acting*：输出标准化 JSON 格式的边界框坐标、病灶类型和置信度评分
- **应用场景**：快速筛查可疑病灶，辅助医生聚焦重点区域

### 3. 🩺 辅助诊断 (Diagnostic Assistant)

- **功能描述**：提供多种可能的疾病诊断建议
- **ReAct 实现**：
  - *Reasoning*：分析影像表现，结合临床知识库，推理可能的疾病类型和鉴别诊断
  - *Acting*：输出结构化的诊断建议列表，包含疾病名称、置信度、诊断依据和建议检查
- **应用场景**：为医生提供诊断参考，提高诊断准确性和效率

### 4. 📄 报告生成 (Report Generation)

- **功能描述**：自动生成结构化的眼科影像诊断报告
- **ReAct 实现**：
  - *Reasoning*：综合分析影像所见，组织诊断逻辑，规划报告结构
  - *Acting*：按照医疗规范生成包含"影像所见"、"诊断意见"、"建议"等标准章节的完整报告
- **应用场景**：减少医生撰写报告的工作量，提高工作效率

### 5. 🧠 眼科知识库 (Knowledge Base)

- **功能描述**：专业眼科医学知识问答系统
- **ReAct 实现**：
  - *Reasoning*：检索相关医学文献和指南，评估信息可靠性，组织知识要点
  - *Acting*：提供结构化的知识解答，引用权威来源，确保医学准确性
- **应用场景**：医学知识查询、学习辅助、临床指导

## 🚀 技术架构

### 后端技术栈

- **FastAPI**：高性能异步 Web 框架，支持自动 API 文档生成
- **SQLModel**：统一数据验证与数据库模型管理
- **SQLite**：轻量级数据库，支持快速部署
- **WebSocket**：实时通信，支持流式 AI 响应
- **OpenAI API**：标准化的 AI 模型调用接口

### 前端技术栈

- **原生 JavaScript ES6+**：无框架依赖，确保系统稳定性
- **响应式设计**：适配桌面和移动设备
- **WebSocket 客户端**：实时 AI 响应展示
- **模块化架构**：每个智能体独立的 UI 组件

### AI 模型集成 (基于 ReAct 架构)

- **模型服务**：基于 OpenAI API 标准的模型服务接口，驱动 OphVLM-R1 推理引擎
- **图像处理**：支持多种医学影像格式的预处理和 base64 编码
- **ReAct 流式输出**：实时展示 `<think>` 推理过程和 `<answer>` 行动结果，提升用户体验
- **智能体调度**：统一的 ReAct 框架管理五大智能体的推理-行动循环
- **提示工程**：每个智能体配备专门优化的 system prompt，指导 ReAct 流程执行

## 📦 快速开始

### 环境要求

- Python 3.8+
- 8GB+ RAM（推荐）
- GPU 支持（可选，用于本地模型部署）

### 安装步骤

1. **克隆项目**

   ```bash
   git clone [项目地址]
   cd 慧眼·灵析项目代码
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

### 配置说明

关键配置项（在.env 文件中）：

```env
# 模型服务配置
OPENAI_API_BASE=your-api-base-url
OPENAI_API_KEY=your-api-key
MODEL_NAME=your-model-name

# 系统配置
TEMPERATURE=0.7
JWT_SECRET_KEY=your-secret-key
```

## 🏗️ 系统架构

```
慧眼·灵析系统/
├── app/
│   ├── main.py              # FastAPI主应用
│   ├── core/config.py       # 配置管理
│   ├── db/                  # 数据库层
│   │   ├── models.py        # 数据模型
│   │   ├── crud.py          # 数据操作
│   │   └── database.py      # 数据库连接
│   ├── auth/                # 认证模块
│   │   ├── router.py        # 认证路由
│   │   ├── security.py      # 安全组件
│   │   └── schemas.py       # 认证模型
│   ├── agents/              # AI智能体
│   │   ├── interactive_vqa.py      # 智能问答
│   │   ├── lesion_localizer.py     # 病灶定位
│   │   ├── aux_diagnosis.py        # 辅助诊断
│   │   ├── report_generator.py     # 报告生成
│   │   └── knowledge_base.py       # 知识库
│   ├── api/                 # API路由
│   ├── services/            # 业务服务
│   │   ├── model_service.py        # 模型服务
│   │   ├── chat_service.py         # 聊天服务
│   │   └── file_service.py         # 文件服务
│   ├── static/              # 前端资源
│   │   ├── js/              # JavaScript文件
│   │   ├── css/             # 样式文件
│   │   └── icons/           # 图标资源
│   └── templates/           # HTML模板
├── .github/
│   └── copilot-instructions.md     # AI开发指南
├── requirements.txt         # Python依赖
├── run.py                  # 启动脚本
└── README.md               # 项目文档
```

## 🔧 开发指南

### 添加新智能体

1. **创建智能体模块**

   ```python
   # app/agents/new_agent.py
   def get_welcome_message():
       return "新智能体的欢迎语"

   def get_system_prompt():
       return "系统提示语..."

   def process_request(messages, uploaded_file_path):
       # 处理逻辑
       return {"type": "success", "payload": {...}}
   ```

2. **注册智能体**

   ```python
   # app/api/router.py
   agent_processors = {
       "new_agent": new_agent.process_request,
       # ...其他智能体
   }
   ```

3. **创建前端 UI**
   ```javascript
   // app/static/js/agents/new_agent.js
   class NewAgentUI {
     renderSpecialOutput(messageElement, data) {
       // UI渲染逻辑
     }
   }
   ```

### 自定义配置

编辑配置文件以适应不同部署环境：

```python
# app/core/config.py
class Settings(BaseSettings):
    OPENAI_API_BASE: str = "http://your-model-service/v1"
    MODEL_NAME: str = "your-model-name"
    # 其他配置...
```

## 🛠️ API 文档

启动系统后可访问自动生成的 API 文档：

- **Swagger UI**: http://localhost:8012/docs
- **ReDoc**: http://localhost:8012/redoc

### 主要 API 端点

#### 认证相关

- POST /register - 用户注册
- POST /login - 用户登录
- GET /me - 获取用户信息

#### 对话管理

- GET /api/v1/conversations - 获取对话列表
- POST /api/v1/conversations - 创建新对话
- POST /api/v1/conversations/{id}/messages - 发送消息
- WebSocket /api/v1/ws/{conversation_id} - 实时通信

#### 文件处理

- POST /api/v1/upload - 文件上传

## 🔍 故障排除

### 常见问题

1. **模型服务连接失败**

   - 检查 OPENAI_API_BASE 配置是否正确
   - 确认模型服务是否正常运行
   - 验证 API 密钥的有效性

2. **文件上传问题**

   - 检查 app/static/uploads/目录权限
   - 确认文件格式是否支持
   - 检查文件大小限制

3. **数据库问题**
   - 运行 python init_db.py 重新初始化
   - 检查数据库文件权限

### 调试技巧

- 查看控制台日志中的[DEBUG]标记
- 使用浏览器开发者工具检查网络请求
- 检查 WebSocket 连接状态

## 🤝 贡献指南

1. Fork 项目仓库
2. 创建功能分支 (git checkout -b feature/NewFeature)
3. 提交更改 (git commit -m 'Add NewFeature')
4. 推送到分支 (git push origin feature/NewFeature)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证

## 🙏 致谢

- 眼科医学专家的专业指导
- 开源社区的技术支持

---

**"灵瞳"眼科智慧诊疗系统** - 让 AI 成为眼科医生的智能助手，提升诊疗效率与精度。

本项目欢迎各界贡献与合作，共同推动医疗 AI 技术的发展！










