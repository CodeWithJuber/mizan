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
console.log("5 cache ownership checks passed");
