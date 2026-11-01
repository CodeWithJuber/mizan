import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Coding with MIZAN against the mock API: a project beside its chat, the changes a
// reply made (undo a file, reject a hunk), Rewind with Undo, "Always" taken back,
// and a plan run by its button.

async function signIn(page: Page) {
  await page.routeWebSocket(/\/ws\//, (ws) => ws.send(JSON.stringify({ type: "connected", message: "MIZAN", agents: 2 })));
  await page.goto("/login");
  await page.getByLabel("Username").fill("tester");
  await page.getByLabel("Password", { exact: true }).fill("secret");
  await page.getByRole("button", { name: "Sign in" }).click();
  // Signed in once the page leaves /login: reloading earlier races the stored token.
  await expect(page).not.toHaveURL(/\/login/);
  await page.evaluate(() => localStorage.setItem("mizan_setup_complete", "1"));
}

const phone = (page: Page) => page.viewportSize()!.width < 768;

async function send(page: Page, text: string) {
  const box = page.getByLabel("Message MIZAN");
  await box.fill(text);
  await box.press("Enter");
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible({ timeout: 20_000 });
}

async function chooseMode(page: Page, title: RegExp) {
  await page.getByRole("button", { name: "Attach and options" }).click();
  await page.getByRole("radio", { name: title }).click();
  await page.keyboard.press("Escape");
}

/** On a phone the split view shows one side at a time. */
async function show(page: Page, side: "Chat" | "Project") {
  if (phone(page)) await page.getByRole("button", { name: side, exact: true }).click();
}

test("a project opens beside its chat, and a reply's changes can be undone or rejected", async ({ page }) => {
  await signIn(page);
  await page.goto("/code");
  await page.getByLabel("New project name").fill("shop");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/code\/ws-/);
  await expect(page.getByRole("heading", { name: "shop" })).toBeVisible();

  await show(page, "Chat");
  await send(page, "Build a todo app in React");
  await expect(page.getByText("Built the todo app")).toBeVisible();

  await show(page, "Project");
  await page.getByRole("tab", { name: "Changes" }).click();
  const changed = page.getByRole("list", { name: "Changed files" });
  await expect(changed.getByText("src/Todo.jsx")).toBeVisible();
  await expect(changed.getByText("src/App.jsx")).toBeVisible();

  // Undo one file: the file did not exist before the message, so it goes.
  await changed.getByRole("listitem").filter({ hasText: "src/Todo.jsx" }).getByRole("button", { name: "Undo" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Undo" }).click();
  await expect(changed.getByText("src/Todo.jsx")).toHaveCount(0);

  // Review App.jsx hunk by hunk: keep the new imports, reject the new body, save.
  await changed.getByRole("button", { name: /src\/App\.jsx/ }).click();
  const editor = page.getByRole("textbox", { name: "Changes in src/App.jsx" });
  await expect(editor.getByRole("insertion").filter({ hasText: "import Todo" })).toBeVisible();
  await editor.getByRole("button", { name: "Accept" }).first().click();
  await editor.getByRole("button", { name: "Reject" }).first().click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("src/App.jsx saved")).toBeVisible();
  // Compared with before the message, only the imports are new now.
  await expect(editor.getByRole("insertion").filter({ hasText: "import Todo" })).toBeVisible();
  await expect(editor.getByRole("deletion")).toHaveCount(0);
  await expect(editor).toContainText("return <h1>Hello</h1>;");

  // Reject all, save: nothing is left changed.
  await page.getByRole("button", { name: "Reject all" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("No changes since this checkpoint.")).toBeVisible();
});

test("an edit asks with its diff, Always is listed, and can be taken back", async ({ page }) => {
  await signIn(page);
  await page.goto("/chat");
  await chooseMode(page, /^Ask first/);
  await page.getByLabel("Message MIZAN").fill("Build a todo app in React");
  await page.getByLabel("Message MIZAN").press("Enter");

  const prompt = page.getByRole("alert").filter({ hasText: "Allow workspace_write?" });
  await expect(prompt.getByText("New file")).toBeVisible();
  await expect(prompt.getByText("export default function Todo")).toBeVisible();
  await prompt.getByRole("button", { name: "Always in this chat" }).click();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible({ timeout: 20_000 });

  const chip = page.getByText("Always: Write files");
  await expect(chip).toBeVisible();
  await page.getByRole("button", { name: "Remove Always: Write files" }).click();
  await expect(chip).toHaveCount(0);

  // The chat made a project: the header opens it beside this chat.
  await page.getByRole("link", { name: /Open project/ }).click();
  await expect(page).toHaveURL(/\/code\/ws-[^?]+\?chat=session_/);
  await expect(page.getByRole("heading", { name: "todo-app" })).toBeVisible();
});

test("Rewind puts the code back to before a message, and Undo restores it", async ({ page }) => {
  await signIn(page);
  await page.goto("/chat");
  await send(page, "Build a todo app in React");

  await page.getByRole("button", { name: "Rewind code to before this message" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("src/Todo.jsx (added)");
  await dialog.getByRole("button", { name: "Rewind" }).click();
  await expect(page.getByText("Code rewound")).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();

  // After the undo the reply's files are back: the rewind finds them to put back again.
  await page.getByRole("button", { name: "Rewind code to before this message" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("src/Todo.jsx (added)");
});

test("a plan for the project runs only from its button", async ({ page }) => {
  await signIn(page);
  await page.goto("/chat");
  await send(page, "Build a todo app in React");
  await chooseMode(page, /^Plan/);
  await send(page, "Add a dark mode");
  await expect(page.getByText("Nothing has changed yet.")).toBeVisible();

  await page.getByRole("button", { name: "Approve plan and run" }).click();
  await expect(page.getByText("Carried out the approved plan")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Approve plan and run" })).toHaveCount(0);
  // The run left plan mode: no mode chip under the composer.
  await expect(page.getByRole("button", { name: "Remove Plan" })).toHaveCount(0);
});

test("the project view has no serious accessibility problems", async ({ page }) => {
  await signIn(page);
  await page.goto("/code");
  await page.getByLabel("New project name").fill("a11y");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "a11y" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});
