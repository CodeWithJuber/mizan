import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { Agent, ApiClient } from "../types";
import { agentFormData, type AgentFormData } from "../utils/agentSettings.ts";
import { AgentModal } from "./AgentModal";

vi.mock("./Toast", () => ({ addToast: vi.fn() }));

const responses: Record<string, Record<string, unknown>> = {
  "/providers": { active: "anthropic", default_model: "claude-haiku-5-5", providers: [{ name: "anthropic", display: "Anthropic", configured: true }] },
  "/connectors": { connectors: [{ id: "c1", name: "GitHub", slug: "github", enabled: true }] },
  "/agent-skills": { skills: [{ name: "tafsir-notes", description: "Notes", enabled: true }] },
};

function api(): ApiClient {
  const get = vi.fn(async (path: string) => {
    if (path.startsWith("/providers/anthropic/models")) return { models: [{ id: "claude-haiku-5-5", name: "Haiku" }], total: 1 };
    return responses[path] ?? {};
  });
  const write = vi.fn(async () => ({}));
  return { get, post: write, put: write, patch: write, del: write, API_URL: "/api" };
}

function open(props: { editingAgent?: Agent | null; onSave: (data: AgentFormData) => Promise<void>; canShare?: boolean }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AgentModal
          editingAgent={props.editingAgent ?? null}
          initialData={agentFormData()}
          api={api()}
          onSave={props.onSave}
          onClose={() => undefined}
          canShare={props.canShare}
          toolCatalog={["bash", "web_search"]}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const katib: Agent = {
  id: "agent-2", name: "Katib", role: "katib", state: "resting", nafs_level: 1, total_tasks: 0, success_rate: 0, hikmah_count: 0,
  tools: ["bash"], model: "claude-haiku-5-5", provider: "anthropic", editable: true, shared: false,
  settings: { orchestration: "mizan", starter_prompts: ["Hello"], avatar: "✍️" },
};

describe("AgentModal (the agent builder)", () => {
  afterEach(() => cleanup());

  it("creates an agent with its behaviour, tools and starter prompts", async () => {
    const onSave = vi.fn(async (_data: AgentFormData) => undefined);
    open({ onSave, canShare: true });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "  Planner  " } });
    fireEvent.change(screen.getByLabelText("Avatar"), { target: { value: "🗓️" } });
    await waitFor(() => expect(screen.getByRole("option", { name: /^claude-haiku-5-5/ })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: JSON.stringify(["anthropic", "claude-haiku-5-5"]) } });
    fireEvent.click(screen.getByRole("switch", { name: "Share with everyone on this server" }));

    fireEvent.click(screen.getByRole("tab", { name: "Behaviour" }));
    fireEvent.change(screen.getByLabelText("Who directs the work"), { target: { value: "hybrid" } });
    fireEvent.change(screen.getByLabelText("What it may do without asking"), { target: { value: "ask" } });
    fireEvent.change(screen.getByLabelText("Max steps"), { target: { value: "12" } });
    // A Claude model takes no temperature.
    expect((screen.getByLabelText("Temperature") as HTMLInputElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("tab", { name: "Tools & knowledge" }));
    fireEvent.click(screen.getByRole("button", { name: "web_search: available" }));
    fireEvent.click(screen.getByRole("button", { name: "bash: available" }));
    fireEvent.click(screen.getByRole("button", { name: "bash: only these" }));
    fireEvent.click(await screen.findByRole("button", { name: "GitHub" }));
    fireEvent.click(await screen.findByRole("button", { name: "tafsir-notes" }));
    fireEvent.click(screen.getByRole("switch", { name: "Let this agent save what it learns as skills" }));

    fireEvent.click(screen.getByRole("tab", { name: "Starter prompts" }));
    fireEvent.click(screen.getByRole("button", { name: "Add starter prompt" }));
    fireEvent.change(screen.getByLabelText("Starter prompt 1"), { target: { value: "Plan my week" } });
    fireEvent.click(screen.getByRole("button", { name: "Add starter prompt" }));

    fireEvent.click(screen.getByRole("button", { name: "Create agent" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    expect(saved.name).toBe("Planner");
    expect(saved.shared).toBe(true);
    expect(saved.model).toBe("claude-haiku-5-5");
    expect(saved.settings).toMatchObject({
      avatar: "🗓️", orchestration: "hybrid", permission_mode: "ask", max_steps: 12, temperature: null,
      tools_allow: ["web_search"], tools_deny: ["bash"], connectors: ["github"], skills: ["tafsir-notes"],
      learn_skills: false, starter_prompts: ["Plan my week"],
    });
  });

  it("names what is missing instead of saving", async () => {
    const onSave = vi.fn(async () => undefined);
    open({ onSave });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "No model yet" } });
    fireEvent.click(screen.getByRole("button", { name: "Create agent" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Choose a model/);
    expect(onSave).not.toHaveBeenCalled();
    // Only admins may share an agent.
    expect(screen.queryByRole("switch", { name: "Share with everyone on this server" })).toBeNull();
  });

  it("opens an agent with its saved settings and returns to the tab with the problem", async () => {
    const onSave = vi.fn(async () => undefined);
    open({ editingAgent: katib, onSave });
    expect((screen.getByLabelText("Avatar") as HTMLInputElement).value).toBe("✍️");
    fireEvent.click(screen.getByRole("tab", { name: "Behaviour" }));
    expect((screen.getByLabelText("Who directs the work") as HTMLSelectElement).value).toBe("mizan");
    fireEvent.change(screen.getByLabelText("Max steps"), { target: { value: "2.5" } });
    fireEvent.click(screen.getByRole("tab", { name: "Starter prompts" }));
    expect((screen.getByLabelText("Starter prompt 1") as HTMLInputElement).value).toBe("Hello");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/whole number/);
    expect(screen.getByRole("tab", { name: "Behaviour" }).getAttribute("aria-selected")).toBe("true");
    expect(onSave).not.toHaveBeenCalled();
  });
});
