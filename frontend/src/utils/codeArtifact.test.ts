/** Render the actual Sandpack provider state; no browser/network is required. */
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { SandpackProvider, useSandpack } from "@codesandbox/sandpack-react";
import { codeArtifactConfig } from "./codeArtifact.ts";

let passed = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(`FAIL: ${name}`);
  passed += 1;
}

function renderConfig(language: string, content: string, view: "preview" | "code" = "preview") {
  const config = codeArtifactConfig(language, content, view);
  let captured: { activeFile: string; visibleFiles: string[]; files: Record<string, { code: string }> } | undefined;
  function Inspect() {
    const { sandpack } = useSandpack();
    captured = {
      activeFile: sandpack.activeFile,
      visibleFiles: sandpack.visibleFiles,
      files: sandpack.files,
    };
    return null;
  }
  renderToString(createElement(SandpackProvider, config, createElement(Inspect)));
  if (!captured) throw new Error("Sandpack did not render");
  return { config, state: captured };
}

for (const [language, code, file] of [
  ["python", "print('actual artifact')", "/main.py"],
  ["json", '{"answer":42}', "/data.json"],
  ["bash", "echo actual-artifact", "/main.sh"],
]) {
  const { config, state } = renderConfig(language, code);
  check(`${language}: displays artifact, not static template HTML`, state.activeFile === file);
  check(`${language}: actual source is visible`, state.files[state.activeFile].code === code);
  check(`${language}: no template tab`, state.visibleFiles.length === 1 && state.visibleFiles[0] === file);
  check(`${language}: no browser execution claim`, !config.runnable && !config.options.autorun);
}

const script = 'document.getElementById("app").textContent = "actual output";';
const js = renderConfig("javascript", script);
check("plain JS uses its own entry", js.state.activeFile === "/index.js");
check("plain JS does not require a React component", !js.state.files["/App.js"]);
check("plain JS entry is included in HTML", js.state.files["/index.html"].code.includes("index.js"));
const node = { textContent: "" };
new Function("document", js.state.files["/index.js"].code)({ getElementById: () => node });
check("plain JS executes its DOM update", node.textContent === "actual output");
check("plain JS preview runs", js.config.options.autorun);

const ts = renderConfig("typescript", 'const n: number = 42; document.body.textContent = String(n);');
check("plain TS uses its own entry", ts.state.activeFile === "/index.ts");
check("plain TS does not require a React component", !ts.state.files["/App.tsx"]);
check("plain TS has TypeScript build dependency", ts.state.files["/package.json"].code.includes("typescript"));
for (const [language, file] of [["jsx", "/App.js"], ["tsx", "/App.tsx"]]) {
  const jsx = renderConfig(language, 'export default function App() { return <h1>Actual artifact</h1>; }');
  check(`${language}: React component keeps its proper entry`, jsx.state.activeFile === file);
}
check("code-only view does not start executable preview", !renderConfig("javascript", script, "code").config.options.autorun);
console.log(`codeArtifact: ${passed} checks passed`);
