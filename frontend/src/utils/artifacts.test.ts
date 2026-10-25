import type { Artifact } from "../types.ts";
import { artifactDownloadName, artifactVersion, mergeSessionArtifacts } from "./artifacts.ts";

let passed = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(`FAIL: ${name}`);
  passed += 1;
}
const old: Artifact = { id: "old", session_id: "chat-a", title: "Old graph", kind: "image", versions: [] };
const current: Artifact = { id: "current", session_id: "chat-b", title: "Graph", kind: "image", versions: [] };
const visible = mergeSessionArtifacts("chat-b", [old, current], [old]);
check("late publish from old chat never appears in current chat", visible.length === 1 && visible[0].id === "current");
check("empty new chat does not inherit previous artifacts", mergeSessionArtifacts("new-chat", [old], [old]).length === 0);

const saved = { ...current, version: 3 };
const seeded = { ...current, versions: [{ version: 1, content: "stale", created_at: "" }] };
const merged = mergeSessionArtifacts("chat-b", [saved], [seeded]);
check("server HTTP version survives older streamed seed", artifactVersion(merged[0]) === 3);
check("merge deduplicates persisted and live artifact", merged.length === 1);
check("image JPEG download preserves actual format", artifactDownloadName(current, "data:image/jpeg;base64,AAAA") === "Graph.jpg");
check("image WebP download preserves actual format", artifactDownloadName(current, "data:image/webp;base64,AAAA") === "Graph.webp");
for (const [language, extension] of [["javascript", "js"], ["typescript", "ts"], ["python", "py"], ["bash", "sh"]]) {
  check(`${language}: file uses runnable extension`, artifactDownloadName({ ...current, kind: "code", language }, "code") === `Graph.${extension}`);
}
check("existing filename preserved", artifactDownloadName({ ...current, title: "graph.png" }, "data:image/png;base64,AAAA") === "graph.png");
console.log(`artifacts: ${passed} checks passed`);
