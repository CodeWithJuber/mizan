import { describe, expect, it } from "vitest";
import { chatWorkspace, MAX_CHATS, migrateLegacyWorkspace, setChatWorkspace } from "./chatWorkspaces";

function memory() {
  const items = new Map<string, string>();
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
    items,
  };
}

describe("chat projects", () => {
  it("keeps each chat's project apart and forgets one on unbind", () => {
    const store = memory();
    setChatWorkspace("chat-a", "w1", store);
    setChatWorkspace("chat-b", "w2", store);
    expect(chatWorkspace("chat-a", store)).toBe("w1");
    expect(chatWorkspace("chat-b", store)).toBe("w2");
    expect(chatWorkspace("chat-new", store)).toBe("");
    setChatWorkspace("chat-a", "", store);
    expect(chatWorkspace("chat-a", store)).toBe("");
    expect(chatWorkspace("chat-b", store)).toBe("w2");
  });

  it("keeps only the most recent chats", () => {
    const store = memory();
    for (let index = 0; index <= MAX_CHATS; index++) setChatWorkspace(`chat-${index}`, `w${index}`, store);
    expect(chatWorkspace("chat-0", store)).toBe("");
    expect(chatWorkspace(`chat-${MAX_CHATS}`, store)).toBe(`w${MAX_CHATS}`);
    // Binding an old chat again makes it recent.
    setChatWorkspace("chat-1", "w1", store);
    setChatWorkspace("chat-extra", "wx", store);
    expect(chatWorkspace("chat-1", store)).toBe("w1");
  });

  it("gives the old shared project to the open chat once, then drops it", () => {
    const store = memory();
    store.setItem("mizan_workspace_id", "shared");
    migrateLegacyWorkspace("chat-a", store);
    expect(chatWorkspace("chat-a", store)).toBe("shared");
    expect(store.getItem("mizan_workspace_id")).toBeNull();
    migrateLegacyWorkspace("chat-b", store);
    expect(chatWorkspace("chat-b", store)).toBe("");
  });

  it("survives a broken store", () => {
    const store = memory();
    store.setItem("mizan_chat_workspaces", "{not json");
    expect(chatWorkspace("chat-a", store)).toBe("");
    setChatWorkspace("chat-a", "w1", store);
    expect(chatWorkspace("chat-a", store)).toBe("w1");
  });
});
