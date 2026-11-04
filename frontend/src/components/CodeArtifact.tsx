import { lazy, Suspense, useMemo } from "react";
import {
  SandpackProvider,
  SandpackLayout,
  SandpackCodeEditor,
  SandpackPreview,
} from "@codesandbox/sandpack-react";
import type { ArtifactPreviewProps } from "./ArtifactPreview";
import { codeArtifactConfig } from "../utils/codeArtifact.ts";
import { useTheme } from "../hooks/useTheme";

const PythonRunner = lazy(() => import("./workspace/PythonRunner"));

export default function CodeArtifact({
  language,
  content,
  view,
  title,
}: Omit<ArtifactPreviewProps, "kind">) {
  const lang = (language ?? "").toLowerCase();
  const { template, runnable, files, options, customSetup } = useMemo(
    () => codeArtifactConfig(language, content, view),
    [language, content, view],
  );
  const { isDark } = useTheme();

  // Python runs in the browser with Pyodide, as a project's Python preview does.
  if (view === "preview" && (lang === "python" || lang === "py")) {
    return (
      <div className="rounded-b-xl overflow-hidden border-t border-border">
        <Suspense fallback={<p className="p-4 text-sm text-muted-foreground">Loading Python…</p>}>
          <PythonRunner files={{ "main.py": content }} entry="main.py" />
        </Suspense>
      </div>
    );
  }

  return (
    <div className="rounded-b-xl overflow-hidden border-t border-border">
      <SandpackProvider
        template={template}
        files={files}
        customSetup={customSetup}
        theme={isDark ? "dark" : "light"}
        options={options}
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
                <div className="px-3 py-2 text-[11px] text-muted-foreground bg-muted/50">
                  Live preview runs HTML, SVG, JavaScript, TypeScript, React and Python
                  {lang ? ` — "${lang}" is shown as code.` : "."}
                </div>
              )}
            </>
          )}
        </SandpackLayout>
      </SandpackProvider>
    </div>
  );
}
