import { expect, test, type Page } from "@playwright/test";

// Screenshots for a person to look at (SCREENSHOTS=1 npx playwright test screens).
test.skip(!process.env.SCREENSHOTS, "screenshots only when asked");

const OUT = process.env.SCREENSHOTS_DIR || "test-results/screens";

async function open(page: Page, scheme: "light" | "dark") {
  await page.emulateMedia({ colorScheme: scheme });
  await page.routeWebSocket(/\/ws\//, (ws) => ws.send(JSON.stringify({ type: "connected", message: "MIZAN", agents: 2 })));
  await page.goto("/login");
  await page.getByLabel("Username").fill("tester");
  await page.getByLabel("Password", { exact: true }).fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();
  // Signed in once the page leaves /login: reloading earlier races the stored token.
  await expect(page).not.toHaveURL(/\/login/);
  await page.evaluate(() => localStorage.setItem("mizan_setup_complete", "1"));
  await page.goto("/chat");
}

for (const scheme of ["light", "dark"] as const) {
  test(`chat ${scheme}`, async ({ page }, info) => {
    const tag = `${info.project.name}-${scheme}`;
    await open(page, scheme);
    await page.screenshot({ path: `${OUT}/${tag}-empty.png` });
    const box = page.getByLabel("Message MIZAN");
    await box.fill("Compare sabr and shukr");
    await box.press("Enter");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/${tag}-running.png` });
    await page.getByRole("button", { name: "Send message" }).waitFor({ timeout: 20_000 });
    await page.getByText(/Worked/).first().click();
    await page.getByText("2 verified · 1 supported · 1 model's words only").click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/${tag}-answer.png`, fullPage: true });
    await box.fill("/");
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/${tag}-slash.png` });
    await box.fill("");
    await page.getByRole("button", { name: "Attach and options" }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/${tag}-plus.png` });
    await page.keyboard.press("Escape");
    await page.goto("/settings/account");
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/${tag}-settings.png` });
  });
}

const PAGES = ["/agents", "/library/memory", "/automations/watchers", "/settings/developer/system", "/settings/connectors", "/code"];

for (const scheme of ["light", "dark"] as const) {
  test(`pages ${scheme}`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "desktop only");
    await open(page, scheme);
    for (const path of PAGES) {
      await page.goto(path);
      await page.waitForTimeout(700);
      await page.screenshot({ path: `${OUT}/${info.project.name}-${scheme}${path.replaceAll("/", "-")}.png` });
    }
  });
}

for (const scheme of ["light", "dark"] as const) {
  test(`code ${scheme}`, async ({ page }, info) => {
    const tag = `${info.project.name}-${scheme}`;
    const phone = page.viewportSize()!.width < 768;
    await open(page, scheme);
    await page.goto("/code");
    await page.getByLabel("New project name").fill(`todo-${scheme}`);
    await page.getByRole("button", { name: "Create" }).click();
    await page.getByRole("heading", { name: `todo-${scheme}` }).waitFor();
    if (phone) await page.getByRole("button", { name: "Chat", exact: true }).click();
    const box = page.getByLabel("Message MIZAN");
    await box.fill("Build a todo app in React");
    await box.press("Enter");
    await page.getByRole("button", { name: "Send message" }).waitFor({ timeout: 20_000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/${tag}-code-chat.png` });
    if (phone) await page.getByRole("button", { name: "Project", exact: true }).click();
    await page.getByRole("tab", { name: "Changes" }).click();
    await page.getByRole("button", { name: /src\/App\.jsx/ }).click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/${tag}-code-changes.png` });
    await page.goto("/code");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/${tag}-code-list.png` });
  });
}
