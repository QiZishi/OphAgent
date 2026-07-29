import { expect, test } from "@playwright/test";

test("真实后端注册、项目创建、资源导航和语音入口可用", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "桌面端真实工作流验收");
  const suffix = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  const username = `gui_${suffix}`;
  const projectName = `GUI 随访项目 ${suffix.slice(-6)}`;

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "欢迎使用 OphAgent" })).toBeVisible();
  await page.getByRole("button", { name: "还没有账号？创建一个" }).click();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill("Visual-test-2026");
  await page.getByRole("button", { name: "创建账号" }).click();

  await expect(page.getByRole("heading", { name: "今天想先处理什么？" })).toBeVisible();
  await expect(page.getByRole("button", { name: "语音输入" })).toBeVisible();
  await expect(page.getByRole("button", { name: "实时语音模式" })).toBeVisible();

  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "项目" }).click();
  await page.getByLabel("项目名称").fill(projectName);
  await page.getByLabel("说明").fill("用于验证真实浏览器、真实 API 与项目持久化。");
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();

  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "记忆" }).click();
  await expect(page.getByRole("heading", { name: "长期记忆" })).toBeVisible();
  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "知识库" }).click();
  await expect(page.getByRole("heading", { name: "知识库与来源" })).toBeVisible();
  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "技能" }).click();
  await expect(page.getByRole("heading", { name: "Skill 注册表" })).toBeVisible();
  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "设置" }).click();
  const evolution = page.getByRole("region", { name: "持续改进状态" });
  await expect(evolution).toBeVisible();
  await expect(evolution).toContainText("生产自动变更：关闭");
  await expect(evolution).toContainText("临床记忆不按粗粒度反馈重排");
  await page.screenshot({ path: testInfo.outputPath("live-evolution-settings.png"), fullPage: true });
  await page.getByRole("navigation", { name: "工作区" }).getByRole("button", { name: "项目" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();

  await page.screenshot({ path: testInfo.outputPath("live-projects.png"), fullPage: true });

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: `删除项目 ${projectName}` }).click();
  await expect(page.getByRole("heading", { name: projectName })).toHaveCount(0);
});
