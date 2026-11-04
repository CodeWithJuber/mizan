import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// The live connection is mocked in the page: one greeting, then quiet.
async function mockSocket(page: Page) {
  await page.routeWebSocket(/\/ws\//, (ws) => {
    ws.send(JSON.stringify({ type: "connected", message: "MIZAN", agents: 2 }));
  });
}

async function signIn(page: Page) {
  await mockSocket(page);
  await page.goto("/chat");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Username").fill("tester");
  await page.getByLabel("Password", { exact: true }).fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();
  // Signed in once the page leaves /login: reloading earlier races the stored token.
  await expect(page).not.toHaveURL(/\/login/);
  // First visit: the setup page; skip it for these tests.
  await page.evaluate(() => localStorage.setItem("mizan_setup_complete", "1"));
  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "Assalamu alaikum" })).toBeVisible();
}

async function send(page: Page, text: string) {
  const box = page.getByLabel("Message MIZAN");
  await box.fill(text);
  await box.press("Enter");
}

test("a signed-out visit goes to sign in, and a wrong password says so", async ({ page }) => {
  await mockSocket(page);
  await page.goto("/settings/account");
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings%2Faccount/);
  await page.getByLabel("Username").fill("tester");
  await page.getByLabel("Password", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Wrong username or password.");
});

test("setup's provider link opens the providers page instead of looping back to setup", async ({ page }) => {
  await mockSocket(page);
  await page.goto("/chat");
  await page.getByLabel("Username").fill("tester");
  await page.getByLabel("Password", { exact: true }).fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/welcome/);
  await page.getByRole("button", { name: "Get Started" }).click();
  await page.getByRole("button", { name: "Open Models & providers" }).click();
  await expect(page).toHaveURL(/\/settings\/developer\/providers/);
  await page.reload();
  await expect(page).not.toHaveURL(/\/welcome/);
});

test("a web page in an answer opens in a sandboxed preview and saves to the chat", async ({ page }) => {
  await signIn(page);
  await send(page, "Make me a web page");
  await page.getByRole("button", { name: "Preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Hello page" });
  await expect(dialog).toBeVisible();
  const frame = dialog.locator("iframe");
  // Opaque origin: the page can never reach the MIZAN session.
  await expect(frame).not.toHaveAttribute("sandbox", /allow-same-origin/);
  await expect(dialog.frameLocator("iframe").getByRole("heading", { name: "Hello from the sandbox" })).toBeVisible();
  await dialog.getByRole("button", { name: "Save to chat" }).click();
  await expect(page.getByText("Saved to this chat")).toBeVisible();
});

test("a message streams into a formatted answer with its sources", async ({ page }) => {
  await signIn(page);
  await send(page, "Compare sabr and shukr");
  await expect(page.getByLabel("MIZAN is working")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop generating" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible({ timeout: 20_000 });
  // The chat now has its own URL and appears in the sidebar.
  await expect(page).toHaveURL(/\/chat\/session_/);
  if (page.viewportSize()!.width >= 768) {
    await expect(page.getByRole("link", { name: "Compare sabr and shukr" })).toBeVisible();
  }
  const answer = page.locator(".prose").last();
  await expect(answer.getByRole("table")).toBeVisible();
  await expect(answer.getByText("Patience in hardship")).toBeVisible();
  await expect(answer.locator("pre").getByText("console.log(i)")).toBeVisible();
  // The run folded into one line, and the sources row is there.
  await expect(page.getByText(/Worked · 2 steps/)).toBeVisible();
  await page.getByText("2 sahih · 1 hasan · 1 da'if").click();
  await expect(page.getByText("Isnad — what supports each claim")).toBeVisible();
});

test("Stop keeps what arrived and says it stopped", async ({ page }) => {
  await signIn(page);
  await send(page, "slow answer please");
  await expect(page.locator(".prose").last()).toContainText("Sabr and shukr", { timeout: 15_000 });
  await page.getByRole("button", { name: "Stop generating" }).click();
  await expect(page.getByText(/Stopped · received text kept/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
});

test("an approval prompt waits for Allow, then the run goes on", async ({ page }) => {
  await signIn(page);
  await send(page, "approve a file write");
  await expect(page.getByText("Allow workspace_write?")).toBeVisible();
  await page.getByRole("button", { name: "Allow", exact: true }).click();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".prose").last().getByRole("table")).toBeVisible();
});

test("a chat link opens that chat after a reload, and Back works", async ({ page }) => {
  await signIn(page);
  await send(page, "First chat");
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible({ timeout: 20_000 });
  const first = page.url();
  await page.reload();
  await expect(page.getByText("First chat", { exact: true }).last()).toBeVisible();
  await page.goto("/settings/appearance");
  await expect(page.getByRole("heading", { name: "Appearance" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(first);
});

test("every main page opens without an error", async ({ page }) => {
  await signIn(page);
  const pages: [string, RegExp][] = [
    ["/code", /Code/],
    ["/agents", /Agents/],
    ["/agents/majlis", /Majlis/],
    ["/library/memory", /Library/],
    ["/library/knowledge", /Library/],
    ["/automations/watchers", /Automations/],
    ["/automations/tasks", /Automations/],
    ["/automations/queue", /Automations/],
    ["/settings/account", /Settings/],
    ["/settings/appearance", /Appearance/],
    ["/settings/developer/system", /Settings/],
  ];
  for (const [path, heading] of pages) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
    // Lazy pages render after the heading: give them a moment to fail.
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("Something went wrong"), path).toHaveCount(0);
  }
});

test("the chat page has no serious accessibility problems", async ({ page }) => {
  await signIn(page);
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
  expect(serious.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
});

test("on a phone the sidebar opens as a drawer", async ({ page }) => {
  test.skip(page.viewportSize()!.width >= 768, "phone layout only");
  await signIn(page);
  await page.getByRole("button", { name: "Toggle Sidebar" }).first().click();
  await expect(page.getByRole("link", { name: "Library" })).toBeVisible();
});
