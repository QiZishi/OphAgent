# OphAgent-Pro 对齐 ChatGPT Work 的前后端审计与重构指南

> 文档用途：直接交给代码智能体，作为后续重构的需求、问题清单、架构约束和验收标准。
> 审计日期：2026-07-28
> 审计范围：`frontend/`、FastAPI API、Run/Event/Artifact、Agent 编排、插件、知识检索、上传、认证与管理页。

## 0. 先读结论

当前项目不是“ChatGPT Work 风格的眼科助手”，而是“固定三栏的 Agent 调试工作台”：

- 前端把计划、工具轨迹和执行过程固定放在右栏，主对话只显示一句最新状态和最终结果。
- 左栏宽度硬编码，不能拖动或折叠；窄屏时直接消失。
- 五项专业能力被做成五种互斥“工作方式”，但它们实际上应该是一个统一助手可自动或手动调用的五个主要插件。
- 每条消息都是孤立 Run，不是真正的多轮会话；历史对话、项目、文件、产物和运行没有统一数据模型。
- 后端不根据任务难度规划。即使输入“1+1等于多少？请直接回答。”，也会固定执行 Supervisor、临床抽取、医学检索、报告生成。
- 预算检查发生在模型已经调用之后，导致系统花完时间和 token 才失败；现有失败任务点“恢复”也不能真正重跑失败节点。
- 检索没有绝对相关性阈值，会把接近零相关度的眼科材料硬塞给无关问题，再由报告 Agent 扩写成伪相关长报告。
- 项目是浏览器 SPA，由 FastAPI 托管，并不具备原生桌面应用的窗口、系统菜单、Dock 图标、本地文件权限和打包能力。

建议先修复编排与数据模型，再重做前端。只换皮肤会把当前的慢、错和不可恢复包装得更漂亮，却不会改善产品。

---

## 1. 审计方法与证据边界

### 1.1 实际执行过的检查

已启动当前仓库：

```bash
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8013
```

已通过真实 HTTP/SSE 调用验证：

- 注册、登录、`/auth/me`
- 创建 Run、读取 Run、SSE 事件流
- 取消、恢复、再次取消
- 图片上传
- Memory、Skill、知识库、Capability、Artifact 读取接口
- React 生产构建
- Python 测试

验证结果：

| 检查 | 结果 |
|---|---|
| 首页与 API 启动 | 通过，HTTP 200 |
| 注册、登录、Cookie 会话 | 通过 |
| 上传 `figures/system_logo.png` | 通过 |
| 创建任务、SSE、最终回答 | 能运行，但编排严重过度 |
| 取消、恢复 | 状态能切换，但恢复失败节点存在逻辑缺陷 |
| Memory / Skill / Knowledge / Capability / Artifact | 读取接口通过 |
| `npm run build` | 通过 |
| `npm run lint` | 失败：项目声明了脚本但没有安装 `eslint` |
| `pytest` | 18 passed，4 warnings |

### 1.2 内置浏览器限制

本次会话的 ChatGPT 内置浏览器没有暴露可连接实例，因此未能进行可信的点击、键盘、窗口缩放和截图测试。本文不把源码审查伪装成“已经目测”。

界面结论来自：

1. React/CSS 源码；
2. 成功生成的生产构建；
3. 真实 API/SSE 行为；
4. OpenAI 官方公开的 ChatGPT Work 产品行为。

后续代码智能体在提交 UI 改动前，必须补做 Playwright 或可用内置浏览器 E2E，并保存桌面宽屏、窄屏、移动端三组截图。

### 1.3 ChatGPT Work 的公开事实与合理推断

只能审查 OpenAI 公开的产品行为，不能声称掌握其专有前后端源码。

官方公开行为包括：

- 桌面端左上可在 ChatGPT 与 Codex 间切换；ChatGPT 内再切换 Chat 与 Work。
- Chat 用于快速问答，Work 用于端到端复杂任务。
- Chat 与 Work 共用 Recents，可筛选、排序、置顶。
- Projects、文件、插件、产物都进入同一工作上下文。
- Work 允许用户在运行中查看进度、回答问题、改变方向、批准重要操作。
- 插件可根据提示自动触发，也可在输入中用 `@` 明确指定。
- 支持在侧栏打开文档、表格、演示文稿和 PDF，但侧栏不是执行过程的唯一承载区。

官方参考：

