import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ApiClient } from "../types";

vi.mock("./ui/confirm", () => ({ confirmDialog: vi.fn(async () => true) }));

import DaftarPanel from "./DaftarPanel";

const decision = {
  id: "decision:7",
  kind: "decision",
  content: "Use Postgres, not SQLite — many people write at once",
  source: { kind: "chat", session_id: "c1", label: "you decided, in a chat (Booking service)" },
  created: "2026-11-27T10:00:00Z",
  last_used: "",
  expires: "",
  editable: false,
  forgettable: true,
};
const handoff = {
  id: "handoff:project:w1",
  kind: "handoff",
  content: "## Goal\n- A booking service\n## Open items\n- Write the migration",
  source: { kind: "chat", session_id: "c1", label: "a project's hand-off, rewritten after each answer" },
  created: "2026-11-27T10:05:00Z",
  last_used: "",
  expires: "",
  editable: false,
  forgettable: true,
};

function client(entries: unknown[]) {
  const posts: { path: string; body?: Record<string, unknown> }[] = [];
  const api = {
    get: vi.fn(async (path: string) => {
      const kind = new URLSearchParams(path.split("?")[1] ?? "").get("kind");
      const shown = (entries as { kind: string }[]).filter((entry) => !kind || entry.kind === kind);
      return { entries: shown, counts: { decision: 1, handoff: 1 } };
    }),
    post: vi.fn(async (path: string, body?: Record<string, unknown>) => {
      posts.push({ path, body });
      return { forgotten: { decision: 1 } };
    }),
    put: vi.fn(), patch: vi.fn(), delete: vi.fn(),
  } as unknown as ApiClient;
  return { api, posts };
}

describe("DaftarPanel: decisions", () => {
  afterEach(cleanup);

  it("shows each decision with its reason and where it was made, and forgets one", async () => {
    const { api, posts } = client([decision, handoff]);
    render(<DaftarPanel api={api} />);
    expect(await screen.findByText("Use Postgres, not SQLite")).toBeTruthy();
    expect(screen.getByText(/because many people write at once/)).toBeTruthy();
    expect(screen.getByText(/you decided, in a chat \(Booking service\)/)).toBeTruthy();
    expect(screen.getByText(/A booking service/)).toBeTruthy();
    // Decisions are append-only: forgotten, never edited.
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Forget" })[0]);
    await waitFor(() => expect(posts).toEqual([{ path: "/daftar/forget", body: { ids: ["decision:7"] } }]));
  });

  it("filters to decisions, with a next step when there are none", async () => {
    const { api } = client([]);
    render(<DaftarPanel api={api} />);
    fireEvent.click(await screen.findByRole("tab", { name: /Decisions/ }));
    expect(await screen.findByText(/Tell MIZAN in a chat what you decided and why/)).toBeTruthy();
  });
});
