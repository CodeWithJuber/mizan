/**
 * Which permission mode a chat runs in. MIZAN acts on its own by default
 * ("auto"); the server may name another default for the person, an agent may
 * set its own, and a mode the person picks wins for that chat.
 *
 * Order, first that is set:
 *   1. the mode the person picked in this chat
 *   2. the chosen agent's `settings.permission_mode`
 *   3. the mode the person last picked in this browser
 *   4. the server's `default_permission_mode` for the person
 *   5. "auto"
 */
import { PERMISSION_MODES, type PermissionMode } from "./agentActivity.ts";

export const DEFAULT_PERMISSION_MODE: PermissionMode = "auto";
export const PERMISSION_STORAGE_KEY = "mizan_permission_mode";

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export const isPermissionMode = (value: unknown): value is PermissionMode =>
  typeof value === "string" && (PERMISSION_MODES as readonly string[]).includes(value);

function browserStore(): Store | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

/** The mode the person last picked in this browser, if any (a per-viewer convenience). */
export function savedPermissionMode(store: Store | null = browserStore()): PermissionMode | null {
  try {
    const saved = store?.getItem(PERMISSION_STORAGE_KEY);
    return isPermissionMode(saved) ? saved : null;
  } catch {
    return null;
  }
}

export function rememberPermissionMode(mode: PermissionMode, store: Store | null = browserStore()): void {
  try {
    store?.setItem(PERMISSION_STORAGE_KEY, mode);
  } catch {
    // per-viewer convenience only
  }
}

export function forgetPermissionMode(store: Store | null = browserStore()): void {
  try {
    store?.removeItem(PERMISSION_STORAGE_KEY);
  } catch {
    // per-viewer convenience only
  }
}

/** The first valid `default_permission_mode` in the responses the app loaded (auth/me, …). */
export function serverPermissionDefault(...sources: unknown[]): PermissionMode | null {
  for (const source of sources) {
    if (source && typeof source === "object" && !Array.isArray(source)) {
      const value = (source as Record<string, unknown>).default_permission_mode;
      if (isPermissionMode(value)) return value;
    }
  }
  return null;
}

/** What a chat starts in when neither the person nor the agent chose: the server's default, else "auto". */
export function baselinePermissionMode(serverDefault?: unknown): PermissionMode {
  return isPermissionMode(serverDefault) ? serverDefault : DEFAULT_PERMISSION_MODE;
}

/** The mode for a new chat with no agent mode: the browser's saved choice, else the server's default, else "auto". */
export function loadPermissionMode(serverDefault?: unknown, store: Store | null = browserStore()): PermissionMode {
  return savedPermissionMode(store) ?? baselinePermissionMode(serverDefault);
}

/** The mode an agent asks for, from its settings (older servers send none). */
export function agentPermissionMode(agent: { settings?: unknown } | null | undefined): PermissionMode | null {
  const settings = agent?.settings;
  if (!settings || typeof settings !== "object") return null;
  const mode = (settings as Record<string, unknown>).permission_mode;
  return isPermissionMode(mode) ? mode : null;
}

export type PermissionSource = "chat" | "agent" | "saved" | "server" | "default";

export function chatPermissionMode(options: {
  chosen?: PermissionMode | null;
  agent?: PermissionMode | null;
  saved?: PermissionMode | null;
  serverDefault?: PermissionMode | null;
}): { mode: PermissionMode; source: PermissionSource } {
  if (isPermissionMode(options.chosen)) return { mode: options.chosen, source: "chat" };
  if (isPermissionMode(options.agent)) return { mode: options.agent, source: "agent" };
  if (isPermissionMode(options.saved)) return { mode: options.saved, source: "saved" };
  if (isPermissionMode(options.serverDefault)) return { mode: options.serverDefault, source: "server" };
  return { mode: DEFAULT_PERMISSION_MODE, source: "default" };
}
