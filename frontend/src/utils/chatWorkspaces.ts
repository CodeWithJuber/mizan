/**
 * Which project each chat works on, kept in the browser so a chat opens with its
 * project before the server answers. The server's binding always wins: chat history
 * (`workspace_id`), `chat_complete` and the `workspace` event overwrite it.
 */

const KEY = "mizan_chat_workspaces";
/** Before chats owned their project, one project was shared by every chat. */
const LEGACY_KEY = "mizan_workspace_id";
export const MAX_CHATS = 200;

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const browserStore = (): Store | null => {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
};

/** Pairs of [chat, project], oldest first. */
function read(store: Store): [string, string][] {
  try {
    const value: unknown = JSON.parse(store.getItem(KEY) || "[]");
    return Array.isArray(value)
      ? value.filter(
          (pair): pair is [string, string] =>
            Array.isArray(pair) && typeof pair[0] === "string" && typeof pair[1] === "string",
        )
      : [];
  } catch {
    return [];
  }
}

function write(store: Store, pairs: [string, string][]) {
  try {
    store.setItem(KEY, JSON.stringify(pairs.slice(-MAX_CHATS)));
  } catch {
    /* a convenience only: the server keeps the binding */
  }
}

/** The project this chat works on, or "" when it has none. */
export function chatWorkspace(sessionId: string, store: Store | null = browserStore()): string {
  if (!store || !sessionId) return "";
  return read(store).find(([chat]) => chat === sessionId)?.[1] ?? "";
}

/** Bind (or, with "", unbind) a chat's project; the most recent chats are kept. */
export function setChatWorkspace(
  sessionId: string,
  workspaceId: string,
  store: Store | null = browserStore(),
) {
  if (!store || !sessionId) return;
  const pairs = read(store).filter(([chat]) => chat !== sessionId);
  if (workspaceId) pairs.push([sessionId, workspaceId]);
  write(store, pairs);
}

/** Signing out (or in as someone else) forgets every chat's project here. */
export function clearChatWorkspaces(store: Store | null = browserStore()) {
  try {
    store?.removeItem(KEY);
  } catch {
    /* nothing to forget */
  }
}

/** The project every chat used to share becomes this chat's, once. */
export function migrateLegacyWorkspace(sessionId: string, store: Store | null = browserStore()) {
  if (!store) return;
  let legacy: string | null = null;
  try {
    legacy = store.getItem(LEGACY_KEY);
    store.removeItem(LEGACY_KEY);
  } catch {
    return;
  }
  if (legacy && sessionId && !chatWorkspace(sessionId, store)) setChatWorkspace(sessionId, legacy, store);
}
