# ChatGPT Work 重构完成矩阵

> 核对基准：`docs/CHATGPT_WORK_REFACTOR_GUIDE.md`
> 核对日期：2026-07-29
> 对话开始前基线：Git commit `658d23c`，安全分支 `backup/chat-start-658d23c`

## 1. 用户覆盖的两项原指南要求

本轮有两项明确用户决策优先于原指南：

1. DetailDrawer 只展示产物，不展示证据。证据改为回答内联 `CitationGroup`，所有公开执行步骤进入消息流。
2. 当前为本地研究原型，所有登录用户均可使用记忆、知识库、Skill 和能力管理；不按 patient/clinician/admin 限制功能。治理写操作仍记录无患者正文的审计日志。

这两项不是遗漏，而是有意覆盖。

## 2. 前端

| 编号 | 状态 | 实现 |
|---|---|---|
| FE-P0-01 多轮会话 | 完成 | Conversation 下包含多个 Run；后端将同会话历史打包为持久化 context snapshot，最近轮次保留原文、旧轮次代码压缩，并支持追问路由、补充输入与刷新恢复 |
| FE-P0-02 执行固定在右栏 | 完成 | ActivityCard 位于消息流；右栏只接受 Artifact |
| FE-P0-03 历史事件丢失 | 完成 | 打开会话时重载 Run Event、Artifact 与 sequence cursor |
| FE-P0-04 附件类型错误 | 完成 | image/document/audio 分型、私有 Attachment、正确 DAG |
| FE-P0-05 旧任务劫持新会话 | 完成 | active conversation id 守卫 SSE 更新 |
| FE-P1-01 左栏 | 完成 | 220–420 px 拖动、56 px 折叠、localStorage、键盘 separator、移动抽屉 |
| FE-P1-02 插件语义 | 完成 | 问答与知识检索为默认能力；病灶定位、辅助评估、报告生成三个专业插件可 `@` 多选或自动组合 |
| FE-P1-03 Logo 与图标 | 完成 | 品牌、登录、加载、assistant mark、favicon、apple touch icon |
| FE-P1-04 流式回答 | 完成 | provider delta → `answer.delta` → React 增量正文 |
| FE-P1-05 SSE 恢复 | 完成 | sequence、Last-Event-ID、replay、heartbeat、指数退避 |
| FE-P1-06 可访问性 | 完成 | Focus trap、Esc、ARIA、移动导航；axe serious/critical 为 0 |
| FE-P1-07 管理入口 | 用户覆盖 | 登录用户均可使用；全部入口恢复且写操作留审计 |
| FE-P2-01 工程质量门 | 完成 | ESLint、Vitest、Playwright、axe、TypeScript、生产构建 |

额外完成：

- 真实 MediaRecorder → 服务端 Fun-ASR-Flash 转写；
- 语音对话自动执行“录音 → ASR → 发送 → Agent → Qwen3-TTS → WAV 播放”，手动播放器支持再次点击立即停止；
- 长回答按句切分为符合 TTS 服务端限制的片段并顺序播放，停止后不会继续请求或播放后续片段；
- 修复 `/v1` 基础 URL 被误当最终音频 endpoint 的 404；
- 提交锁与后台运行状态分离，运行中可停止旧 Run 并按新方向继续；
- 回答支持替换式重新生成、历史版本切换、点赞/点踩持久化、删除以及 MD、PDF、DOCX、JPG 导出；
- 插件显示实际名称；Composer 的 Skill 按钮选择已验证并启用的 Skill，导入与验证归入 Skill 工作区；
- ActivityCard 只按进度追加已开始步骤，关键过程与结果使用默认收起的分步卡片展示；
- 计时从 Run 被接受开始并以不可变终止事件冻结，不受点赞等后续更新影响；
- 用户附件在发送前和用户消息内均显示预览；附件菜单支持多选并在选择后自动关闭；
- 右侧文档工作区可调宽、编辑 Markdown、实时预览、自动保存和四格式导出；
- 页面字号按用户最终要求统一为原设计的 1.2 倍；
- 所有按钮、图标操作、菜单 `summary` 和格式导出入口具有统一中文悬浮说明，键盘聚焦同样可见；
- 设置页支持每个用户独立覆盖 Agent、Sub-agent、ASR、TTS、Embedding、Reranker、搜索和 MinerU Token；密钥加密落库且不回显，可随时恢复系统默认；
- Projects 创建/删除及对话归档；
- 文件库复用既有附件；
- 密码修改后撤销所有会话。

