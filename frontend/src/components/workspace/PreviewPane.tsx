/** Live preview of the whole project: Sandpack for web apps, Pyodide for Python. */
import { lazy, Suspense } from "react";
import {
  SandpackLayout, SandpackPreview, SandpackProvider, useSandpack,
} from "@codesandbox/sandpack-react";
import { Wrench } from "lucide-react";
import type { ProjectPreview } from "../../utils/workspacePreview";
import { useTheme } from "../../hooks/useTheme";

const PythonRunner = lazy(() => import("./PythonRunner"));

/** "Fix with MIZAN" over the preview while Sandpack shows a build or runtime error. */
function FixError({ onError }: { onError: (message: string) => void }) {
  const { sandpack } = useSandpack();
  const message = sandpack.error?.message;
  if (!message) return null;
  return (
    <button
      type="button"
      className="btn-primary btn-sm absolute right-3 bottom-3 z-10 inline-flex items-center gap-1 shadow"
      onClick={() => onError(message.slice(0, 4000))}
    >
      <Wrench className="w-3.5 h-3.5" /> Fix with MIZAN
    </button>
  );
}

export default function PreviewPane({ preview, revision, onError }: {
  preview: ProjectPreview | null;
  revision: number;
  /** "Fix with MIZAN": the error the preview shows goes to the chat. */
  onError?: (message: string) => void;
}) {
  const { isDark: dark } = useTheme();
  if (!preview) return <div className="p-4 text-sm text-gray-500">Loading preview…</div>;
  if (preview.kind === "none") return <div className="p-4 text-sm text-gray-500">{preview.reason}</div>;
  if (preview.kind === "python") {
    return (
      <Suspense fallback={<div className="p-4 text-sm text-gray-500">Loading Python…</div>}>
        <PythonRunner key={revision} files={preview.files} entry={preview.entry} onError={onError} />
      </Suspense>
    );
  }
  return (
    <div className="relative h-full [&_.sp-wrapper]:h-full [&_.sp-layout]:h-full [&_.sp-stack]:h-full">
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
        {onError && <FixError onError={onError} />}
      </SandpackProvider>
    </div>
  );
}
