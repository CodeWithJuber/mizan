import { useMemo } from "react";
import {
  SandpackProvider,
  SandpackLayout,
  SandpackCodeEditor,
  SandpackPreview,
} from "@codesandbox/sandpack-react";
import type { ArtifactKind } from "../types";
import type { ArtifactPreviewProps } from "./ArtifactPreview";
const LANG_FILE: Record<string, string> = {
  python: "/main.py",
  py: "/main.py",
  javascript: "/index.js",
  js: "/index.js",
  jsx: "/App.js",
  typescript: "/index.ts",
  ts: "/index.ts",
  tsx: "/App.tsx",
  css: "/styles.css",
  html: "/index.html",
  json: "/data.json",
};

const RUNNABLE = new Set([
  "html",
  "javascript",
  "js",
  "jsx",
  "typescript",
  "ts",
  "tsx",
]);

function sandpackTemplate(
  kind: ArtifactKind,
  language?: string,
): "react" | "react-ts" | "static" {
  if (kind === "html") return "static";
  const lang = (language ?? "").toLowerCase();
  if (lang === "ts" || lang === "tsx" || lang === "typescript")
    return "react-ts";
  if (lang === "jsx" || lang === "js" || lang === "javascript") return "react";
  return "static";
}

export default function CodeArtifact({
  language,
  content,
  view,
  title,
}: Omit<ArtifactPreviewProps, "kind">) {
  const lang = (language ?? "").toLowerCase();
  const file = LANG_FILE[lang] ?? "/snippet.txt";
  const template = sandpackTemplate("code", language);
  const files = useMemo(() => {
    const f: Record<string, string> = {};
    if (template === "static" && file === "/index.html")
      f["/index.html"] = content;
    else if (template === "react") f["/App.js"] = content;
    else if (template === "react-ts") f["/App.tsx"] = content;
    else f[file] = content;
    return f;
  }, [template, file, content]);
  const runnable =
    RUNNABLE.has(lang) || template !== "static" || file === "/index.html";
  const isDark =
    typeof document !== "undefined" &&
    document.documentElement.classList.contains("dark");

  return (
    <div className="rounded-b-xl overflow-hidden border-t border-gray-200 dark:border-zinc-700">
      <SandpackProvider
        template={template}
        files={files}
        theme={isDark ? "dark" : "light"}
        options={{ autorun: true, recompileMode: "delayed" }}
      >
        <SandpackLayout>
          {view === "preview" && runnable ? (
            <SandpackPreview showOpenInCodeSandbox={false} title={title} />
          ) : (
            <>
              <SandpackCodeEditor
                readOnly
                showLineNumbers
                showInlineErrors
                closableTabs={false}
              />
              {view === "preview" && !runnable && (
                <div className="px-3 py-2 text-[11px] text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-zinc-800/50">
                  Live preview is only available for JavaScript/TypeScript/HTML
                  {lang ? ` — "${lang}"` : ""} shows as read-only code.
                </div>
              )}
            </>
          )}
        </SandpackLayout>
      </SandpackProvider>
    </div>
  );
}