## 3. 后端与 Harness

| 编号 | 状态 | 实现 |
|---|---|---|
| BE-P0-01 动态 DAG | 完成 | `TaskRoute + PluginManifest` 构建 Quick/Standard/Deep DAG |
| BE-P0-02 Quick path | 完成 | 算术/问候单次 DirectAnswer，不检索、不产报告 |
| BE-P0-03 Supervisor 过重 | 完成 | Quick/Standard 不运行 Supervisor；公开计划来自确定性节点 |
| BE-P0-04 预算预检 | 完成 | 调用前检查 calls/token/reserved output/time，分层预算且任何路径不得越过全局上限 |
| BE-P0-05 恢复 | 完成 | FAILED/RUNNING/CANCELLED 节点可重置，保留已完成节点，attempt 递增 |
| BE-P0-06 低相关检索 | 完成 | absolute threshold、领域门、去重、空证据真实降级 |
| BE-P0-07 Manifest 脱节 | 完成 | activation/latency/fallback/permission/nodes；planner 拒绝清单外能力 |
| BE-P0-08 terminal 固定 Report | 完成 | answer/report 按 intent；optional failure → completed_with_warnings |
| BE-P0-09 运行中交互 | 完成 | question/input/approve/cancel/resume 与 checkpoint 状态 |
| BE-P1-01 分裂存储 | 完成（本地版） | Run/Event/Artifact/Attachment 迁入 SQLite WAL；旧 JSON 幂等导入 |
| BE-P1-02 SSE cursor | 完成 | 数据库单调 sequence、唯一 final、replay/heartbeat |
| BE-P1-03 重启恢复 | 完成（单进程） | 启动时扫描并标记 interrupted；可恢复执行 |
| BE-P1-04 取消竞争 | 完成（单进程） | version、事务写、幂等 cancel、唯一终态事件 |
| BE-P1-05 文件隐私 | 完成 | user ownership、鉴权下载、私有路径、删除清理 |
| BE-P1-06 RBAC | 用户覆盖 | 所有登录用户可管理；User.role 保留，治理写入 AuditLog |
| BE-P1-07 红旗延迟 | 完成 | 模型前立即 `safety.alert`；显式 Quick 也不能覆盖高风险；候选稿经 Critic 审查后再生成终稿 |
| BE-P2-01 认证完整性 | 完成 | 输入校验、中文统一错误、速率限制、SameSite/secure cookie、Origin CSRF、JWT jti 撤销、密码修改 |
| BE-P2-02 可观察性 | 完成 | route、complexity、node duration、TTFT、tokens、partial success、retrieval score；不记录患者全文 |

医疗增强：

- HIGH/EMERGENCY 自动进入 Deep；
- 按关键词选择眼底、青光眼、角膜、神经眼科、儿童眼病或综合眼科；
- 每个专科使用独立 Agent 实例，防止并发 memory 交叉；
- 最多两个专科，控制 token 和延迟；
- 高风险先生成候选稿，Critic 实际审查候选稿，最终回答按审查意见重新生成。
- 定义型眼科问题直接进入知识检索路径，优先本地指南/共识并补充联网来源；
- 来源按指南、共识、专业医学站点、普通网页排序，低可信来源仅在没有高质量证据时回退；
- 提示语不设置字数、段数、章节数约束；上下文打包、预算预检、引用完整性和安全边界由代码执行；
- 模型已返回的正文不会因后处理异常或预算告警被丢弃，非致命问题记录为 `completed_with_warnings`；
- 重试只携带必要问题与高价值上下文，不复制整段执行历史。
- 个人供应商配置在每个 Run 创建独立客户端并使用 `ContextVar` 隔离，不会把一名用户的端点泄漏到并发 Run。
- 回答与文档导出会把内部证据 ID 转换为编号，并追加来源标题、链接、定位和采用文本。
- 单个附件解析后不会再被 `attachment_ids` 与 typed path 重复计数；单图定位/评估保持 Standard，避免无必要 Deep 和专科复核。
- 病灶定位输出只接受 `ImageRegion` 校验通过的模型坐标；空坐标在原图卡和最终正文中明确披露，不补造边界。
- 辅助评估独立消费 ClinicalState、影像观察、文档与证据，输出定性支持程度及支持/反对/缺失项，不生成疾病概率。
- 上传事实与定位状态由代码注入并校验；下游模型不得把已上传影像写成“未提供图像”，无确证分期和直接治疗指令会被代码收敛。

