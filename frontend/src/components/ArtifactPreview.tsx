/**
 * ArtifactPreview.tsx — renders one artifact version.
 *
 *  - kind "code"     → Sandpack (live preview for JS/TS/React, Pyodide for
 *                      Python, read-only editor otherwise); language "svg" is
 *                      drawn as a picture in the sandboxed frame below.
 *                      Artifacts are immutable, iteration happens via versions.
 *  - kind "markdown" → the chat's own Markdown (GFM tables, images, lists).
 *  - kind "html"     → sandboxed <iframe>; see the SECURITY comment below.
 */
import { useMemo, lazy, Suspense } from "react";
import { Markdown } from "./Markdown";
const CodeArtifact = lazy(() => import("./CodeArtifact"));
import { buildSandboxDoc } from "../utils/safeHtml.ts";
import type { ArtifactKind } from "../types.ts";

export interface ArtifactPreviewProps {
  kind: ArtifactKind;
  language?: string;
  content: string;
  view: "preview" | "code";
  title: string;
}

function isSvg(kind: ArtifactKind, language: string | undefined, content: string): boolean {
  return kind === "code" && ((language ?? "").toLowerCase() === "svg" || /^\s*<svg[\s>]/i.test(content));
}

export function ArtifactPreview({
  kind,
  language,
  content,
  view,
  title,
}: ArtifactPreviewProps) {
  const svg = isSvg(kind, language, content);
  const doc = useMemo(
    () => (svg ? buildSandboxDoc("svg", content) : kind === "html" ? buildSandboxDoc("html", content) : ""),
    [svg, kind, content],
  );

  if (kind === "image") {
    const safe = /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(
      content,
    );
    return safe ? (
      <img
        src={content}
        alt={title}
        className="w-full max-h-[560px] object-contain bg-muted rounded-lg"
      />
    ) : (
      <p role="alert" className="p-4 text-sm text-destructive">
        This image format cannot be displayed.
      </p>
    );
  }
  if (kind === "code" && !(svg && view === "preview")) {
    return (
      <Suspense
        fallback={
          <p className="p-4 text-sm text-muted-foreground">Loading code preview…</p>
        }
      >
        <CodeArtifact
          language={language}
          content={content}
          view={view}
          title={title}
        />
      </Suspense>
    );
  }

  if (view === "code") {
    return (
      <pre className="rounded-b-xl border-t border-border bg-muted p-3 text-xs font-mono whitespace-pre-wrap wrap-break-word max-h-[420px] overflow-auto text-foreground/90">
        {content}
      </pre>
    );
  }

  if (kind === "markdown") {
    return (
      <div className="rounded-b-xl border-t border-border p-4 max-h-[560px] overflow-auto">
        <Markdown content={content} />
      </div>
    );
  }

  return (
    // SECURITY: no allow-same-origin, so the document has an opaque origin and
    // its scripts cannot reach the parent DOM, cookies, localStorage or the
    // MIZAN session. Links (popups, which stay sandboxed), dialogs and forms
    // work; buildSandboxDoc's policy decides what the page may load.
    <iframe
      title={title}
      sandbox="allow-scripts allow-popups allow-modals allow-forms"
      srcDoc={doc}
      className="w-full min-h-[380px] rounded-b-xl border-t border-border bg-white"
    />
  );
}
