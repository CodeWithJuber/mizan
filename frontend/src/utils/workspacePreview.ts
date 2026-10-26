/** Decide how a project previews in the browser and build the files for it. */

export type SandpackTemplate =
  | "static" | "vanilla" | "vanilla-ts" | "react" | "react-ts"
  | "vite-react" | "vite-react-ts" | "vite-vue" | "vite-svelte" | "vite";

export type ProjectPreview =
  | { kind: "web"; template: SandpackTemplate; files: Record<string, string>; activeFile: string; dependencies: Record<string, string> }
  | { kind: "python"; entry: string; files: Record<string, string> }
  | { kind: "none"; reason: string };

const SKIPPED_DIRS = ["node_modules/", "dist/", "build/", ".next/", ".git/", "__pycache__/", ".venv/"];
const SKIPPED_FILES = new Set(["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"]);
export const MAX_PREVIEW_FILES = 300;
export const MAX_PREVIEW_BYTES = 3 * 1024 * 1024;

export function previewable(path: string): boolean {
  const name = path.split("/").pop() ?? path;
  return !SKIPPED_DIRS.some((dir) => path.startsWith(dir) || path.includes(`/${dir}`)) && !SKIPPED_FILES.has(name);
}

function packageJson(files: Record<string, string>): Record<string, Record<string, string>> | null {
  try {
    return files["package.json"] ? JSON.parse(files["package.json"]) : null;
  } catch {
    return null;
  }
}

/** Choose a runtime from project markers; ``files`` maps relative paths to text. */
export function projectPreview(files: Record<string, string>, focus = ""): ProjectPreview {
  const paths = Object.keys(files).filter(previewable);
  if (!paths.length) return { kind: "none", reason: "The project has no files yet." };
  const pkg = packageJson(files);
  const dependencies = { ...(pkg?.dependencies ?? {}) };
  const devDependencies = pkg?.devDependencies ?? {};
  const has = (name: string) => name in dependencies || name in devDependencies;
  const typescript = paths.some((p) => /\.tsx?$/.test(p));
  let template: SandpackTemplate | null = null;
  if (has("vite")) {
    template = has("react") ? (typescript ? "vite-react-ts" : "vite-react")
      : has("vue") ? "vite-vue" : has("svelte") ? "vite-svelte" : "vite";
  } else if (has("react")) {
    template = typescript ? "react-ts" : "react";
  } else if (paths.includes("index.html") || paths.some((p) => p.endsWith(".html"))) {
    template = "static";
  } else if (paths.some((p) => /\.(jsx|tsx)$/.test(p))) {
    template = typescript ? "react-ts" : "react";
  }
  const python = paths.filter((p) => p.endsWith(".py"));
  const focusIsPython = focus.endsWith(".py");
  if ((!template || focusIsPython) && python.length) {
    const entry = focusIsPython ? focus
      : ["main.py", "app.py", "src/main.py"].find((p) => python.includes(p)) ?? python[0];
    return { kind: "python", entry, files: Object.fromEntries(python.map((p) => [p, files[p]])) };
  }
  if (!template) {
    return { kind: "none", reason: "Add an index.html, a React/Vite package.json or a .py file to preview." };
  }
  const sandpackFiles: Record<string, string> = {};
  let bytes = 0;
  for (const path of paths.slice(0, MAX_PREVIEW_FILES)) {
    bytes += files[path].length;
    if (bytes > MAX_PREVIEW_BYTES) break;
    sandpackFiles[`/${path}`] = files[path];
  }
  const candidates = [focus, "index.html", "src/App.tsx", "src/App.jsx", "App.tsx", "App.js", "src/main.tsx"];
  const activeFile = `/${candidates.find((p) => p && `/${p}` in sandpackFiles) ?? paths[0]}`;
  return { kind: "web", template, files: sandpackFiles, activeFile, dependencies };
}