- [ChatGPT Work and Codex](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)
- [ChatGPT desktop app experience updates](https://help.openai.com/en/articles/6825453-chatgpt-release)
- [ChatGPT Work 产品介绍](https://openai.com/index/chatgpt-for-your-most-ambitious-work/)
- [Work 中创建和编辑文件](https://help.openai.com/en/articles/20001278-creating-and-editing-documents-spreadsheets-and-presentations-with-chatgpt-work)
- [桌面端内置浏览器](https://help.openai.com/en/articles/20001277-using-the-built-in-browser-in-the-chatgpt-desktop-app)

对 OphAgent-Pro 的架构推断应明确标注为“目标设计”，不是对 OpenAI 私有实现的逆向结论。

---

## 2. 真实运行复现：简单问题为什么又慢又错

审计输入：

```text
1+1等于多少？请直接回答。
```

选择插件：`interactive_vqa`

真实结果：

| 指标 | 实测值 |
|---|---:|
| 总耗时 | 约 67 秒 |
| 模型调用 | 3 次 |
| 统计 token | 14,927 |
| 计划节点 | 4 个 |
| Supervisor | 约 32 秒 |
| ClinicalReasoning | 约 9 秒 |
| Evidence | 约 3 秒 |
| Report | 约 26 秒 |

系统返回的开头确实是“1+1等于2”，但随后强制生成一份长篇眼科结构化报告，并引用 6 条与算术无关的眼科文献。检索分数只有约 `0.004`–`0.015`，仍被当成证据使用。

这不是单纯的“模型慢”，而是以下问题叠加：

1. `app/runtime/planning.py:8-76` 为几乎所有插件固定构建同一套 DAG。
2. `interactive_vqa` 也必经临床信息抽取和医学检索。
3. Supervisor 使用带 Toolkit、Skill、PlanNotebook、最多 3 轮 ReAct 的重型 Agent，只为了输出 120 字摘要。
4. 检索器没有最低相关性阈值，永远尽量返回 `top_k`。
5. 所有成功任务都必须经过 `report` 节点才能被判定完成。
6. 报告提示词无条件要求结构化 Markdown、证据、不确定性、行动和免责声明。

### 2.1 历史失败证据

审计时仓库已有的两条真实失败 Run 均为：

```text
error_code = report_unavailable
report.error_code = budget_exceeded
```

| Run | 耗时 | 模型调用 | 总 token | 结果 |
|---|---:|---:|---:|---|
| 历史任务 A | 约 122 秒 | 4 | 32,306 | 最终报告失败 |
| 历史任务 B | 约 97 秒 | 5 | 27,781 | 最终报告失败 |

默认 token 预算是 24,000，但预算在模型返回后才累加和校验，见 `app/runtime/orchestrator.py:334-355`。因此任务可以先花到 27k 或 32k，再告诉用户“失败”。

默认时间预算是 300 秒，外部请求还允许超时和重试，所以用户观察到接近 5 分钟后失败与当前实现相符。

---

## 3. 目标产品模型

### 3.1 产品定位

主体：一个统一的 OphAgent 眼科诊疗增强助手。
受众：患者与临床人员使用同一产品界面；后台治理能力按角色授权。
单一核心任务：用户在一个连续对话中提出问题、提供影像或资料，并获得及时、可追踪、可复核的回答或产物。

内部可以有多个 Agent，但用户只面对一个 OphAgent。Agent 名称只应出现在管理员调试信息中，不应成为普通用户的主导航。

### 3.2 Chat 与 Work 的任务分层

不必照搬 OpenAI 的全产品切换器，但必须具备等价能力：

| 层级 | 适用任务 | 默认行为 | 目标 |
|---|---|---|---|
| Quick | 问候、算术、简单解释、非眼科问题 | 单模型直接回答或简短说明范围 | 首 token < 2.5 秒，总耗时 p50 < 8 秒 |
| Standard | 常规眼科问答、主诉整理、单次影像描述 | 1 次临床推理 + 按需并行插件 | p50 < 25 秒，p95 < 60 秒 |
| Deep Work | 多文件、报告、复杂鉴别、最新指南综合 | 动态 DAG、检查点、产物、可中途纠偏 | 进度透明，可暂停/继续 |
| Emergency | 红旗症状 | 本地规则立即给安全提示，再后台补充 | 首个安全提示 < 200 ms |

Quick 与 Standard 不应该先运行一个重型 Supervisor Agent。路由优先使用确定性规则；只有边界模糊时才调用轻量结构化分类模型。

### 3.3 默认能力与三个专业插件

通用问答、知识库检索和按需联网检索是每次任务都可使用的默认能力，不再占用插件入口。公开插件只保留需要专门输入输出契约的三项：

| 插件 ID | 用户名称 | 触发方式 | 必需输入 |
|---|---|---|---|
| `lesion_localizer` | 病灶定位 | `@病灶定位` 或检测到定位诉求 | 至少 1 张支持的眼科影像 |
| `aux_diagnosis` | 辅助评估 | 明确请求鉴别、风险或下一步 | 主诉；影像可选 |
| `report_generator` | 报告生成 | 明确请求报告或已有检查资料 | 文本、影像或文档至少一种 |

插件可以多选、自动激活或被 `@` 指定，不应是互斥智能体模式。前端只显示实际启用的专业插件；本地知识与联网检索作为执行阶段呈现，不伪装成插件。

---

## 4. 目标前端：ChatGPT Work 式信息架构

### 4.1 布局

```text
┌──────────────────────┬────────────────────────────────────────────┬─────────────────────┐
│ Logo  OphAgent       │ 对话标题 / 共享 / 更多                     │ 按需打开的详情抽屉   │
│ ＋ 新对话            ├────────────────────────────────────────────┤ 证据 / 产物 / 文件   │
│ 搜索                 │                                            │ 默认关闭              │
│ 最近                 │ 用户消息                                   │ 不承载唯一执行过程     │
│   对话 A             │                                            │                     │
│   对话 B             │ OphAgent                                   │                     │
│ 项目                 │ ┌ 执行中：正在检索指南…                 ┐ │                     │
│ 插件                 │ │ ✓ 整理问题  • 检索 6 条来源  ◌ 生成回答│ │                     │
│ 文件库               │ └ 可折叠的公开执行卡                    ┘ │                     │
│                      │ 回答正文、引用、产物卡                    │                     │
│                      │                                            │                     │
│ 账号 / 设置          │ [＋] [@插件]  向 OphAgent 提问… [语音][发送]│                     │
└────可拖动/可折叠─────┴────────────────────────────────────────────┴────按需可调整────────┘
```

### 4.2 执行过程必须回到消息流

删除“右栏才看得到执行详情”的信息层级。

每次 assistant 回复由以下顺序组成：

1. `ActivityCard`：紧跟在用户消息后，显示公开步骤。
2. `ClarificationCard`：需要补充信息时直接在消息中提问。
3. `ApprovalCard`：高影响动作在消息中请求批准。
4. `AssistantContent`：支持流式文本。
5. `ArtifactCard`：报告、影像标注、表格等产物。
6. `CitationGroup`：正文引用可点击，打开右侧证据详情抽屉。

任务完成后 ActivityCard 默认折叠成一行：

```text
已完成 · 使用了辅助评估和指南检索 · 3 个步骤 · 18 秒
```

右侧抽屉只用于查看：

- 证据全文、来源、版本、定位；
- 报告/PDF/影像产物预览；
- 文件和差异；
- 管理员调试信息。

### 4.3 左侧栏

当前 `frontend/src/styles.css:62-63` 把左栏固定为 248 px，没有 resize handle。

整改要求：

- 默认 260 px；
- 可拖动范围 220–420 px；
- 可折叠为 56 px 图标栏；
- 宽度和折叠状态持久化到 `localStorage`；
- 双击分隔线恢复默认宽度；
- 键盘可操作，handle 使用 `role="separator"`、`aria-orientation="vertical"`；
- 移动端用抽屉和汉堡按钮，不能像当前 `max-width:760px` 那样直接隐藏后无入口。

左栏顺序：

1. 品牌与新对话；
2. 全局搜索；
3. Recents，支持筛选、置顶、重命名、删除；
4. Projects；
5. Plugins；
6. Library；
7. 账号与设置。

“长期记忆、Skill 注册表、知识库治理、能力状态”应移入设置或管理员控制台，不能挤占所有用户的主导航。

### 4.4 输入框

目标行为：

- 圆角但克制，接近桌面原生输入区；
- 文本自动增高，设置最大高度；
- `Enter` 发送，`Shift+Enter` 换行，输入法组合态不误发；
- `+` 菜单：上传影像、上传文档、上传音频、从文件库选择；
- `@` 插件选择器；
- 语音按钮只有在 ASR 可用且真实接线后才显示；
- 运行时发送按钮变为停止按钮，但仍允许用户输入“改变方向”或回答澄清问题；
- 显示附件缩略图、类型、大小、上传状态和单个删除；
- 支持粘贴图片、拖放文件；
- 失败后保留草稿和附件。

当前 `frontend/src/App.tsx:367-370` 的语音按钮没有任何事件处理，属于虚假控件；必须接通或删除。

### 4.5 输出与消息

当前输出被包在大白卡、粗边框和 `OPHAGENT / FINAL` 工程标签中。改为 ChatGPT 式轻量消息流：

- 用户消息可用浅灰圆角气泡；
- assistant 正文直接落在内容列，不再整块卡片化；
- 内容列建议 760–860 px；
- Markdown 支持表格、代码、数学公式、脚注、引用；
- 每条回答底部提供复制、重试、赞/踩、朗读、更多；
- 错误不能只写“任务未能完成”，要说明失败节点、已保留内容、建议动作；
- 已经完成的中间产物不能因最终报告失败而全部丢失。

### 4.6 视觉系统

本产品应“行为与布局对齐 ChatGPT Work，品牌属于 OphAgent”，不要复制 OpenAI 标识。

建议 Token：

| Token | 值 | 用途 |
|---|---|---|
| `--bg-app` | `#F7F7F8` | 应用底色 |
| `--bg-canvas` | `#FFFFFF` | 对话画布 |
| `--bg-sidebar` | `#F1F1F1` | 左栏 |
| `--text-primary` | `#202123` | 主文字 |
| `--text-secondary` | `#6B6B6B` | 次级文字 |
| `--brand-cyan` | `#35A9D6` | 来自机器人 Logo 的蓝色，小面积使用 |
| `--danger` | `#C83B3B` | 医疗红旗与失败 |
| `--border` | `#E5E5E5` | 分隔线 |

字体：

- UI/正文：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif`
- 数据/Trace：`"SFMono-Regular", Consolas, monospace`
- 不再把宋体和全大写等宽英文作为主要品牌表达。

项目唯一的视觉签名应是提供的医生机器人，不再保留大面积“光圈仪表盘”装饰。执行进度可从 Logo 的青蓝色提取细线或小圆点，保持安静。

设计自检：最初可以考虑保留“视网膜扫描/光圈”作为医疗特色，但它会继续强化“监控台”和“AI 生成仪表盘”的观感，也与用户要求的 ChatGPT Work 式安静对话界面冲突。因此最终只保留机器人 Logo 这一处品牌记忆点，其他结构和动效都服从对话、进度与产物的可读性。

### 4.7 应用图标

用户指定源图：

```text
figures/system_logo.png
```

仓库中的 `app/static/icons/system_logo.png` 与它 SHA-256 完全一致，但当前界面没有实际使用这张图，而是用 `.brand-eye` 和 `.lens-mark` CSS 图形代替。

必须完成：

- 左栏品牌使用 `<img src="/static/icons/system_logo.png">`；
- 登录/启动页使用同一 Logo；
- `frontend/index.html` 增加 favicon 和 `apple-touch-icon`；
- 如打包桌面端，从此源图生成 `icns`、`ico` 和 Linux PNG；
- 原图是 299×382，生成系统图标时先置于透明方形画布，保留 8%–12% 安全区，禁止拉伸；
- 小尺寸 favicon 可从同一源图裁出机器人头部，提高 16–32 px 可识别性；
- 为 Logo 提供清晰的 `alt="OphAgent"`，纯装饰场景使用空 `alt`。

---

## 5. 前端问题与逐项解决方案

### FE-P0-01：不是多轮会话

证据：

- 前端只保存 `activeRun`，只渲染一条 user message 和一条 final answer。
- `conversation_id` 后端字段存在，但前端创建 Run 时不传。
- 旧 Conversation/Message 表和新 Run Store 完全分离。

影响：无法追问、纠偏、承接上下文，也无法像 ChatGPT Work 一样在同一线程中持续完成任务。

解决：

1. 引入 `Conversation`、`Message`、`MessagePart`、`Attachment`、`Run` 的统一接口。
2. `POST /conversations/{id}/messages` 创建用户消息，并按需产生 Run。
3. 一个 Conversation 可包含多个 Run；一个 assistant message 对应当前 Run 的可见输出。
4. 前端按消息数组渲染，不再按单个 Run 渲染。
5. 保留旧 API 兼容层，但停止维护两套事实源。

验收：

- 同一线程连续追问 5 轮，上下文、附件、插件产物不丢失。
- 刷新页面后消息顺序、执行卡和引用全部恢复。

### FE-P0-02：执行过程被错误固定在右栏

证据：`frontend/src/App.tsx:383-428` 把计划、证据、公开轨迹全部放入 `inspector`；主线程运行时只显示最后一个 `public_summary`。

解决：实现消息内 `ActivityCard`，消费同一事件流；右栏改为按需详情抽屉。

验收：

- 不打开右栏也能看懂任务正在做什么、是否卡住、如何停止或回应。
- 完成后执行卡自动折叠，点击可展开完整公开轨迹。

### FE-P0-03：历史任务丢失事件和证据

证据：`followRun` 先清空 `events/evidence`，随后对 completed/failed/cancelled 直接 return，见 `frontend/src/App.tsx:180-185`。

解决：

- 增加 `GET /runs/{id}/events?after=...` 的普通 JSON 查询或让 SSE 支持完整 replay。
- 打开任何历史任务时都加载事件、证据与产物。
- 前端按 event id 去重。

验收：刷新后打开完成任务，仍能看到使用过的插件、步骤、耗时、引用和产物。

### FE-P0-04：附件类型全部被当作影像

证据：UI 接受图片、PDF、TXT、MD、DOCX、音频，但 `createRun` 把所有上传路径都放入 `image_paths`，见 `frontend/src/App.tsx:234-235` 和 `frontend/src/api.ts:33-38`。

解决：

- 上传响应返回规范化 `kind: image|document|audio`、MIME、大小、attachment id。
- 创建消息只传 attachment id，后端负责安全解析和归类。
- 图像进入 imaging；文档进入 document parser；音频先转写。
- `.docx` 要么实现解析，要么从允许列表移除。

验收：分别上传 PNG、PDF、MD、MP3，执行图与事件均进入正确插件，不出现把 PDF 当 image URL 的情况。

### FE-P0-05：新建对话会被旧任务事件劫持

证据：“新建任务”只清状态，没有关闭当前 EventSource。旧任务完成后监听器会重新 `setActiveRun(updated)`。

解决：

- 切换会话或新建会话时取消订阅，或将订阅归属于 `conversationId/runId` scoped store。
- 允许后台任务继续，但只能更新自己的会话，不得改变当前路由。
- 用 React Query/Zustand 或 reducer 管理 entity，而不是单个全局 `busy/activeRun`。

验收：任务 A 在后台运行时新建任务 B，A 完成不会把界面自动切回。

### FE-P1-01：左栏不可缩放、不可折叠

按 4.3 实现 resizable/collapsible sidebar，并加入键盘和持久化测试。

### FE-P1-02：五插件被当成五种工作方式

移出主导航，进入 Plugin Directory、`@` 菜单和自动路由。用户面对一个 OphAgent。

### FE-P1-03：指定 Logo 未使用

按 4.7 替换 CSS 眼睛图形。不要只把文件复制进仓库而不绑定 UI 和桌面打包资源。

### FE-P1-04：没有流式回答

当前只有 `answer.completed`，用户长时间只能看三个跳动圆点。

解决：

- 增加 `message.delta` / `answer.delta` 事件；
- Markdown 增量渲染；
- 连接中断后按 cursor 续传；
- 如果 provider 不支持 token streaming，至少先发结构化摘要或首屏安全提示。

### FE-P1-05：SSE 不可恢复

当前 `source.onerror` 直接关闭并把 `busy` 设为 false，可能诱导用户重复提交。

解决：

- 事件使用单调递增序号；
- 支持 `Last-Event-ID` 和 `after` cursor；
- 指数退避重连；
- 服务端 heartbeat；
- 网络断开只显示“正在重连”，不得把服务端任务误判为空闲；
- 重连失败后继续轮询 Run 状态。

### FE-P1-06：右栏和移动端可访问性不足

问题：

- 抽屉没有关闭按钮、遮罩、Esc、焦点陷阱；
- 移动端左栏完全消失；
- 图标按钮依赖 `title`，缺少稳定的 `aria-label`；
- textarea 没有可访问名称；
- 没有针对输入法组合态的发送保护。

解决：补齐语义、键盘路径、焦点管理和 axe 测试。

### FE-P1-07：管理能力暴露给普通用户

普通患者无需看到 Skill checksum、模型 provider、索引治理和演化能力。

解决：

- 普通设置：插件、记忆、隐私、账户。
- 管理控制台：知识来源、Skill、Capability、演化。
- 路由与 API 同时按 RBAC 控制，不能只在前端隐藏。

### FE-P2-01：前端工程缺少质量门

问题：

- `App.tsx` 同时承担认证、导航、事件流、会话、插件和渲染。
- 没有组件测试、E2E、视觉回归。
- `npm run lint` 因缺失 `eslint` 直接失败。
- 前后端类型手写重复。

解决：

```text
frontend/src/
  app/
  features/auth/
  features/conversations/
  features/runs/
  features/plugins/
  features/artifacts/
  features/admin/
  components/ui/
  lib/api/
```

- 安装并配置 ESLint；
- 从 OpenAPI 生成 TypeScript types/client；
- Vitest + Testing Library；
- Playwright 覆盖关键路径；
- Storybook 或独立 preview 覆盖消息和状态组件。

---

## 6. 后端与编排问题及解决方案

### BE-P0-01：固定 DAG，完全忽略任务难度

证据：`build_plan` 始终创建 Supervisor、Evidence、Report，除知识库外还创建 Clinical。`PluginManifest.agent_graph` 只是声明，没有驱动计划。

解决：增加 `TaskRouter`，输出严格结构：

```python
class TaskRoute(BaseModel):
    intent: Literal[
        "quick_answer",
        "clinical_qna",
        "image_analysis",
        "aux_assessment",
        "report_generation",
        "knowledge_retrieval",
    ]
    complexity: Literal["quick", "standard", "deep"]
    risk: RiskLevel
    selected_plugins: list[PluginId]
    needs_clinical_state: bool
    needs_retrieval: bool
    needs_imaging: bool
    needs_report: bool
    reason_code: str
```

路由优先级：

1. 红旗规则；
2. 明确插件、附件和关键词规则；
3. 简单/非医疗 quick path；
4. 仅边界模糊时调用一次轻量分类模型。

计划必须从 `TaskRoute + PluginManifest` 生成，而不是写死。

### BE-P0-02：Quick path 缺失

实现：

- 问候、算术、简短解释：一次直接模型调用，禁用 Toolkit、PlanNotebook 和 ReAct。
- 明显超出产品范围的问题：简洁回答或说明范围，不触发眼科检索。
- 不创建“报告产物”，只创建普通 assistant message。
- 只有用户明确要报告时才运行 `ReportAgent`。

禁止为了显示“Agent 很努力”而制造计划节点。

### BE-P0-03：Supervisor 过重

当前 Supervisor 只是生成 120 字公开摘要，却使用带工具和最多 3 轮迭代的 ReActAgent。

解决：

- 大多数任务用确定性公开步骤文案；
- 边界复杂任务使用无工具、JSON 输出、`max_output_tokens <= 256` 的轻量调用；
- Supervisor 不得访问医学检索和联网搜索；
- Deep Work 才使用 PlanNotebook。

### BE-P0-04：预算在花完后才校验

解决：

- 每个计划先预留最终回答 token；
- 调用前检查 `remaining_calls`、`remaining_input_tokens`、`reserved_output_tokens`；
- 为每次 provider 调用设置 `max_output_tokens`；
- 使用 `asyncio.timeout(remaining_seconds)` 包裹节点；
- token 超限时压缩上下文或产出已有结果摘要，不能先超支再整体失败；
- 预算按 Quick/Standard/Deep 分层，不再所有插件共用 12 calls / 24k / 300s。

建议初值：

| 层级 | 模型调用 | 总 token | 时间 |
|---|---:|---:|---:|
| Quick | 1 | 2,000 | 15 s |
| Standard | 3 | 12,000 | 60 s |
| Deep | 8 | 32,000 | 300 s |
| Emergency 首屏 | 0 | 0 | 200 ms |

### BE-P0-05：失败恢复实际上不能恢复

证据：`resume()` 只把 RUNNING 和 CANCELLED 设回 PENDING，没有处理 FAILED。历史任务恰好都是 report FAILED。

另外，预算已超限的 Run 即使重置 report，也没有剩余预算。

解决：

- 根据 retry policy 把可重试 FAILED 节点重置为 PENDING；
- 不可重试错误明确要求修改输入或配置；
- 保留已完成节点输出；
- 为恢复创建新的 attempt，记录 attempt id；
- 对预算失败执行上下文压缩并分配独立的 recovery budget，或允许用户选择“生成精简回答”；
- 恢复 API 返回将重跑的节点列表。

验收：构造 report 超限，点击“精简后重试”，不重跑 Clinical/Evidence，最终成功生成精简答案。

### BE-P0-06：检索强制返回低相关结果

证据：算术问题仍返回 6 条眼科指南，相关分数接近 0。

解决：

- 路由判定不需要证据时完全不检索；
- 增加 absolute relevance threshold；
- BM25、向量、rerank 分数校准，不能把每次检索第一名归一化为 1 后忽略绝对质量；
- 设置最少命中词或领域门；
- 对同一来源做去重和 MMR；
- 低于阈值返回空列表，并显示“未找到足够相关证据”；
- 引用验证升级为 claim-evidence 对齐，不只是检查 `[ev_xxx]` 是否存在。

验收：

- “1+1”等非医疗问题返回 0 条眼科证据；
- 明确指南问题返回相关来源；
- 低相关检索不得进入报告 prompt。

### BE-P0-07：插件 Manifest 与实际执行脱节

例如 `report_generator` Manifest 的 agent graph 不含 Clinical，但固定 planner 仍加入 Clinical。

解决：

- Manifest 增加 activation、input schema、output schema、latency budget、fallback、permission、required/optional nodes；
- Planner 只能实例化 Manifest 声明允许的能力；
- 创建 Run 前验证 required input/capability；
- `lesion_localizer` 无影像时直接返回 422 或进入 `waiting_for_user`，不能生成普通文字报告冒充定位。

### BE-P0-08：所有成功都依赖最终 Report

当前 `_execute_inner` 只认 `report` 节点成功，否则整条 Run 失败。

解决：

- 按 intent 定义 terminal output：
  - quick_answer → answer node；
  - knowledge → evidence answer；
  - lesion → validated regions + explanation；
  - report → report artifact；
- optional node 失败时返回 partial success；
- 产物和已完成答案独立持久化；
- Run 增加 `completed_with_warnings` 或结构化 warnings。

### BE-P0-09：没有运行中交互、澄清和审批

`waiting_for_user` 枚举存在但没有实际使用。

解决：

- 增加 `run.question`、`run.approval_required` 事件；
- `POST /runs/{id}/input` 接收澄清或改变方向；
- `POST /runs/{id}/approve` 批准高影响动作；
- planner 支持 checkpoint；
- 用户追加输入后只更新受影响节点。

### BE-P1-01：Conversation、Run、Artifact 分裂

当前：

- SQLite 保存旧 Conversation/Message；
- JSON/JSONL 保存 Run/Event；
- Artifact 又单独保存 JSON；
- 新前端只使用 Run。

解决：

- 迁移到事务数据库；
- Conversation → Message → RunAttempt → Event/Artifact/Attachment 建立外键；
- 所有用户资源统一 ownership；
- 本地单机也使用 SQLite/PostgreSQL，而不是混合多套状态；
- 提供迁移脚本，不直接删除旧 API。

### BE-P1-02：SSE cursor 不是稳定事件序号

当前 `after` 实际是数组下标，event id 是随机 UUID，前端无法可靠使用 `Last-Event-ID`。

解决：事件增加单调 `sequence`；支持 replay、heartbeat、Last-Event-ID、终态重连。

### BE-P1-03：服务重启后任务不会自动恢复

Run 虽持久化，但 `_tasks` 只存在内存，lifespan 没有扫描 queued/running 状态。

解决：

- 启动时把中断的 RUNNING 标记为 INTERRUPTED；
- 按 retry policy 恢复或要求用户确认；
- 生产环境使用可靠队列和 worker lease；
- 节点执行要幂等。

### BE-P1-04：取消存在竞争和重复事件风险

API 线程与执行任务同时修改同一个 Run；取消时 task 也会在 `CancelledError` 中再写一次取消事件。

解决：

- CAS/version 字段或数据库行锁；
- cancel command 幂等；
- 只有状态机服务能推进状态；
- 每次转换验证合法前态；
- 终态事件 exactly-once。

### BE-P1-05：附件与医疗数据隐私

当前上传文件直接挂在公开 `/static/uploads` 下，没有资源 ownership 检查。UUID 降低猜测概率，但不等于访问控制。

解决：

- Attachment 表记录 user/conversation/message/checksum/MIME/size；
- 下载通过鉴权 API 或短时签名 URL；
- 静态服务不直接暴露患者上传；
- 删除会话时按策略级联删除上传与产物；
- 增加保留期、审计日志和加密策略；
- 禁止日志、Trace 和前端错误暴露患者全文。

### BE-P1-06：管理接口没有 RBAC

任何登录用户都可启停 Skill、修改知识来源状态、重建索引。

解决：

- User 增加 role/permissions；
- patient/clinician/admin 使用同一版本，但权限不同；
- 管理 API 需要 admin dependency；
- 写操作记录 actor、时间、前后值；
- 高风险治理动作需二次确认。

### BE-P1-07：红旗规则存在过宽正则与延迟提示

部分 `|` 组合会让单独“恶心”或“眼痛”过度触发；真正的红旗提示又要等最终报告。

解决：

- 给每个规则加括号和正反例测试；
- 区分“立即安全提示”和“最终风险分层”；
- `run.created` 后立刻发 `safety.alert`；
- 高风险任务失败也必须保留安全提示；
- 规则版本化并记录命中 reason code。

### BE-P2-01：认证与会话完整性

补充：

- 后端校验用户名和密码长度/复杂度；
- logout、会话撤销、密码修改；
- 生产环境 secure cookie、CSRF 防护、速率限制；
- 登录错误中文化且不泄露账号是否存在。

### BE-P2-02：可观察性缺少产品指标

必须记录但不记录患者原文：

- route/complexity/plugin；
- TTFT、总时长、各节点时长；
- provider timeout/retry；
- token、成本、缓存命中；
- retrieval 最高/最低分和被阈值过滤数；
- cancel、resume、partial success；
- SSE 重连次数；
- p50/p95 按 Quick/Standard/Deep 分层。

---

## 7. 推荐后端流程

```text
用户消息
  │
  ├─ 确定性 Safety Gate ──命中──> 立即 safety.alert
  │
  └─ TaskRouter
       │
       ├─ Quick ───────────────> DirectAnswer（1 call，无工具）
       │
       ├─ Standard ────────────> Clinical / Imaging / Retrieval 按需并行
       │                              └─ AnswerSynthesizer
       │
       └─ Deep Work ───────────> Dynamic Plan
                                      ├─ checkpoint / question / approval
                                      ├─ plugins
                                      └─ artifact builder
```

关键原则：

- 路由决定是否需要计划，不是所有消息先规划。
- 插件是能力，Agent 是内部实现。
- 检索、影像、报告都按需调用。
- 安全提示先于慢模型。
- 最终回答不是唯一成功产物。
- 每一步都可重放、可恢复、可审计但不暴露 chain-of-thought。

---

## 8. API 目标草案

```http
POST   /api/v1/conversations
GET    /api/v1/conversations?filter=&sort=&pinned=
GET    /api/v1/conversations/{id}
PATCH  /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}

POST   /api/v1/conversations/{id}/messages
GET    /api/v1/conversations/{id}/messages?after=

GET    /api/v1/runs/{id}
GET    /api/v1/runs/{id}/events?after_sequence=
POST   /api/v1/runs/{id}/cancel
POST   /api/v1/runs/{id}/resume
POST   /api/v1/runs/{id}/input
POST   /api/v1/runs/{id}/approve

POST   /api/v1/attachments
GET    /api/v1/attachments/{id}
DELETE /api/v1/attachments/{id}

GET    /api/v1/plugins
GET    /api/v1/artifacts
GET    /api/v1/artifacts/{id}
```

消息创建请求示例：

```json
{
  "content": "结合这份 OCT，说明可见异常和下一步。",
  "attachment_ids": ["att_xxx"],
  "requested_plugins": ["aux_diagnosis"],
  "mode": "auto",
  "idempotency_key": "client-generated-uuid"
}
```

服务器响应必须先持久化 message/run，再返回 202，避免请求断开后任务丢失。

---

## 9. 实施顺序

### Phase 0：建立回归基线

- 修复 ESLint 依赖。
- 增加简单问题、普通眼科问题、红旗、影像、报告、指南、取消、恢复基准用例。
- 保存当前延迟/token/失败率。
- 增加 Playwright 桌面与移动端 smoke test。

完成标准：CI 同时跑 Python、TypeScript、lint、unit、E2E。

### Phase 1：先修后端 P0

1. TaskRouter + Quick path；
2. 动态 planner；
3. 预算预检与输出上限；
4. 检索阈值；
5. terminal output 按 intent；
6. 失败恢复；
7. 立即安全提示。

完成标准：“1+1”不检索、不生成眼科报告、最多 1 次模型调用；历史预算失败可精简恢复。

### Phase 2：统一会话和事件模型

- 合并 Conversation/Message/Run/Artifact；
- 事件 sequence、replay 和断线续传；
- running input/checkpoint；
- 上传资源 ownership。

完成标准：刷新、切换线程、服务重启后，消息与运行状态一致。

### Phase 3：重做 ChatGPT Work 式前端

- 可缩放左栏；
- 多轮消息流；
- 内联 ActivityCard；
- 流式回答；
- 插件选择器；
- 右侧按需证据/产物抽屉；
- 指定 Logo 与应用图标；
- 错误、空态、移动端、无障碍。

完成标准：不打开右栏也能完成完整任务；五项能力只以插件出现。

### Phase 4：权限、管理与桌面化

- patient/clinician/admin RBAC；
- 管理控制台；
- 文件私有访问与保留策略；
- 如果产品明确要求桌面安装，再引入 Tauri/Electron 壳、原生菜单、文件授权和打包图标。

不建议在后端稳定前先做桌面打包。

---

## 10. 必须新增的自动化测试

### 10.1 编排

- `test_quick_math_uses_one_call_no_retrieval_no_report`
- `test_greeting_uses_quick_path`
- `test_non_medical_query_has_no_ophthalmic_evidence`
- `test_guideline_query_activates_knowledge_plugin`
- `test_report_request_activates_report_plugin`
- `test_localizer_requires_image`
- `test_standard_query_skips_unneeded_nodes`
- `test_emergency_alert_emitted_before_model_call`
- `test_budget_reserved_for_terminal_output`
- `test_budget_failure_can_resume_failed_node`
- `test_optional_tool_failure_returns_partial_success`

### 10.2 检索

- 低相关问题返回空证据；
- 相关问题通过阈值；
- 同来源去重；
- 过期/已替代来源不误用；
- 引用 claim-evidence 对齐；
- embedding/rerank 失败时真实 BM25 降级。

### 10.3 会话与流

- 多轮消息恢复；
- SSE 断线续传无重复、无丢失；
- 新建会话不会被后台 Run 劫持；
- completed Run 重新打开仍有证据和轨迹；
- 取消、恢复、重复取消幂等；
- 服务重启恢复策略。

### 10.4 前端

- sidebar drag/collapse/persist；
- ActivityCard inline；
- plugin `@` picker；
- 图片/文档/音频分类；
- 输入法组合态；
- 键盘焦点和 Esc；
- 移动端导航；
- axe 无严重可访问性问题；
- 视觉回归覆盖 empty/running/waiting/completed/partial/failed。

### 10.5 权限与隐私

- 用户 A 无法读取用户 B 的 run/event/artifact/attachment；
- 普通用户无法调用管理写接口；
- `/static/uploads/...` 不再公开访问；
- 删除会话按策略删除关联文件；
- Event 与 Trace 不包含 prompt、密钥或隐藏推理。

---

## 11. 最终验收指标

### 体验

- 左栏可拖动、折叠、持久化。
- 指定机器人 Logo 出现在品牌区、启动页和应用图标。
- 五项能力只作为插件出现。
- 运行进度在回答消息内可见。
- 右栏默认关闭，只看证据/产物详情。
- 同一会话可连续追问、纠偏、补资料。

### 性能与编排

- Quick：1 次模型调用，不检索，p50 < 8 秒，p95 < 15 秒。
- Standard：不超过 3 次模型调用，p95 < 60 秒。
- 非医疗问题不产生眼科引用。
- 最终节点预算失败率 < 1%。
- 断线恢复成功率 > 99%。
- 红旗首屏提示 < 200 ms。

### 正确性与安全

- 无低相关证据硬引用。
- 无影像不运行病灶定位。
- 可选能力失败不会抹掉已完成结果。
- 恢复只重跑必要节点。
- 普通用户不能进入治理 API。
- 上传的医疗资料必须鉴权访问。

### 工程质量

以下命令全部成功：

```bash
./venv/bin/pytest
./venv/bin/python -m compileall -q app
cd frontend
npm run lint
npm run build
npm run test
npm run test:e2e
```

---

## 12. 代码智能体执行约束

重构时必须遵守：

1. 保留五个公开 plugin ID，迁移其产品语义，不删除兼容性。
2. 不向前端暴露隐藏 chain-of-thought，只显示 `public_summary` 和结构化公开步骤。
3. 不使用 Mock、随机概率、预设诊断、伪造坐标或虚假证据填补生产失败。
4. 红旗安全门不能因 Quick path 被绕过。
5. 患者与医生使用同一前端版本；权限差异由 RBAC 和数据范围表达。
6. 不在一次提交中同时重写数据层、编排器和全部 UI；按 Phase 小步迁移。
7. 每个修复必须附对应测试和可观测指标。
8. 保留取消、恢复、重连和能力不可用状态。
9. 不把右栏重新做成新的“Agent 调试器”；普通用户首先看到对话和结果。
10. UI 行为对齐 ChatGPT Work，但使用 OphAgent 的 Logo、文案和医疗安全边界。
