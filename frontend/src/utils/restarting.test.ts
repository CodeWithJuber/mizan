import { authFetch } from "./authFetch.ts";
import { BACK_EVENT, RESTARTING_EVENT, healthUrl, isRestarting, waitUntilBack } from "./restarting.ts";
declare const process: { exit(code: number): void };

let checks = 0;
function check(name: string, ok: boolean) {
  if (!ok) throw new Error(name);
  checks++;
}
const events: string[] = [];
Object.defineProperty(globalThis, "window", {
  value: { dispatchEvent: (event: Event) => { events.push(event.type); return true; } },
  configurable: true,
});
Object.defineProperty(globalThis, "localStorage", {
  value: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  configurable: true,
});
const proxyPage = (status: number) => new Response("<html>Bad Gateway</html>", { status, headers: { "content-type": "text/html" } });
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

check("the proxy's 502 page is a restart", isRestarting(proxyPage(502)) && isRestarting(proxyPage(503)));
check("MIZAN's own 503 (JSON) is not", !isRestarting(json(503, { detail: "Voice is off" })));
check("a 504 (slow answer) is not", !isRestarting(proxyPage(504)));
check("health sits next to the API", healthUrl("https://m.example/api/chat/x?y=1") === "https://m.example/api/health" &&
  healthUrl("/api/agents") === "/api/health" && healthUrl("/elsewhere") === null);

// A read during a restart waits for one shared probe, then is sent once more.
let up = false;
const calls: string[] = [];
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input);
  calls.push(`${init?.method ?? "GET"} ${url}`);
  if (url.endsWith("/api/health")) return up ? json(200, { status: "ok" }) : proxyPage(502);
  return up ? json(200, { ok: true }) : proxyPage(502);
}) as typeof fetch;
const instant = { sleep: async () => { up = true; } };
const first = waitUntilBack("/api/health", null, instant);
const second = waitUntilBack("/api/health", null, instant);
check("waiting requests share one probe", first === second);
check("the probe ends when MIZAN is back", (await first) === true && events.join(",") === `${RESTARTING_EVENT},${BACK_EVENT}`);

up = false;
calls.length = 0;
setTimeout(() => { up = true; }, 1100);
const read = await authFetch("/api/agents");
check("a read is resent once MIZAN is back", read.status === 200 && calls.filter((c) => c === "GET /api/agents").length === 2);

up = false;
calls.length = 0;
const write = await authFetch("/api/chat/stream", { method: "POST", body: "{}" });
check("a write is never resent", write.status === 502 && calls.length === 1);

const controller = new AbortController();
const stopped = waitUntilBack("/api/health", controller.signal, { sleep: () => new Promise(() => {}) });
controller.abort();
check("a caller that gives up stops waiting", (await stopped) === false);

console.log(`${checks} restart checks passed`);
process.exit(0);
