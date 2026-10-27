/** Dev-server commands that work behind the sandbox preview path. */

export interface ServerSuggestion {
  label: string;
  command: string;
  port: number;
  /** base: the server is told its path prefix; root: the prefix is stripped. */
  mode: "base" | "root";
}

const STATIC: ServerSuggestion = {
  label: "Static files",
  command: "python3 -m http.server $PORT --bind 127.0.0.1",
  port: 8000,
  mode: "root",
};

export function suggestServers(packageJson?: string): ServerSuggestion[] {
  let pkg: { scripts?: Record<string, string>; dependencies?: Record<string, string>; devDependencies?: Record<string, string> } = {};
  try {
    pkg = packageJson ? JSON.parse(packageJson) : {};
  } catch {
    pkg = {};
  }
  const has = (name: string) => Boolean(pkg.dependencies?.[name] || pkg.devDependencies?.[name]);
  const result: ServerSuggestion[] = [];
  if (has("vite")) {
    result.push({
      label: "Vite dev server",
      command: "npm install && npx vite --host 127.0.0.1 --port $PORT --strictPort --base $MIZAN_PREVIEW_PREFIX/$PORT/",
      port: 5173,
      mode: "base",
    });
  } else if (pkg.scripts?.dev) {
    result.push({
      label: "npm run dev",
      command: "npm install && npm run dev -- --host 127.0.0.1 --port $PORT",
      port: 3000,
      mode: "root",
    });
  }
  if (pkg.scripts?.start && !has("vite")) {
    result.push({ label: "npm start", command: "npm install && npm start", port: 3000, mode: "root" });
  }
  result.push(STATIC);
  return result;
}

/** Preview paths are served by the backend on Mizan's own origin. */
export function previewSrc(previewUrl: string): string {
  return previewUrl.startsWith("/api/workspaces/preview/") ? previewUrl : "";
}
