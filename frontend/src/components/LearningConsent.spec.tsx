import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const calls: { url: string; init?: RequestInit }[] = [];
let saved: { key: string; value: string }[] = [];

vi.mock("../utils/authFetch", () => ({
  authFetch: vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const body = init?.method === "PUT" ? { ok: true } : { preferences: saved };
    return new Response(JSON.stringify(body), { status: 200 });
  }),
}));

import { LearningConsent } from "./LearningConsent";

describe("LearningConsent", () => {
  afterEach(() => {
    cleanup();
    calls.length = 0;
    saved = [];
  });

  it("starts with learning on and training off when nothing was chosen", async () => {
    render(<LearningConsent />);
    const learning = screen.getByRole("switch", { name: "Learn from my chats for me" });
    const training = screen.getByRole("switch", { name: "Let my words help train MIZAN's own model" });
    await waitFor(() => expect(learning.getAttribute("aria-disabled")).not.toBe("true"));
    expect(learning.getAttribute("aria-checked")).toBe("true");
    expect(training.getAttribute("aria-checked")).toBe("false");
  });

  it("shows the person's saved choices and saves a change as on or off", async () => {
    saved = [{ key: "learning", value: "off" }, { key: "training", value: "on" }];
    render(<LearningConsent />);
    const learning = screen.getByRole("switch", { name: "Learn from my chats for me" });
    await waitFor(() => expect(learning.getAttribute("aria-checked")).toBe("false"));
    fireEvent.click(learning);
    await screen.findByText("Saved. It applies from your next message.");
    const put = calls.find((call) => call.init?.method === "PUT");
    expect(put?.url).toMatch(/\/chat\/preferences\/learning$/);
    expect(JSON.parse(String(put?.init?.body))).toEqual({ value: "on" });
    expect(learning.getAttribute("aria-checked")).toBe("true");
  });
});
