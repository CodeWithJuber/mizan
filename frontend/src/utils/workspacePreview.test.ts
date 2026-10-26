import { projectPreview, previewable } from "./workspacePreview.ts";
import { ancestors, buildTree, languageOf } from "./workspaceTree.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const tree = buildTree([
  { path: "src/app.py", kind: "file", size: 10 },
  { path: "README.md", kind: "file", size: 5 },
  { path: "src/util", kind: "directory", size: 0 },
  { path: "src/util/x.py", kind: "file", size: 3 },
  { path: "assets", kind: "directory", size: 0 },
]);
check("folders sort before files", tree.map((n) => n.name).join(",") === "assets,src,README.md");
check("nested children are built", tree[1].children.map((n) => n.name).join(",") === "util,app.py");
check("ancestors open the path", ancestors("a/b/c.ts").join("|") === "a|a/b");
check("languages by extension", languageOf("x.tsx") === "tsx" && languageOf("Makefile") === "text");

const html = projectPreview({ "index.html": "<h1>Hi</h1>", "style.css": "h1{}" });
check("plain html is static", html.kind === "web" && html.template === "static" && html.activeFile === "/index.html");

const vite = projectPreview({
  "package.json": JSON.stringify({ dependencies: { react: "19.3.1", "react-dom": "19.3.1" }, devDependencies: { vite: "8.3.5" } }),
  "src/App.tsx": "export default () => null",
  "src/main.tsx": "",
  "index.html": "",
  "node_modules/x/index.js": "ignored",
  "package-lock.json": "{}",
});
check("vite react ts detected", vite.kind === "web" && vite.template === "vite-react-ts");
check("heavy folders are skipped", vite.kind === "web" && !("/node_modules/x/index.js" in vite.files) && !("/package-lock.json" in vite.files));
check("dependencies carried", vite.kind === "web" && vite.dependencies.react === "19.3.1");

const py = projectPreview({ "main.py": "print(1)", "lib.py": "" });
check("python runs main.py", py.kind === "python" && py.entry === "main.py");
const focused = projectPreview({ "index.html": "", "tool.py": "print(2)" }, "tool.py");
check("focused python file wins", focused.kind === "python" && focused.entry === "tool.py");
check("empty project explains", projectPreview({}).kind === "none");
check("previewable skips caches", !previewable("a/__pycache__/x.pyc") && previewable("src/a.ts"));

console.log(`${checks} workspace tree/preview checks passed`);