持续改进 Harness：

- 去内容化在线信号只记录 Run 指纹、终态、错误码、风险、实际插件/Skill ID、聚合成本与反馈；不保存 query、answer、附件、证据正文、用户 ID 或临床字段。
- 用户反馈使用每 Run 当前值进行 reconciliation，切换或取消不会重复累计。
- 临床病史、用药和过敏不按粗粒度回答反馈重排，负反馈不降低任何 Memory 权重；只有已确认非临床偏好在最小样本和正反馈率达标后可获得最高 +15% 增益。
- Memory 候选拒绝、召回负反馈、真实 Skill 使用负反馈和重复技术错误形成去内容化离线候选；线上不会修改 Prompt、Skill、代码或安全策略。
- 去内容化候选可转换为正式 `EvolutionProposal`，但该操作只生成离线提案元数据，不会自动创建修改或绕过后续阶段。
- 候选沿用独立 Git worktree、路径白名单、冻结 commit、候选不可见 sealed tests 和候选进程外 HMAC attestation。
- 官方 A-Evolve 0.1.0 与 GEPA 0.1.1 已由固定源码安装；独立 sealed-test 共 12 例，三类切片各 4 例，控制器强制校验 manifest、完整病例集合与防泄漏策略。
- 晋升新增全切片非劣、已通过病例不失败、高风险单病例不降分、医疗安全/引用/关键错误和最小切片样本门禁。
- 默认最小平均提升为 0.01；即使所有自动门禁通过，仍需签名人工审批且绑定当前 candidate commit。
- 设置页只读展示持续改进状态和候选；生产自动变更明确关闭。研究依据见 `docs/SELF_EVOLUTION_HARNESS_RESEARCH.md`。

## 4. 验证结果

```text
./venv/bin/pytest -q                 61 passed
./venv/bin/python -m compileall -q app
npm run lint                         passed
npm run build                        passed
npm run test                         5 passed
Playwright E2E                      4 passed，8 个按环境/视口跳过
Playwright 真实 GUI 操作             passed，详见 GUI_TEST_REPORT
git diff --check                     passed
```

本轮 Playwright 真实前后端操作覆盖：

- 从 Composer 发送“什么是青光眼？”并等待真实模型回答；
- 重试替换当前回答、历史版本切换、点赞持久化、不透明三点菜单和四种导出；
- TTS 实际请求、播放状态切换和再次点击停止；模拟麦克风录音状态机，以及合成 WAV 经真实 ASR 得到正确转写；
- 插件名称、Skill 选择器、执行步骤逐步追加/展开和引用悬停原文；
- 多文件上传、用户消息附件预览、发送/停止按钮互换；
- 文档转换、编辑、实时预览、自动保存、调宽和导出；
- 八类个人供应商保存、刷新持久化和恢复系统默认；
- 指南优先排序、回答引用和 token 统计；
- 1440×1000 最终视觉截图，字号为原设计的 1.2 倍。

此前响应式回归还覆盖 980×780 桌面窄屏和 iPhone 13 移动视口。

## 5. 生产部署边界

当前完成的是安全边界明确的本地研究原型。若进入多实例或真实临床部署，仍需新增：

- PostgreSQL + 可靠队列 + worker lease；
- KMS/磁盘加密、备份恢复、数据保留期任务；
- 机构级 RBAC/ABAC、二次确认和审计导出；
- 医疗器械、隐私、网络安全与临床验证流程；
- 真实业务流量下的 p50/p95 指标验收。
