import { previewSrc, suggestServers } from "./sandboxCommands.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const vite = suggestServers(JSON.stringify({ devDependencies: { vite: "8.3.5" }, scripts: { dev: "vite" } }));
check("vite first and told its base", vite[0].mode === "base" && vite[0].command.includes("--base $MIZAN_PREVIEW_PREFIX/$PORT/"));
check("vite listens on loopback", vite[0].command.includes("--host 127.0.0.1"));
check("static fallback always offered", vite[vite.length - 1].mode === "root" && vite[vite.length - 1].port === 8000);
const next = suggestServers(JSON.stringify({ scripts: { dev: "next dev", start: "next start" } }));
check("generic dev script strips the prefix", next[0].label === "npm run dev" && next[0].mode === "root");
check("start script offered", next.some((item) => item.label === "npm start"));
check("broken package.json is tolerated", suggestServers("{").length === 1);
check("only backend preview paths are framed", previewSrc("/api/workspaces/preview/abc/5173/") !== "" && previewSrc("https://evil.example/") === "");

console.log(`${checks} sandbox command checks passed`);
