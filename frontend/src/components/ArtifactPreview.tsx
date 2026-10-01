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
import { useMemo, lazy, Suspense } from "react";
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

export function ArtifactPreview({
  kind,
  language,
  content,
  view,
  title,
}: ArtifactPreviewProps) {
  const doc = useMemo(
    () =>
      kind === "code" || kind === "image" ? "" : buildSandboxDoc(kind, content),
    [kind, content],
  );

  if (kind === "image") {
    const safe = /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(
      content,
    );
    return safe ? (
      <img
        src={content}
        alt={title}
        className="w-full max-h-[560px] object-contain bg-gray-50 dark:bg-zinc-950 rounded-lg"
      />
    ) : (
      <p role="alert" className="p-4 text-sm text-red-600">
        This image format cannot be displayed.
      </p>
    );
  }
  if (kind === "code") {
    return (
      <Suspense
        fallback={
          <p className="p-4 text-sm text-gray-500">Loading code preview…</p>
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
