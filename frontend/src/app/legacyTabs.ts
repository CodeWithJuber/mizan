/**
 * The app used to keep the open page in localStorage ("mizan_active_tab")
 * and messages could carry a button naming a tab. Each old tab id maps to its
 * route now.
 */
export const LEGACY_TAB_ROUTES: Record<string, string> = {
  chat: "/chat",
  workspace: "/code",
  agents: "/agents",
  majlis: "/agents/majlis",
  terminal: "/automations/tasks",
  queue: "/automations/queue",
  watchers: "/automations/watchers",
  automation: "/automations/schedules",
  memory: "/library/memory",
  knowledge: "/library/knowledge",
  notebooks: "/library/notebooks",
  skills: "/settings/skills",
  connectors: "/settings/connectors",
  integrations: "/settings/connectors",
  channels: "/settings/channels",
  security: "/settings/account",
  settings: "/settings",
  providers: "/settings/developer/providers",
  plugins: "/settings/developer/plugins",
  scanner: "/settings/developer/scanner",
  compare: "/settings/developer/compare",
  debug: "/settings/developer/debug",
  perception: "/settings/developer/perception",
  developer: "/settings/developer",
  "ruh-model": "/settings/developer/ruh",
};

export function routeForLegacyTab(tab: string): string {
  return LEGACY_TAB_ROUTES[tab] ?? "/chat";
}

/** Read the old saved tab once (then forget it): where a returning visit lands. */
export function takeLegacyTab(): string | null {
  try {
    const tab = localStorage.getItem("mizan_active_tab");
    if (tab === null) return null;
    localStorage.removeItem("mizan_active_tab");
    return routeForLegacyTab(tab);
  } catch {
    return null;
  }
}
