import { afterEach, describe, expect, it } from "vitest";
import { LEGACY_TAB_ROUTES, routeForLegacyTab, takeLegacyTab } from "./legacyTabs";

describe("legacy tab routes", () => {
  afterEach(() => localStorage.clear());

  it("maps every tab the old sidebar had", () => {
    const old = [
      "chat", "workspace", "agents", "terminal", "queue", "majlis", "perception", "memory", "watchers",
      "knowledge", "notebooks", "skills", "connectors", "plugins", "scanner", "compare", "debug",
      "providers", "channels", "automation", "security", "settings", "developer", "ruh-model", "integrations",
    ];
    for (const tab of old) expect(LEGACY_TAB_ROUTES[tab], tab).toMatch(/^\//);
  });

  it("sends an unknown tab to the chat", () => {
    expect(routeForLegacyTab("gone")).toBe("/chat");
  });

  it("reads the saved tab once and forgets it", () => {
    localStorage.setItem("mizan_active_tab", "memory");
    expect(takeLegacyTab()).toBe("/library/memory");
    expect(takeLegacyTab()).toBeNull();
  });
});
