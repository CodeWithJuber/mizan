/**
 * historySync — resilient chat-history loading and client/server merging.
 *
 * Two problems solved here:
 *  1. Flaky networks: `fetchChatHistoryWithRetry` retries the
 *     GET /api/chat/{sid} fetch with exponential backoff (default 3 attempts)
 *     so a single dropped request doesn't leave the chat empty.
 *  2. Divergence: `mergeHistoryMessages` merges server history with locally
 *     held messages (cache render + optimistic user echoes) without
 *     duplicating messages that exist in both.
 *
 * DEDUPE KEY (documented — do not change casually):
 *   - Server messages carry a numeric DB `id` → key `srv:<id>`.
 *   - Everything else (optimistic echoes, cache entries) → key
 *     `local:<role>:<ts>:<hash(content)>`, a djb2 hash of the content.
 *   - Second pass: a local message is also dropped when a server message
 *     has the SAME role AND byte-identical content (covers the optimistic
 *     user echo: locally it has a Date.now() id, from the server it has a
 *     DB id, so the primary keys never match but role+content do).
 * Merge order: all server messages first (server order), then surviving
 * local-only messages in their local order (these are always the newest).
 */

export interface HistoryMessage {
  id?: number | string;
  role: string;
  content: string;
  agent_id?: string;
  agent?: string;
  created_at?: string;
  ts?: string;
}

/** Small djb2 hash for the local dedupe key — not cryptographic, just stable. */
function contentHash(content: string): string {
  let h = 5381;
  for (let i = 0; i < content.length; i++) {
    h = ((h << 5) + h + content.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(36);
}

export function historyDedupeKey(m: HistoryMessage): string {
  if (typeof m.id === "number" && Number.isFinite(m.id)) {
    return `srv:${m.id}`;
  }
  return `local:${m.role}:${m.ts ?? m.created_at ?? ""}:${contentHash(m.content ?? "")}`;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export interface HistoryFetchResult {
  ok: boolean;
  /** Raw server messages (the `messages` array of the response body). */
  messages: HistoryMessage[];
  /** Set when the session is unknown server-side (HTTP 404). */
  missing: boolean;
  /** The last error, when ok === false. */
  error?: Error;
}

/**
 * GET /api/chat/{sid} with exponential backoff.
 *
 * @param fetchHistory a thunk performing ONE fetch attempt and returning the
 *   raw Response (kept injectable so App.tsx's authFetch stays in one place
 *   and unit tests can stub it).
 */
export async function fetchChatHistoryWithRetry(
  fetchHistory: () => Promise<Response>,
  attempts = 3,
  baseDelayMs = 600,
): Promise<HistoryFetchResult> {
  let lastError: Error | undefined;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const res = await fetchHistory();
      if (res.status === 404) {
        return { ok: true, messages: [], missing: true };
      }
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      const messages = Array.isArray(data?.messages) ? data.messages : [];
      return { ok: true, messages, missing: false };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < attempts) {
        await sleep(baseDelayMs * 2 ** (attempt - 1));
      }
    }
  }
  return { ok: false, messages: [], missing: false, error: lastError };
}

/**
 * Merge server history with locally held messages.
 * Server wins on content; local-only messages are appended in order.
 */
export function mergeHistoryMessages<T extends HistoryMessage>(
  server: T[],
  local: T[],
): T[] {
  const serverKeys = new Set(server.map(historyDedupeKey));
  // role+content fingerprints of server messages, for the optimistic-echo pass
  const serverFingerprints = new Set(
    server.map((m) => `${m.role}\u0000${m.content ?? ""}`),
  );
  const extras = local.filter((m) => {
    if (serverKeys.has(historyDedupeKey(m))) return false;
    return !serverFingerprints.has(`${m.role}\u0000${m.content ?? ""}`);
  });
  return [...server, ...extras];
}
