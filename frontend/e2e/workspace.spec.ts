import { expect, test, type Page } from "@playwright/test";
import axe from "axe-core";

const run = {
  id: "run_visual",
  trace_id: "trace_visual",
  status: "completed",
  risk_level: "routine",
  route: {
    intent: "knowledge_retrieval",
    complexity: "standard",
    selected_plugins: [],
    reason_code: "deterministic_knowledge_retrieval"
  },
  input: {
    query: "糖尿病视网膜病变随访需要关注什么？",
    plugin_id: "knowledge_base",
    conversation_id: 1,
    attachment_ids: [],
    image_paths: [],
    document_paths: [],
    audio_paths: []
  },
  plan: [
    { id: "evidence", title: "检索可追踪医学证据", agent: "EvidenceAgent", capability: "medical_retrieval", depends_on: [], status: "completed", required: true },
    { id: "answer", title: "生成回答", agent: "AnswerSynthesizer", capability: "main_model", depends_on: ["evidence"], status: "completed", required: true }
  ],
  answer: "应结合**视力、眼底和 OCT**进行复核，并由眼科医生根据分期确定随访间隔。[ev_visual]",
  warnings: [],
  attempt: 1,
  budget: { model_calls: 1, prompt_tokens: 300, completion_tokens: 120, max_model_calls: 3, max_tokens: 12000 },
  created_at: "2026-07-28T06:00:00Z",
  updated_at: "2026-07-28T06:00:12Z"
};

const evidence = [{
  id: "ev_visual",
  title: "糖尿病视网膜病变临床诊疗指南",
  source: "https://example.test/guideline",
  excerpt: "随访评估应结合视力、眼底检查、黄斑 OCT 与疾病分期。",
  locator: "随访章节，第 4 段",
  source_status: "current",
  source_type: "guideline",
  score: 0.92
}];

const artifact = {
  id: "artifact_visual",
  run_id: run.id,
  type: "report",
  title: "视网膜随访摘要",
  mime_type: "text/markdown",
  content: "# 视网膜随访摘要\n\n这是可下载、可复核的正式产物。",
  metadata: { plugin_id: "report_generator" }
};

const events = [
  { id: "evt_1", sequence: 1, run_id: run.id, trace_id: run.trace_id, type: "run.created", public_summary: "任务已创建", timestamp: "2026-07-28T06:00:00Z", data: {} },
  { id: "evt_2", sequence: 2, run_id: run.id, trace_id: run.trace_id, type: "retrieval.result", public_summary: "检索到 1 条可追踪证据", timestamp: "2026-07-28T06:00:04Z", duration_ms: 4000, data: { evidence } },
  { id: "evt_3", sequence: 3, run_id: run.id, trace_id: run.trace_id, type: "run.completed", public_summary: "任务执行完成", timestamp: "2026-07-28T06:00:12Z", duration_ms: 8000, data: {} }
];

