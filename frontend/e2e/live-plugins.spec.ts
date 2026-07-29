import path from "node:path";
import { expect, test } from "@playwright/test";

test("真实影像可串联病灶定位、辅助评估和报告生成", async ({ page }, testInfo) => {
  test.skip(!process.env.RUN_LIVE_AGENT_E2E, "仅在显式启用真实模型验收时运行");
  test.skip(testInfo.project.name === "mobile", "真实多模态工作流只运行一次桌面端");
  test.setTimeout(300_000);

  const failedResponses: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) failedResponses.push(`${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  await page.goto("/");
  await page.getByRole("button", { name: "还没有账号？创建一个" }).click();
  await page.getByLabel("用户名").fill(`live_plugins_${suffix}`);
  await page.getByLabel("密码").fill("Visual-test-2026");
  await page.getByRole("button", { name: "创建账号" }).click();

  await page.getByRole("button", { name: "添加附件" }).click();
  await page.locator(".add-menu input[accept='image/*']").setInputFiles(
    path.resolve("../ophthalmic_plugin_test_cases/images/glaucoma_postoperative_followup.jpg"),
  );
  await expect(page.locator(".attachment-chip")).toHaveCount(1);
  await expect(page.locator(".attachment-chip img")).toBeVisible();

  await page.getByRole("main").getByRole("button", { name: "插件" }).click();
  for (const label of ["病灶定位", "辅助评估", "报告生成"]) {
    await page.locator(".plugin-menu").getByRole("button", { name: new RegExp(`^${label}`) }).click();
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("main").getByRole("button", { name: /病灶定位、辅助评估、报告生成/ })).toBeVisible();

  await page.getByLabel("向 OphAgent 提问").fill(
    "请读取这张眼科影像，定位可疑区域，形成定性辅助评估，并生成可编辑的结构化报告。",
  );
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止当前任务" })).toBeVisible();
  await expect(page.locator(".artifact-card").first()).toBeVisible({ timeout: 240_000 });
  await expect(page.getByLabel("本次提问的附件").locator("img")).toBeVisible();
  await expect(page.getByLabel("专业插件结果")).toBeVisible();
  await expect(page.getByText(/支持程度不是患病概率/)).toBeVisible();

  await page.locator(".artifact-card").first().click();
  const drawer = page.getByRole("dialog", { name: "文档工作区" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("编辑文档内容")).not.toHaveValue("");
  await drawer.getByLabel("导出文档").click();
  await expect(drawer.getByRole("link", { name: "DOCX" })).toBeVisible();

  await page.screenshot({ path: testInfo.outputPath("live-three-plugins.png"), fullPage: true });
  expect(failedResponses).toEqual([]);
  expect(pageErrors).toEqual([]);
});
