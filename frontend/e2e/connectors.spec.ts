import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function signIn(page: Page) {
  await page.routeWebSocket(/\/ws\//, (ws) => ws.send(JSON.stringify({ type: "connected", message: "MIZAN", agents: 2 })));
  await page.goto("/login");
  await page.getByLabel("Username").fill("tester");
  await page.getByLabel("Password", { exact: true }).fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await page.evaluate(() => localStorage.setItem("mizan_setup_complete", "1"));
  // Each test starts from the mock's own connectors (desktop and phone share one mock server).
  await page.request.post("/api/e2e/connectors/reset", { headers: { Authorization: "Bearer e2e-token" } });
}

test("Add connector opens on presets, and a preset fills the form", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/connectors");
  await expect(page.getByRole("heading", { name: "GitHub" })).toBeVisible();
  await page.getByRole("button", { name: "Add connector", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Add a connector" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Presets" })).toHaveAttribute("aria-selected", "true");
  const presets = page.getByRole("list", { name: "Presets" });
  await expect(presets.getByRole("heading", { name: "Notion" })).toBeVisible();
  await expect(presets.getByText("Official").first()).toBeVisible();
  await page.getByRole("button", { name: "Set up Notion" }).click();
  await expect(page.getByRole("tab", { name: "Custom" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Notion");
  await expect(page.getByLabel("Server URL", { exact: true })).toHaveValue("https://mcp.notion.com/mcp");
  await page.getByRole("button", { name: "Add connector", exact: true }).click();
  await expect(page.getByRole("article", { name: "Notion" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add a connector" })).toHaveCount(0);
});

test("a held tool shows what changed and can be trusted", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/connectors");
  const github = page.getByRole("article", { name: "GitHub" });
  await expect(github.getByText("What changed", { exact: true })).toBeVisible();
  await github.getByRole("button", { name: "Trust it as it is now" }).click();
  await expect(github.getByText("What changed", { exact: true })).toHaveCount(0);
  await expect(github.getByText("3 of 3 tools usable")).toBeVisible();
});

test("registry entries that can't run here say why", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/connectors");
  await page.getByRole("button", { name: "Add connector", exact: true }).click();
  await page.getByRole("tab", { name: "Registry" }).click();
  const results = page.getByRole("list", { name: "Registry results" });
  await expect(results.getByRole("heading", { name: "Weather" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add Containers as a local server (oci)" })).toBeDisabled();
  await expect(results.getByText("Container images can't run in the sandbox runner.")).toBeVisible();
  await page.getByRole("button", { name: "Add Weather as a local server (npm)" }).click();
  await expect(page.getByLabel("Command", { exact: true })).toHaveValue("npx");
  await expect(page.getByLabel("Arguments", { exact: true })).toHaveValue("-y @acme/weather-mcp@1.2.0");
});

test("the connectors page has no serious accessibility problems and fits a phone", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/connectors");
  await expect(page.getByRole("heading", { name: "GitHub" })).toBeVisible();
  await page.getByRole("button", { name: "Add connector", exact: true }).click();
  await expect(page.getByRole("list", { name: "Presets" }).getByRole("heading", { name: "Notion" })).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  const overflow = await page.evaluate(() => {
    const body = document.querySelector(".page-body");
    return body ? body.scrollWidth - body.clientWidth : 0;
  });
  expect(overflow).toBeLessThanOrEqual(0);
});
