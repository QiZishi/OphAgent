import { expect, test, type Page } from "@playwright/test";

async function register(page: Page, prefix: string) {
  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  await page.goto("/");
  await page.getByRole("button", { name: "还没有账号？创建一个" }).click();
  await page.getByLabel("用户名").fill(`${prefix}_${suffix}`);
  await page.getByLabel("密码").fill("Visual-test-2026");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("heading", { name: "今天想先处理什么？" })).toBeVisible();
}

async function selectReportPlugin(page: Page) {
  await page.getByRole("main").getByRole("button", { name: "插件" }).click();
  await page.locator(".plugin-menu").getByRole("button", { name: /^报告生成/ }).click();
  await page.keyboard.press("Escape");
}

async function currentConversation(page: Page) {
  return page.evaluate(async () => {
    const listing = await fetch("/api/v1/conversations?limit=100").then((response) => response.json());
    return fetch(`/api/v1/conversations/${listing.items[0].id}`).then((response) => response.json());
  });
}

test("真实模型运行中可排队追加，并在下一节点前应用", { tag: "@desktop" }, async ({ page }) => {
  test.skip(!process.env.RUN_LIVE_AGENT_E2E, "仅在显式启用真实模型验收时运行");
  test.setTimeout(300_000);
  const failedResponses: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) failedResponses.push(`${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await register(page, "live_queue");
  await selectReportPlugin(page);
  const composer = page.getByLabel("向 OphAgent 提问");
  await composer.fill("请检索可追踪证据，详细整理青光眼随访评估，并生成结构化报告。");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止当前任务" })).toBeVisible();
  await expect(page.getByRole("button", { name: /排队追加/ })).toBeVisible();

  await composer.fill("追加要求：最终报告只保留三个编号要点，并把检查项目放在第一点。");
  const queuedResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/interventions")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "将新要求排队发送" }).click();
  expect((await queuedResponse).status()).toBe(202);
  await expect(page.locator(".intervention-message").getByText(/最终报告只保留三个编号要点/)).toBeVisible();
  await expect(page.getByRole("button", { name: "重新生成回答" }).first()).toBeVisible({
    timeout: 240_000,
  });

  const conversation = await currentConversation(page);
  expect(conversation.runs).toHaveLength(1);
  const run = conversation.runs[0];
  expect(run.status).toMatch(/^completed/);
  expect(run.interventions).toHaveLength(1);
  expect(run.interventions[0].status).toBe("applied");
  expect(run.interventions[0].content).toContain("最终报告只保留三个编号要点");
  expect(run.input.query).not.toContain("【用户在执行期间追加的要求");
  const events = await page.evaluate(
    (runId) => fetch(`/api/v1/runs/${runId}/events`).then((response) => response.json()),
    run.id,
  );
  expect(events.some((event: { type: string }) => event.type === "user.intervention_applied")).toBe(true);
  expect(events.some((event: { type: string }) => event.type === "run.cancelled")).toBe(false);
  expect(failedResponses).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test("真实模型运行中可立即打断并从检查点自动恢复", { tag: "@desktop" }, async ({ page }) => {
  test.skip(!process.env.RUN_LIVE_AGENT_E2E, "仅在显式启用真实模型验收时运行");
  test.setTimeout(300_000);
  const failedResponses: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) failedResponses.push(`${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await register(page, "live_interrupt");
  await selectReportPlugin(page);
  const composer = page.getByLabel("向 OphAgent 提问");
  await composer.fill("请详细比较开角型与闭角型青光眼，检索证据并生成结构化报告。");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止当前任务" })).toBeVisible();

  await page.getByRole("button", { name: /立即打断：/ }).click();
  await composer.fill("改为只回答闭角型青光眼的急性发作识别与就医优先级，不再做两类比较。");
  const interruptedResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/interventions")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "立即打断并发送新要求" }).click();
  expect((await interruptedResponse).status()).toBe(202);
  await expect(page.locator(".intervention-message").getByText(/改为只回答闭角型青光眼/)).toBeVisible();
  await expect(page.getByRole("button", { name: "重新生成回答" }).first()).toBeVisible({
    timeout: 240_000,
  });

  const conversation = await currentConversation(page);
  expect(conversation.runs).toHaveLength(1);
  const run = conversation.runs[0];
  expect(run.status).toMatch(/^completed/);
  expect(run.attempt).toBe(2);
  expect(run.interventions[0].status).toBe("applied");
  expect(run.interventions[0].content).toContain("不再做两类比较");
  expect(run.input.query).not.toContain("【用户在执行期间追加的要求");
  const events = await page.evaluate(
    (runId) => fetch(`/api/v1/runs/${runId}/events`).then((response) => response.json()),
    run.id,
  );
  const eventTypes = events.map((event: { type: string }) => event.type);
  expect(eventTypes).toContain("run.interrupted");
  expect(eventTypes).toContain("run.resumed");
  expect(eventTypes).not.toContain("run.cancelled");
  expect(failedResponses).toEqual([]);
  expect(pageErrors).toEqual([]);
});
