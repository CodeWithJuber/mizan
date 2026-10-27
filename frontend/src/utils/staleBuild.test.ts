import { shouldReload } from "./staleBuild.ts";

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

console.log(`staleBuild: ${checks} checks passed`);
