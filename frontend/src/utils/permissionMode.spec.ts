import { describe, expect, it } from "vitest";
import {
  agentPermissionMode, baselinePermissionMode, chatPermissionMode, DEFAULT_PERMISSION_MODE, forgetPermissionMode,
  loadPermissionMode, PERMISSION_STORAGE_KEY, rememberPermissionMode, savedPermissionMode, serverPermissionDefault,
} from "./permissionMode";

function memory() {
  const items = new Map<string, string>();
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
    items,
  };
}

const broken = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
};

describe("permission mode defaulting", () => {
  it("is fully autonomous when nothing was chosen anywhere", () => {
    expect(DEFAULT_PERMISSION_MODE).toBe("auto");
    expect(loadPermissionMode(undefined, memory())).toBe("auto");
    expect(chatPermissionMode({})).toEqual({ mode: "auto", source: "default" });
  });

  it("uses the server's default for the person when it names a known mode", () => {
    expect(loadPermissionMode("ask", memory())).toBe("ask");
    expect(loadPermissionMode("everything", memory())).toBe("auto");
    expect(baselinePermissionMode("plan")).toBe("plan");
    expect(baselinePermissionMode(null)).toBe("auto");
  });

  it("reads default_permission_mode from whichever loaded response has it", () => {
    expect(serverPermissionDefault({ user_id: "u1" }, { default_permission_mode: "auto_edits" })).toBe("auto_edits");
    expect(serverPermissionDefault({ default_permission_mode: "nonsense" }, null, undefined, [])).toBeNull();
    expect(serverPermissionDefault()).toBeNull();
  });

  it("keeps the browser's last pick above the server default, and forgets it on reset", () => {
    const store = memory();
    rememberPermissionMode("ask", store);
    expect(store.items.get(PERMISSION_STORAGE_KEY)).toBe("ask");
    expect(loadPermissionMode("auto", store)).toBe("ask");
    forgetPermissionMode(store);
    expect(savedPermissionMode(store)).toBeNull();
    expect(loadPermissionMode("auto_edits", store)).toBe("auto_edits");
  });

  it("ignores a saved value that is not a mode, and survives storage that throws", () => {
    const store = memory();
    store.setItem(PERMISSION_STORAGE_KEY, "yolo");
    expect(savedPermissionMode(store)).toBeNull();
    expect(loadPermissionMode(undefined, broken)).toBe("auto");
    expect(() => rememberPermissionMode("plan", broken)).not.toThrow();
    expect(() => forgetPermissionMode(broken)).not.toThrow();
  });

  it("takes the agent's own mode until the person picks one in the chat", () => {
    expect(agentPermissionMode({ settings: { permission_mode: "ask" } })).toBe("ask");
    expect(agentPermissionMode({ settings: { permission_mode: null } })).toBeNull();
    expect(agentPermissionMode({})).toBeNull();
    expect(agentPermissionMode(null)).toBeNull();

    // An agent's mode wins over the browser's last pick and the server default…
    expect(chatPermissionMode({ agent: "ask", saved: "auto", serverDefault: "auto" })).toEqual({ mode: "ask", source: "agent" });
    // …but not over a mode picked in this chat.
    expect(chatPermissionMode({ chosen: "auto", agent: "ask", saved: "plan" })).toEqual({ mode: "auto", source: "chat" });
    // With no agent mode, the browser's pick, then the server's default.
    expect(chatPermissionMode({ saved: "plan", serverDefault: "ask" })).toEqual({ mode: "plan", source: "saved" });
    expect(chatPermissionMode({ serverDefault: "ask" })).toEqual({ mode: "ask", source: "server" });
  });
});
