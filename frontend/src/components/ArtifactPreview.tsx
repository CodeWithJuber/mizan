/**
 * ArtifactPreview.tsx — renders one artifact version.
 *
 * JEV-LOCKED hybrid rendering:
 *  - kind "code"     → Sandpack (live runnable preview for JS/HTML, read-only
 *                      editor otherwise). Editor is readOnly: artifacts are
 *                      immutable, iteration happens via versions.
 *  - kind "html"/"markdown" → locked-down <iframe>. See the sandbox comment
 *                      on the iframe below for the anti-exfiltration rationale.
 */
import { useMemo } from "react";
import {
  SandpackProvider,
  SandpackLayout,
  SandpackCodeEditor,
  SandpackPreview,
} from "@codesandbox/sandpack-react";
import { buildSandboxDoc } from "../utils/safeHtml.ts";
import type { ArtifactKind } from "../types.ts";

export interface ArtifactPreviewProps {
  kind: ArtifactKind;
  language?: string;
  content: string;
  view: "preview" | "code";
  title: string;
}

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

function CodeArtifact({
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

export function ArtifactPreview({
  kind,
  language,
  content,
  view,
  title,
}: ArtifactPreviewProps) {
  const doc = useMemo(
    () => (kind === "code" ? "" : buildSandboxDoc(kind, content)),
    [kind, content],
  );

  if (kind === "code") {
    return (
      <CodeArtifact
        language={language}
        content={content}
        view={view}
        title={title}
      />
    );
  }

  if (view === "code") {
    return (
      <pre className="rounded-b-xl border-t border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-900/60 p-3 text-xs font-mono whitespace-pre-wrap break-words max-h-[420px] overflow-auto text-gray-800 dark:text-gray-200">
        {content}
      </pre>
    );
  }

  return (
    // SECURITY — anti-exfiltration, two independent layers:
    //  1. sandbox="allow-scripts" WITHOUT allow-same-origin: the document gets
    //     an opaque origin, so artifact scripts cannot reach the parent DOM,
    //     cookies, localStorage, or the Mizan JWT — even top-navigation is
    //     contained. allow-scripts stays so legitimate artifact interactivity
    //     (animations, calculators, tabs) keeps working.
    //  2. buildSandboxDoc injects Content-Security-Policy with
    //     connect-src 'none': fetch/XHR/WebSocket/EventSource/sendBeacon are
    //     all blocked, so even a malicious script inside the sandbox cannot
    //     phone data home. Markdown additionally goes through
    //     markdownToSafeHtml (all raw HTML escaped) before injection.
    <iframe
      title={title}
      sandbox="allow-scripts"
      srcDoc={doc}
      className="w-full min-h-[380px] rounded-b-xl border-t border-gray-200 dark:border-zinc-700 bg-white"
    />
  );
}
