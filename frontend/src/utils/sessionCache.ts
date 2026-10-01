/**
 * sessionCache — client-side cache of the current chat session's messages.
 *
 * Purpose: the chat UI must NEVER render empty when data exists locally
 * (e.g. flaky mobile network on refresh). On mount we render the cached
 * messages immediately while the server fetch is in flight, then merge
 * the server history when it arrives.
 *
 * Storage: IndexedDB (preferred — survives quota pressure better and is
 * async so it never blocks the render path) with a synchronous
 * localStorage fallback when IndexedDB is unavailable (private mode, etc).
 *
 * Cache key: `mizan_chat_cache_v1:<session_id>` — versioned so a future
 * schema change can bump the version and ignore stale entries.
 */

export interface CachedChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  agent?: string;
  ts: string;
  /** Epoch ms when this entry was written — used for TTL pruning. */
  cachedAt: number;
}

const CACHE_VERSION = "v1";
const MAX_CACHED_MESSAGES = 200;
/** Drop cache entries older than 7 days on read. */
const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

const DB_NAME = "mizan-chat-cache";
const STORE_NAME = "sessions";

function cacheKey(sessionId: string): string {
  return `mizan_chat_cache_${CACHE_VERSION}:${sessionId}`;
}

// ---------- IndexedDB layer ----------

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> | null {
  if (typeof indexedDB === "undefined") return null;
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore(STORE_NAME);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

async function idbWrite(
  sessionId: string,
  messages: CachedChatMessage[],
): Promise<boolean> {
  try {
    const db = await openDb();
    if (!db) return false;
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(
        { messages, cachedAt: Date.now() },
        cacheKey(sessionId),
      );
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    return true;
  } catch {
    return false;
  }
}

async function idbRead(sessionId: string): Promise<CachedChatMessage[] | null> {
  try {
    const db = await openDb();
    if (!db) return null;
    const record = await new Promise<{
      messages: CachedChatMessage[];
      cachedAt: number;
    } | null>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(cacheKey(sessionId));
      req.onsuccess = () =>
        resolve(
          (req.result as
            { messages: CachedChatMessage[]; cachedAt: number } | undefined) ??
            null,
        );
      req.onerror = () => reject(req.error);
    });
    if (!record || !Array.isArray(record.messages)) return null;
    if (Date.now() - record.cachedAt > CACHE_TTL_MS) {
      void idbDelete(sessionId);
      return null;
    }
    return record.messages;
  } catch {
    return null;
  }
}

async function idbDelete(sessionId: string): Promise<void> {
  try {
    const db = await openDb();
    if (!db) return;
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(cacheKey(sessionId));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    /* best effort */
  }
}

// ---------- localStorage fallback ----------

function lsWrite(sessionId: string, messages: CachedChatMessage[]): boolean {
  try {
    localStorage.setItem(
      cacheKey(sessionId),
      JSON.stringify({ messages, cachedAt: Date.now() }),
    );
    return true;
  } catch {
    return false;
  }
}

function lsRead(sessionId: string): CachedChatMessage[] | null {
  try {
    const raw = localStorage.getItem(cacheKey(sessionId));
    if (!raw) return null;
    const record = JSON.parse(raw) as {
      messages: CachedChatMessage[];
      cachedAt: number;
    };
    if (!Array.isArray(record.messages)) return null;
    if (Date.now() - record.cachedAt > CACHE_TTL_MS) {
      try {
        localStorage.removeItem(cacheKey(sessionId));
      } catch {
        /* ignore */
      }
      return null;
    }
    return record.messages;
  } catch {
    return null;
  }
}

// ---------- public API ----------

export interface CacheableMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  agent?: string;
  ts: string;
}

/**
 * Persist the current session's messages. Fire-and-forget from the caller —
 * failures are silent (the cache is a render fallback, never critical).
 */
export async function cacheMessages(
  sessionId: string,
  messages: CacheableMessage[],
): Promise<void> {
  if (!sessionId || messages.length === 0) return;
  const now = Date.now();
  const trimmed = messages.slice(-MAX_CACHED_MESSAGES).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    agent: m.agent,
    ts: m.ts,
    cachedAt: now,
  }));
  // Prefer IndexedDB; fall back to localStorage only if IDB failed.
  const ok = await idbWrite(sessionId, trimmed);
  if (!ok) lsWrite(sessionId, trimmed);
}

/** Read cached messages for a session. Returns null when nothing usable is cached. */
export async function readCachedMessages(
  sessionId: string,
): Promise<CacheableMessage[] | null> {
  if (!sessionId) return null;
  const fromIdb = await idbRead(sessionId);
  if (fromIdb) return fromIdb;
  return lsRead(sessionId);
}

/** Drop the cache for a session (e.g. after the user deletes it). */
export async function clearCachedMessages(sessionId: string): Promise<void> {
  await idbDelete(sessionId);
  try {
    localStorage.removeItem(cacheKey(sessionId));
  } catch {
    /* ignore */
  }
}
