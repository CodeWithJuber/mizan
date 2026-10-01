import { authFetch } from "./authFetch.ts";
declare const process: { exit(code: number): void };
const values = new Map<string, string>();
let unauthorized = 0;
Object.defineProperty(globalThis, "localStorage", {
  value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  },
  configurable: true,
});
Object.defineProperty(globalThis, "window", {
  value: {
    dispatchEvent: () => {
      unauthorized++;
      return true;
    },
  },
  configurable: true,
});
let resolve!: (response: Response) => void;
globalThis.fetch = (() =>
  new Promise<Response>((done) => {
    resolve = done;
  })) as typeof fetch;
values.set("mizan_token", "request-token-A");
const stale = authFetch("/api/status");
values.set("mizan_token", "new-login-token-B");
resolve(new Response("{}", { status: 401 }));
await stale;
if (values.get("mizan_token") !== "new-login-token-B" || unauthorized)
  throw new Error("Stale request logged out a newer session");
const current = authFetch("/api/status");
resolve(new Response("{}", { status: 401 }));
await current;
if (values.has("mizan_token") || unauthorized !== 1)
  throw new Error("Current unauthorized session was not invalidated");
console.log("2 auth request race checks passed");
