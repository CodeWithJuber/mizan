import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// The agent builder against the mock API: build an agent with starter prompts,
// see them in a new chat, export one, make one the default (then put it back).

async function signIn(page: Page) {
  await page.routeWebSocket(/\/ws\//, (ws) => ws.send(JSON.stringify({ type: "connected", message: "MIZAN", agents: 2 })));
  await page.goto("/login");
  await page.getByLabel("Username").fill("tester");
  await page.getByLabel("Password", { exact: true }).fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await page.evaluate(() => localStorage.setItem("mizan_setup_complete", "1"));
}

const card = (page: Page, name: string) => page.locator(".group").filter({ has: page.getByRole("button", { name: new RegExp(`^Agent ${name},`) }) });

test("an agent built with starter prompts offers them in a new chat", async ({ page }, info) => {
  const name = `Planner ${info.project.name}`;
  await signIn(page);
  await page.goto("/agents");
  await page.getByRole("button", { name: "New agent" }).first().click();
  const dialog = page.getByRole("dialog", { name: /Create an agent/ });
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByLabel("Avatar").fill("🗓️");
  await dialog.getByLabel("Provider").selectOption("anthropic");
  await dialog.getByLabel("Model").selectOption(JSON.stringify(["anthropic", "claude-haiku-5-5"]));

  await dialog.getByRole("tab", { name: "Behaviour" }).click();
  await dialog.getByLabel("Who directs the work").selectOption("hybrid");
  await expect(dialog.getByLabel("Temperature")).toBeDisabled();

  await dialog.getByRole("tab", { name: "Starter prompts" }).click();
  await dialog.getByRole("button", { name: "Add starter prompt" }).click();
  await dialog.getByRole("textbox", { name: "Starter prompt 1", exact: true }).fill("Plan my week around the prayers");
  await dialog.getByRole("button", { name: "Create agent" }).click();
  await expect(page.getByText("Agent created")).toBeVisible();
  await expect(dialog).toHaveCount(0);

  // Pick it, open a new chat: its starter prompt is one tap away.
  await card(page, name).getByRole("button", { name: new RegExp(`^Agent ${name},`) }).click();
  await page.goto("/chat");
  await page.getByRole("button", { name: "Plan my week around the prayers" }).click();
  await expect(page.getByLabel("Message MIZAN")).toHaveValue("Plan my week around the prayers");

  // Clean up so the other tests see the usual team.
  await page.goto("/agents");
  await card(page, name).getByRole("button", { name: `More for ${name}` }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Agent deleted")).toBeVisible();
});

test("an agent exports as a file, and the default can be changed and put back", async ({ page }) => {
  await signIn(page);
  await page.goto("/agents");
  const katib = card(page, "Katib");
  await expect(katib.getByText("Private")).toBeVisible();
  await expect(card(page, "Khalifah").getByText("Default")).toBeVisible();

  await katib.getByRole("button", { name: "More for Katib" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Export" }).click();
  expect((await download).suggestedFilename()).toBe("Katib.mizan-agent.json");

  await katib.getByRole("button", { name: "More for Katib" }).click();
  await page.getByRole("menuitem", { name: "Make default" }).click();
  await expect(page.getByText("Katib is your default agent")).toBeVisible();
  await expect(katib.getByText("Default", { exact: true })).toBeVisible();

  await card(page, "Khalifah").getByRole("button", { name: "More for Khalifah" }).click();
  await page.getByRole("menuitem", { name: "Make default" }).click();
  await expect(card(page, "Khalifah").getByText("Default", { exact: true })).toBeVisible();
});

test("the agent builder has no serious accessibility problems", async ({ page }) => {
  await signIn(page);
  await page.goto("/agents");
  await page.getByRole("button", { name: "New agent" }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});
