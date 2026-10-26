/** Live preview of the whole project: Sandpack for web apps, Pyodide for Python. */
import { lazy, Suspense } from "react";
import {
  SandpackLayout, SandpackPreview, SandpackProvider,
} from "@codesandbox/sandpack-react";
import type { ProjectPreview } from "../../utils/workspacePreview";

const PythonRunner = lazy(() => import("./PythonRunner"));

export default function PreviewPane({ preview, revision }: { preview: ProjectPreview | null; revision: number }) {
  if (!preview) return <div className="p-4 text-sm text-gray-500">Loading preview…</div>;
  if (preview.kind === "none") return <div className="p-4 text-sm text-gray-500">{preview.reason}</div>;
  if (preview.kind === "python") {
    return (
      <Suspense fallback={<div className="p-4 text-sm text-gray-500">Loading Python…</div>}>
        <PythonRunner key={revision} files={preview.files} entry={preview.entry} />
      </Suspense>
    );
  }
  const dark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");
  return (
    <div className="h-full [&_.sp-wrapper]:h-full [&_.sp-layout]:h-full [&_.sp-stack]:h-full">
      <SandpackProvider
        key={revision}
        template={preview.template}
        files={preview.files}
        theme={dark ? "dark" : "light"}
        customSetup={Object.keys(preview.dependencies).length ? { dependencies: preview.dependencies } : undefined}
        options={{ activeFile: preview.activeFile, recompileMode: "delayed", autorun: true }}
      >
        <SandpackLayout style={{ height: "100%", border: 0, borderRadius: 0 }}>
          <SandpackPreview style={{ height: "100%" }} showOpenInCodeSandbox={false} showRefreshButton />
        </SandpackLayout>
      </SandpackProvider>
    </div>
  );
}
