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
 * Cache key: `mizan_chat_cache_v2:<token_sha256>:<session_id>` — versioned so a future
 * schema change can bump the version and ignore stale entries.
 */

import type { ChatMessage } from "../types.ts";

export interface CachedChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  agent?: string;
  model?: string;
  requestId?: string;
  messageId?: string;
  notStarted?: boolean;
  meta?: ChatMessage["meta"];
  error?: ChatMessage["error"];
  stopped?: boolean;
  interrupted?: boolean;
  ts: string;
  /** Epoch ms when this entry was written — used for TTL pruning. */
  cachedAt: number;
}

const CACHE_VERSION = "v2";
const MAX_CACHED_MESSAGES = 200;
/** Drop cache entries older than 7 days on read. */
const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_DRAFT_CHARACTERS = 1_000_000;
let preparedNamespace: { token: string; hash: string } | null = null;
const draftRevisions = new Map<string, number>();
let draftRevision = 0;
function nextDraftWrite(sessionId: string, ownerToken: string, requestId: string) {
  const key = `${ownerToken}:${sessionId}:${requestId}`;
  const revision = ++draftRevision;
  draftRevisions.set(key, revision);
  if (draftRevisions.size > 200) draftRevisions.delete(draftRevisions.keys().next().value!);
  return () => draftRevisions.get(key) === revision;
}

const DB_NAME = "mizan-chat-cache";
const STORE_NAME = "sessions";

function cacheKey(sessionId: string): string {
  return `mizan_chat_cache_${CACHE_VERSION}:${sessionId}`;
}

// Authentication namespaces prevent another signed-in account seeing cached history.
// The token itself is never written to the cache key or message records.
async function authNamespace(
  sessionId: string,
  expectedToken?: string,
): Promise<{ key: string; token: string } | null> {
  const token = localStorage.getItem("mizan_token");
  if (!token || (expectedToken != null && token !== expectedToken) || !globalThis.crypto?.subtle) return null;
  if (preparedNamespace?.token === token) return { key: `${preparedNamespace.hash}:${sessionId}`, token };
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(token),
  );
  const hash = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  if (localStorage.getItem("mizan_token") !== token) return null;
  preparedNamespace = { token, hash };
  return { key: `${hash}:${sessionId}`, token };
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
  model?: string;
  requestId?: string;
  messageId?: string;
  notStarted?: boolean;
  meta?: ChatMessage["meta"];
  error?: ChatMessage["error"];
  stopped?: boolean;
  interrupted?: boolean;
  ts: string;
}

/**
 * Persist the current session's messages. Fire-and-forget from the caller —
 * failures are silent (the cache is a render fallback, never critical).
 */
export async function cacheMessages(
  sessionId: string,
  messages: CacheableMessage[],
  expectedToken?: string,
): Promise<void> {
  if (!sessionId || messages.length === 0) return;
  const namespace = await authNamespace(sessionId, expectedToken);
  if (!namespace) return;
  const now = Date.now();
  const trimmed = messages.slice(-MAX_CACHED_MESSAGES).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    agent: m.agent,
    model: m.model,
    requestId: m.requestId,
    messageId: m.messageId,
    notStarted: m.notStarted,
    meta: m.meta,
    error: m.error,
    stopped: m.stopped,
    interrupted: m.interrupted,
    ts: m.ts,
    cachedAt: now,
  }));
  // Prefer IndexedDB; fall back to localStorage only if IDB failed.
  const ok = await idbWrite(namespace.key, trimmed);
  if (!ok && localStorage.getItem("mizan_token") === namespace.token)
    lsWrite(namespace.key, trimmed);
}

export interface CachedChatDraft {
  message: CacheableMessage;
  cachedAt: number;
}

function draftRecords(key: string): CachedChatDraft[] {
  try {
    const raw = localStorage.getItem(`${cacheKey(key)}:draft`);
    if (!raw) return [];
    const record = JSON.parse(raw);
    const records: CachedChatDraft[] = Array.isArray(record.drafts) ? record.drafts : [record];
    return records.filter((draft) => draft && Number.isFinite(draft.cachedAt) && Date.now() - draft.cachedAt < CACHE_TTL_MS &&
      typeof draft.message?.requestId === "string" && draft.message.requestId.length <= 100 &&
      typeof draft.message.content === "string" && draft.message.content.length <= MAX_DRAFT_CHARACTERS);
  } catch { return []; }
}

