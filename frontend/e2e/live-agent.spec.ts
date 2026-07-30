import path from "node:path";
import { expect, test } from "@playwright/test";

test("真实模型完成多轮追问、上下文压缩、反馈、重生成和文档编辑", { tag: "@desktop" }, async ({ page }, testInfo) => {
  test.skip(!process.env.RUN_LIVE_AGENT_E2E, "仅在显式启用真实模型验收时运行");
  test.setTimeout(360_000);

  const failedResponses: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) {
      failedResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  await page.goto("/");
  await page.getByRole("button", { name: "还没有账号？创建一个" }).click();
  await page.getByLabel("用户名").fill(`live_agent_${suffix}`);
  await page.getByLabel("密码").fill("Visual-test-2026");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("heading", { name: "今天想先处理什么？" })).toBeVisible();

  const composer = page.getByLabel("向 OphAgent 提问");
  await composer.fill("什么是青光眼？请结合知识库和可追踪来源回答。");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止当前任务" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新生成回答" }).first()).toBeVisible({
    timeout: 120_000,
  });
  await expect(page.locator(".citation-group").first()).toBeVisible();

  await composer.fill("那通常需要做哪些检查？");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.locator(".turn")).toHaveCount(2);
  const secondTurn = page.locator(".turn").last();
  await expect(secondTurn.getByRole("button", { name: "重新生成回答" })).toBeVisible({
    timeout: 120_000,
  });
  await secondTurn.locator(".activity-summary").click();
  await expect(secondTurn.getByText(/已衔接 1 轮历史对话/)).toBeVisible();

  const latestActions = secondTurn.locator(".message-actions");
  await latestActions.getByRole("button", { name: "有帮助", exact: true }).click();
  await expect(latestActions.getByRole("button", { name: "有帮助", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await latestActions.locator("summary[aria-label='更多操作']").click();
  await expect(page.locator(".answer-menu").last()).toBeVisible();
  await page.locator(".answer-menu").last().getByRole("button", { name: "转为文档编辑" }).click();
  const drawer = page.getByRole("dialog", { name: "文档工作区" });
  await expect(drawer).toBeVisible();
  await drawer.getByLabel("编辑文档内容").fill("# 青光眼检查清单\n\n已通过真实 GUI 编辑。");
  await expect(drawer.getByRole("heading", { name: "青光眼检查清单" })).toBeVisible();
  await drawer.getByLabel("导出文档").click();
  await expect(drawer.getByRole("link", { name: "PDF" })).toBeVisible();
  await page.keyboard.press("Escape");

  await secondTurn.getByRole("button", { name: "重新生成回答" }).click();
  await expect(page.getByText("回答 2 / 2")).toBeVisible();
  await expect(secondTurn.getByRole("button", { name: "重新生成回答" })).toBeVisible({
    timeout: 120_000,
  });

  const speech = secondTurn.getByRole("button", { name: "朗读回答" });
  await speech.click();
  await expect(secondTurn.getByRole("button", { name: /取消准备朗读|停止朗读/ })).toBeVisible();
  await secondTurn.getByRole("button", { name: /取消准备朗读|停止朗读/ }).click();
  await expect(secondTurn.getByRole("button", { name: "朗读回答" })).toBeVisible();

  await page.getByRole("button", { name: "添加附件" }).click();
  const imageInput = page.locator(".add-menu input[accept='image/*']");
  await imageInput.setInputFiles([
    path.resolve("../ophthalmic_plugin_test_cases/images/glaucoma_postoperative_followup.jpg"),
    path.resolve("../ophthalmic_plugin_test_cases/images/glaucoma_preoperative_fundus_oct_visual_field.jpg"),
  ]);
  await expect(page.locator(".attachment-chip")).toHaveCount(2);
  await expect(page.locator(".add-menu")).toHaveCount(0);
  while (await page.locator(".attachment-chip button").count()) {
    await page.locator(".attachment-chip button").first().click();
  }

  await page.getByRole("main").getByRole("button", { name: "插件" }).click();
  await expect(page.locator(".plugin-menu").getByText("病灶定位", { exact: true })).toBeVisible();
  await expect(page.locator(".plugin-menu").getByText("辅助评估", { exact: true })).toBeVisible();
  await expect(page.locator(".plugin-menu").getByText("报告生成", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("main").getByRole("button", { name: "技能" }).click();
  await expect(page.getByText("只列出已验证并启用的技能")).toBeVisible();
  await expect(page.locator(".skill-menu input[type=file]")).toHaveCount(0);
  await page.keyboard.press("Escape");

  const conversation = await page.evaluate(async () => {
    const pageResult = await fetch("/api/v1/conversations?limit=100").then((response) => response.json());
    return fetch(`/api/v1/conversations/${pageResult.items[0].id}`).then((response) => response.json());
  });
  expect(conversation.runs).toHaveLength(3);
  const regenerated = conversation.runs.find(
    (run: { input: { regenerated_from?: string | null } }) => run.input.regenerated_from,
  );
  const followUp = conversation.runs.find(
    (run: { id: string }) => run.id === regenerated?.input.regenerated_from,
  );
  expect(followUp.route.reason_code).toBe("contextual_follow_up");
  expect(followUp.context_stats.source_turns).toBe(1);
  expect(regenerated.context_stats.source_turns).toBe(1);
  if (Number(process.env.CONVERSATION_CONTEXT_MAX_INPUT_TOKENS || 0) <= 350) {
    expect(followUp.context_stats.compaction_status).toBe("completed");
    expect(followUp.context_stats.compaction_method).toBe("model_structured_summary");
    expect(followUp.context_stats.summarized_turns).toBe(1);
    expect(followUp.context_stats.tokens_after).toBeLessThan(
      followUp.context_stats.tokens_before,
    );
  }

  await page.screenshot({ path: testInfo.outputPath("live-multiturn.png"), fullPage: true });
  expect(failedResponses).toEqual([]);
  expect(pageErrors).toEqual([]);
});