async function mockWorkspace(page: Page) {
  await page.route("**/auth/me", (route) => route.fulfill({ json: { id: 1, username: "视觉测试用户", role: "patient" } }));
  await page.route("**/api/v1/conversations?*", (route) => route.fulfill({
    json: { items: [{ id: 1, title: "视网膜病变随访", agent_type: "interactive_vqa", created_at: "2026-07-28T06:00:00Z", pinned: true }], total: 1, skip: 0, limit: 100 }
  }));
  await page.route("**/api/v1/conversations/1", (route) => route.fulfill({
    json: { id: 1, title: "视网膜病变随访", agent_type: "interactive_vqa", created_at: "2026-07-28T06:00:00Z", pinned: true, messages: [], runs: [run] }
  }));
  await page.route(`**/api/v1/runs/${run.id}/events?*`, (route) => route.fulfill({ json: events }));
  await page.route(`**/api/v1/artifacts?run_id=${run.id}`, (route) => route.fulfill({ json: [artifact] }));
  await page.route(`**/api/v1/artifacts/${artifact.id}`, async (route) => {
    const payload = route.request().postDataJSON() as { title?: string; content?: string };
    await route.fulfill({ json: { ...artifact, ...payload } });
  });
  await page.route("**/api/v1/capabilities", (route) => route.fulfill({ json: [
    { id: "main_model", configured: true, status: "ready", required: true, provider: "OpenAI-compatible" },
    { id: "asr", configured: true, status: "ready", required: false, provider: "ASR" }
  ] }));
  await page.route("**/api/v1/projects", (route) => route.fulfill({ json: [
    { id: 8, name: "黄斑随访", description: "随访上下文", color: "#35A9D6", conversation_count: 1, created_at: "2026-07-28T06:00:00Z", updated_at: "2026-07-28T06:00:00Z" }
  ] }));
  await page.route("**/api/v1/attachments", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/artifacts", (route) => route.fulfill({ json: [artifact] }));
  await page.route("**/api/v1/memories/preference", (route) => route.fulfill({ json: { enabled: true } }));
  await page.route("**/api/v1/memories", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/skills", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/provider-config", (route) => route.fulfill({ json: {
    mineru_url: "https://mineru.net/api/v1/agent/parse/file",
    providers: Object.fromEntries(
      ["agent", "sub_agent", "asr", "tts", "embedding", "reranker", "search", "mineru"]
        .map((id) => [id, {
          use_default: true,
          url: "",
          model: "",
          has_api_key: false,
          default_url: id === "mineru" ? "https://mineru.net/api/v1/agent/parse/file" : "https://provider.example/v1",
          default_model: ["search", "mineru"].includes(id) ? "" : "test-model",
          default_configured: true
        }])
    )
  } }));
  await page.route("**/api/v1/evolution/status", (route) => route.fulfill({ json: {
    enabled: true,
    mode: "observe_and_gate",
    signal_count: 12,
    feedback_count: 4,
    observed_run_count: 8,
    ready_candidate_count: 1,
    memory_adaptation: "仅对重复获得正反馈的已确认偏好做有界增益（+15%）；临床记忆不按粗粒度反馈重排，负反馈不降权",
    skill_adaptation: "只生成去内容化候选；隔离评测并经人工批准后才可晋升",
    production_mutation: "disabled",
    human_approval_required: true,
    candidates: [{
      id: "continuous_test",
      kind: "skill",
      target: "guideline_retrieval",
      sample_size: 3,
      negative_rate: 0.67,
      trigger: "该技能关联回答的重复负反馈达到候选门槛",
      allowed_mutation_paths: ["skills/guideline_retrieval/"],
      status: "ready_for_offline_evaluation",
      requires_human_approval: true,
      created_at: "2026-07-29T00:00:00Z",
      updated_at: "2026-07-29T00:00:00Z"
    }]
  } }));
  await page.route("**/api/v1/knowledge/status", (route) => route.fulfill({ json: {
    status: "ready", documents: 2, chunks: 12, vectors: 12, page_visuals: 1, graph_edges: 4
  } }));
  await page.route("**/api/v1/knowledge/sources", (route) => route.fulfill({ json: [] }));
}

async function expectNoSeriousAccessibilityViolations(page: Page) {
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const result = await window.axe.run(document, {
      resultTypes: ["violations"]
    });
    return result.violations
      .filter((item) => item.impact === "serious" || item.impact === "critical")
      .map((item) => ({
        id: item.id,
        impact: item.impact,
        nodes: item.nodes.map((node) => ({
          target: node.target,
          html: node.html,
          summary: node.failureSummary
        }))
      }));
  });
  expect(violations).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "视网膜病变随访" })).toBeVisible();
});