/** A separate bounded draft survives reload without replacing saved history. */
function writeDraft(key: string, message: CacheableMessage): boolean {
  if (!message.requestId || message.content.length > MAX_DRAFT_CHARACTERS) return false;
  const draft: CacheableMessage = {
    id: message.id, role: "assistant", content: message.content, ts: message.ts,
    agent: message.agent, model: message.model,
    requestId: message.requestId, messageId: message.messageId,
    stopped: message.stopped, interrupted: !message.stopped,
    error: message.error ? { code: message.error.code, message: message.error.message.slice(0, 1000) } : undefined,
  };
  try {
    const records = draftRecords(key).filter((record) => record.message.requestId !== draft.requestId);
    records.push({ message: draft, cachedAt: Date.now() });
    // Retain older local-only replies when the next request begins. If the
    // bounded draft budget is full, keep existing text instead of evicting it.
    if (records.length > 8 || records.reduce((total, record) => total + record.message.content.length, 0) > 2_000_000)
      return false;
    localStorage.setItem(`${cacheKey(key)}:draft`, JSON.stringify({ drafts: records }));
    return true;
  } catch { return false; }
}

export async function cacheChatDraft(sessionId: string, message: CacheableMessage, ownerToken: string): Promise<boolean> {
  if (!message.requestId || message.content.length > MAX_DRAFT_CHARACTERS) return false;
  const current = nextDraftWrite(sessionId, ownerToken, message.requestId);
  const namespace = await authNamespace(sessionId, ownerToken);
  return Boolean(current() && namespace && localStorage.getItem("mizan_token") === ownerToken && writeDraft(namespace.key, message));
}

/** pagehide cannot wait for crypto/IndexedDB; use the already prepared owner hash. */
export function cacheChatDraftNow(sessionId: string, message: CacheableMessage, ownerToken: string): boolean {
  if (preparedNamespace?.token !== ownerToken || localStorage.getItem("mizan_token") !== ownerToken) return false;
  if (!message.requestId || message.content.length > MAX_DRAFT_CHARACTERS) return false;
  nextDraftWrite(sessionId, ownerToken, message.requestId);
  return writeDraft(`${preparedNamespace.hash}:${sessionId}`, message);
}

export async function readCachedChatDraft(sessionId: string): Promise<CachedChatDraft | null> {
  const records = await readCachedChatDrafts(sessionId);
  return records[records.length - 1] ?? null;
}

export async function readCachedChatDrafts(sessionId: string): Promise<CachedChatDraft[]> {
  const namespace = await authNamespace(sessionId);
  if (!namespace || localStorage.getItem("mizan_token") !== namespace.token) return [];
  return draftRecords(namespace.key);
}

export async function clearCachedChatDraft(sessionId: string, requestId: string, ownerToken: string): Promise<void> {
  const current = nextDraftWrite(sessionId, ownerToken, requestId);
  const namespace = await authNamespace(sessionId, ownerToken);
  if (!namespace || !current()) return;
  try {
    const key = `${cacheKey(namespace.key)}:draft`;
    if (localStorage.getItem("mizan_token") !== ownerToken) return;
    const records = draftRecords(namespace.key).filter((record) => record.message.requestId !== requestId);
    if (records.length) localStorage.setItem(key, JSON.stringify({ drafts: records }));
    else localStorage.removeItem(key);
  } catch { /* best effort */ }
}

/** Read cached messages for a session. Returns null when nothing usable is cached. */
export async function readCachedMessages(
  sessionId: string,
): Promise<CacheableMessage[] | null> {
  if (!sessionId) return null;
  const namespace = await authNamespace(sessionId);
  if (!namespace) return null;
  const fromIdb = await idbRead(namespace.key);
  if (localStorage.getItem("mizan_token") !== namespace.token) return null;
  return fromIdb ?? lsRead(namespace.key);
}

/** Drop the cache for a session (e.g. after the user deletes it). */
export async function clearCachedMessages(sessionId: string): Promise<void> {
  const namespace = await authNamespace(sessionId);
  if (!namespace) return;
  await idbDelete(namespace.key);
  try {
    localStorage.removeItem(cacheKey(namespace.key));
    localStorage.removeItem(`${cacheKey(namespace.key)}:draft`);
  } catch {
    /* ignore */
  }
}
