# "慧眼·灵析"眼科智慧诊疗系统 - AI开发指南

## 项目架构概览

这是一个基于"慧眼·灵析"眼科多模态推理大模型(OphVLM-R1)构建的专业医疗AI系统，采用现代化的前后端分离架构。

### 核心组件
- **模型引擎**: OphVLM-R1 (2B参数，眼科专用多模态大模型)
- **后端框架**: FastAPI + SQLModel + SQLite
- **前端技术**: 原生JavaScript ES6+ (无框架依赖)
- **AI智能体**: 5个专门的眼科诊疗智能体

## 智能体架构模式

### 智能体结构
每个智能体都遵循统一的结构模式：
`python
# app/agents/{agent_name}.py
def get_welcome_message() -> str
def get_agent_type() -> str  
def get_display_name() -> str
def get_description() -> str
def get_system_prompt() -> str
def process_request(messages: List[Dict], uploaded_file_path: str) -> Dict
`

### 智能体类型
1. **interactive_vqa**: 智能问答 - 支持自由对话的图像分析
2. **lesion_localizer**: 病灶定位 - 返回边界框坐标的JSON格式
3. **aux_diagnosis**: 辅助诊断 - 返回多个诊断建议的JSON格式
4. **report_generator**: 报告生成 - 生成结构化医疗报告
5. **knowledge_base**: 知识库问答 - 纯文本医学知识查询

### 前端UI映射
每个智能体都有对应的前端UI类：
`javascript
// app/static/js/agents/{agent_name}.js
class {AgentName}UI {
    renderSpecialOutput(messageElement, data) {
        // 智能体特定的UI渲染逻辑
    }
}
`

## 关键技术实现

### 模型服务集成
- 模型配置: app/core/config.py - MODEL_NAME="OphVLM-R1"
- 服务接口: app/services/model_service.py
- 图像编码: base64格式，支持多种眼科影像类型
- 响应处理: 支持JSON结构化输出和流式文本输出

### 数据流架构
`
前端文件上传 → file_service处理 → base64编码 → 模型API调用 → 智能体处理 → 前端渲染
`

### WebSocket通信
- 路径: /api/v1/ws/{conversation_id}
- 消息格式: {"agent_type": "...", "history": [...], "file_path": "..."}
- 流式输出: 支持thinking和answer分离显示

## 开发最佳实践

### 添加新智能体
1. 创建app/agents/new_agent.py，实现必需的接口函数
2. 在app/api/router.py的agent_processors中注册
3. 创建对应的前端UI类app/static/js/agents/new_agent.js
4. 在app/static/js/ui.js的initializeAgentUIs()中初始化

### 系统提示语设计
- 使用结构化格式，包含<thinking>和<answer>标签
- 针对JSON输出的智能体，明确指定输出格式
- 专业医学术语和临床标准的一致性

### 文件处理
- 支持格式: PDF, JPG, PNG, JPEG, DOCX
- 存储路径: app/static/uploads/user_{user_id}/
- 安全检查: 文件类型验证和大小限制

### 数据库模式
`python
User -> Conversation -> Message -> Attachment
`
- 用户认证: JWT tokens
- 对话管理: 支持多版本消息和软删除
- 附件关联: 一对多关系

## 配置管理

### 环境变量
`env
OPENAI_API_BASE=http://0.0.0.0:8000/v1  # 模型服务地址
OPENAI_API_KEY=sk-...                    # API密钥
MODEL_NAME=OphVLM-R1                     # 模型名称
TEMPERATURE=0.7                          # 生成温度
`

### 启动命令
`bash
python run.py  # 开发环境 (端口8012)
`

## 前端架构特点

### 模块化设计
- app/static/js/ui.js: 主要UI管理器
- app/static/js/api.js: API通信层
- app/static/js/websocket.js: WebSocket管理
- app/static/js/agents/: 智能体专用UI

### 响应式设计
- 蓝白医疗主题配色
- 移动端适配
- Lucide图标系统

### 状态管理
- 当前智能体状态: 	his.currentAgent
- 对话ID管理: 	his.currentConversationId
- 文件上传状态: 	his.selectedFiles

## 常见开发任务

### 调试模型调用
检查日志输出中的[DEBUG]标记，包含完整的API调用信息。

### 修改智能体提示语
编辑对应智能体文件中的get_system_prompt()函数。

### 自定义前端渲染
在智能体UI类中重写
enderSpecialOutput()方法。

### 数据库结构变更
修改app/db/models.py后重新运行python init_db.py。

这个系统专门为眼科医疗应用场景优化，请遵循医疗软件的安全和准确性标准进行开发。
