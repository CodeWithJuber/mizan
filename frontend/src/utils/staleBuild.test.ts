import { entryPath, servedBuildChanged, shouldReload } from "./staleBuild.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const memory = new Map<string, string>();
const store = { getItem: (k: string) => memory.get(k) ?? null, setItem: (k: string, v: string) => void memory.set(k, v) };

check("first stale chunk reloads", shouldReload(1_000_000, store));
check("a second failure within a minute shows the error", !shouldReload(1_030_000, store));
check("after a minute it may reload again", shouldReload(1_070_000, store));
check("no storage still reloads", shouldReload(5, null));
const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
check("blocked storage still reloads", shouldReload(5, broken));

const page = (entry: string) =>
  `<!doctype html><html><head><script type="module" crossorigin src="${entry}"></script></head><body></body></html>`;
check("the entry script is read from index.html", entryPath(page("/assets/index-AAA.js"), "https://m.example/chat") === "/assets/index-AAA.js");
check("no module script, no entry", entryPath("<html></html>", "https://m.example/") === null);
const served = (html: string, ok = true) => async () => new Response(html, { status: ok ? 200 : 502 });
check("a new build on the server is a stale tab", await servedBuildChanged("/assets/index-AAA.js", served(page("/assets/index-BBB.js")), "https://m.example/"));
check("the same build is not", !(await servedBuildChanged("/assets/index-AAA.js", served(page("/assets/index-AAA.js")), "https://m.example/")));
check("a restarting server is not evidence", !(await servedBuildChanged("/assets/index-AAA.js", served("Bad Gateway", false), "https://m.example/")));
check("a network error is not evidence", !(await servedBuildChanged("/assets/index-AAA.js", async () => { throw new TypeError("offline"); }, "https://m.example/")));

console.log(`staleBuild: ${checks} checks passed`);
