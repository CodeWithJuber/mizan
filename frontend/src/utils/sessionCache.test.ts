import { cacheMessages, readCachedMessages } from "./sessionCache.ts";
declare const process: { exit(code: number): void };
const values = new Map<string, string>();
Object.defineProperty(globalThis, "localStorage", {
  value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  },
  configurable: true,
});
const message = {
  id: 1,
  role: "user" as const,
  content: "Private history",
  ts: "12:00",
};
values.set("mizan_token", "owner-A-token");
await cacheMessages("same-session", [message]);
if ((await readCachedMessages("same-session"))?.[0].content !== message.content)
  throw new Error("Current owner cache missing");
if ([...values.keys()].some((key) => key.includes("owner-A-token")))
  throw new Error("Token leaked into cache key");
const failedMessage = {
  id: 2, role: "assistant" as const, content: "", ts: "12:01", model: "mizan-owned",
  error: { code: "output_budget_exhausted", message: "The model reached its output limit." },
  meta: {
    model: "mizan-owned", output_tokens: 200, reasoning_tokens: 200,
    completion_status: "incomplete" as const, answer_delivered: false, task_verified: false,
    timings: { provider_ms: 1200, total_ms: 2300 },
    owned_checkpoint: { source: "registry" as const, sha256: "a".repeat(64), generation: 2 },
  },
};
const partialMessage = { ...failedMessage, id: 3, content: "  Partial\n```python\n", stopped: false };
const stoppedMessage = { ...message, id: 4, role: "assistant" as const, stopped: true };
await cacheMessages("same-session", [message, failedMessage, partialMessage, stoppedMessage]);
const restored = await readCachedMessages("same-session");
if (restored?.[1].content !== "" || restored[1].error?.message !== failedMessage.error.message)
  throw new Error("Empty cached failure lost its visible notice");
if (restored[1].model !== failedMessage.model || JSON.stringify(restored[1].meta) !== JSON.stringify(failedMessage.meta))
  throw new Error("Cached failure lost usage/timing/checkpoint receipts");
if (restored[2].content !== partialMessage.content || restored[2].error?.code !== failedMessage.error.code || restored[2].stopped !== false)
  throw new Error("Cached partial failure lost bytes or became user-stopped");
if (restored[3].stopped !== true)
  throw new Error("Cached cancelled response lost stopped state");
values.set("mizan_token", "owner-B-token");
if ((await readCachedMessages("same-session")) !== null)
  throw new Error("Another account read cached history");
values.set(
  "mizan_chat_cache_v1:legacy",
  JSON.stringify({ messages: [message], cachedAt: Date.now() }),
);
if ((await readCachedMessages("legacy")) !== null)
  throw new Error("Legacy unscoped cache was exposed");
values.delete("mizan_token");
if ((await readCachedMessages("same-session")) !== null)
  throw new Error("Anonymous cache read");
console.log("9 cache ownership/failure checks passed");
