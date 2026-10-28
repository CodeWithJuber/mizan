import { useMemo } from "react";
import {
  SandpackProvider,
  SandpackLayout,
  SandpackCodeEditor,
  SandpackPreview,
} from "@codesandbox/sandpack-react";
import type { ArtifactPreviewProps } from "./ArtifactPreview";
import { codeArtifactConfig } from "../utils/codeArtifact.ts";
import { useTheme } from "../hooks/useTheme";

export default function CodeArtifact({
  language,
  content,
  view,
  title,
}: Omit<ArtifactPreviewProps, "kind">) {
  const lang = (language ?? "").toLowerCase();
  const { template, runnable, files, options } = useMemo(
    () => codeArtifactConfig(language, content, view),
    [language, content, view],
  );
  const { isDark } = useTheme();

  return (
    <div className="rounded-b-xl overflow-hidden border-t border-gray-200 dark:border-zinc-700">
      <SandpackProvider
        template={template}
        files={files}
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