test("桌面端支持克制进度、技能选择、可编辑产物和侧栏键盘调整", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "桌面视口专用");
  await expect(page.getByText("已完成", { exact: true })).toBeVisible();
  await expect(page.getByText("应结合视力、眼底和 OCT")).toBeVisible();
  await expect(page.getByText("执行与证据")).toHaveCount(0);

  const separator = page.getByRole("separator", { name: "调整侧栏宽度" });
  await separator.focus();
  await separator.press("ArrowRight");
  await expect(separator).toHaveAttribute("aria-valuenow", "270");

  await page.getByRole("main").getByRole("button", { name: "插件" }).click();
  await expect(page.getByRole("button", { name: /病灶定位/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: /病灶定位/ })).toHaveCount(0);

  await page.getByRole("main").getByRole("button", { name: "技能" }).click();
  await expect(page.getByText("只列出已验证并启用的技能")).toBeVisible();
  await expect(page.locator(".skill-menu input[type=file]")).toHaveCount(0);
  await page.keyboard.press("Escape");

  await page.locator(".citation-group summary").click();
  await expect(page.getByText("随访章节，第 4 段")).toBeVisible();
  await expect(page.getByRole("dialog", { name: "证据详情" })).toHaveCount(0);

  await page.getByRole("button", { name: "视网膜随访摘要" }).click();
  const drawer = page.getByRole("dialog", { name: "文档工作区" });
  await expect(drawer).toBeVisible();
  await expect(drawer.locator(".document-preview").getByText("这是可下载、可复核的正式产物。", { exact: true })).toBeVisible();
  await drawer.getByLabel("编辑文档内容").fill("# 已编辑\n\n实时预览内容");
  await expect(drawer.getByRole("heading", { name: "已编辑" })).toBeVisible();
  await drawer.getByLabel("导出文档").click();
  await expect(drawer.getByRole("link", { name: "MD" })).toBeVisible();
  await expect(drawer.getByRole("link", { name: "PDF" })).toBeVisible();
  await expect(drawer.getByRole("link", { name: "DOCX" })).toBeVisible();
  await expect(drawer.getByRole("link", { name: "JPG" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "文档工作区" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "语音输入" })).toBeVisible();
  await expect(page.getByRole("button", { name: "实时语音模式" })).toBeVisible();
  await expect(page.locator(".composer textarea")).toHaveCSS("font-size", "16.8px");
  await page.getByRole("main").getByRole("button", { name: "技能" }).hover();
  await expect(page.getByRole("tooltip")).toHaveText("选择本次任务使用的技能");
  await expectNoSeriousAccessibilityViolations(page);

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.screenshot({ path: testInfo.outputPath("desktop-wide.png"), fullPage: true });
  await page.setViewportSize({ width: 980, height: 780 });
  await page.screenshot({ path: testInfo.outputPath("desktop-narrow.png"), fullPage: true });
});

test("项目、文件、插件、记忆、知识库和技能入口都可实际打开", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "桌面视口专用");
  const checks = [
    ["项目", "项目"],
    ["文件库", "文件库"],
    ["插件", "插件"],
    ["记忆", "长期记忆"],
    ["知识库", "知识库与来源"],
    ["技能", "Skill 注册表"],
    ["设置", "设置"]
  ] as const;
  for (const [navigation, heading] of checks) {
    await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: navigation, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading, exact: true }).first()).toBeVisible();
  }
  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "技能", exact: true }).click();
  await expect(page.getByText("系统级 Skill 由管理员维护")).toBeVisible();
  await expect(page.getByText("导入候选 SKILL.md")).toHaveCount(0);
  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "知识库", exact: true }).click();
  await expect(page.getByRole("button", { name: "重建向量索引" })).toHaveCount(0);
  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByRole("region", { name: "持续改进状态" })).toContainText("生产自动变更：关闭");
  await expect(page.getByRole("region", { name: "持续改进状态" })).toContainText("待离线评测候选");
});

test("移动端导航有明确入口并可关闭", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "desktop", "移动视口专用");
  await expect(page.getByRole("button", { name: "打开导航" })).toBeVisible();
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("button", { name: "新对话", exact: true })).toBeVisible();
  await page.locator(".mobile-close").click();
  await expect.poll(async () => (await page.locator(".sidebar").boundingBox())?.x || 0).toBeLessThan(-250);
  await expect(page.getByRole("button", { name: "向 OphAgent 提问" })).toHaveCount(0);
  await expect(page.getByLabel("向 OphAgent 提问")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile.png"), fullPage: true });
});
