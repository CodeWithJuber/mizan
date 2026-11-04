/**
 * A Preview button under runnable code in an answer (```html, svg, jsx, tsx,
 * js, ts, python). The block opens as an artifact without any tool call, so it
 * works however MIZAN produced the answer; "Save to chat" keeps it as a
 * versioned artifact of this chat.
 */
import { isValidElement, lazy, Suspense, useState, type ComponentProps, type ReactNode } from "react";
import { defaultComponents, useIsCodeFenceIncomplete } from "streamdown";
import { Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { addToast } from "../../components/Toast";
import { config } from "../../config";
import { authFetch } from "../../utils/authFetch";
import { useChatActions, useChatState } from "./ChatProvider";
import type { Artifact, ArtifactKind } from "../../types";

const ArtifactPreview = lazy(() =>
  import("../../components/ArtifactPreview").then((module) => ({ default: module.ArtifactPreview })),
);

interface Target { kind: ArtifactKind; language?: string; label: string }

const PREVIEWABLE: Record<string, Target> = {
  html: { kind: "html", label: "Web page" },
  htm: { kind: "html", label: "Web page" },
  svg: { kind: "code", language: "svg", label: "Picture" },
  jsx: { kind: "code", language: "jsx", label: "React component" },
  tsx: { kind: "code", language: "tsx", label: "React component" },
  js: { kind: "code", language: "javascript", label: "Script" },
  javascript: { kind: "code", language: "javascript", label: "Script" },
  ts: { kind: "code", language: "typescript", label: "Script" },
  typescript: { kind: "code", language: "typescript", label: "Script" },
  python: { kind: "code", language: "python", label: "Python program" },
  py: { kind: "code", language: "python", label: "Python program" },
};

type CodeProps = ComponentProps<"code"> & { node?: unknown };
const StreamdownCode = defaultComponents.code as (props: CodeProps) => ReactNode;

/** The text of a code element, as Streamdown reads it. */
function codeText(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(codeText).join("");
  if (isValidElement<{ children?: ReactNode }>(children)) return codeText(children.props.children);
  return "";
}

/** A page's own <title>, else what the block is. */
function titleOf(code: string, target: Target): string {
  const named = /<title>([^<]{1,120})<\/title>/i.exec(code)?.[1]?.trim();
  return named || target.label;
}

export function PreviewableCode(props: CodeProps) {
  const incomplete = useIsCodeFenceIncomplete();
  const language = /language-([^\s]+)/.exec(props.className ?? "")?.[1]?.toLowerCase() ?? "";
  const target = PREVIEWABLE[language];
  // Inline code has no data-block; a block still streaming is not finished code.
  if (!("data-block" in props) || !target || incomplete) return <StreamdownCode {...props} />;
  return (
    <>
      <StreamdownCode {...props} />
      <CodePreview code={codeText(props.children)} target={target} />
    </>
  );
}

function CodePreview({ code, target }: { code: string; target: Target }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const { sessionId } = useChatState();
  const { addArtifact } = useChatActions();
  const title = titleOf(code, target);

  async function save() {
    setSaving(true);
    try {
      const response = await authFetch(`${config.API_URL}/artifacts/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId, title, kind: target.kind, language: target.language, content: code,
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body?.detail === "string" ? body.detail : `the server answered ${response.status}`);
      }
      const saved = (await response.json()) as Artifact;
      addArtifact({
        ...saved,
        versions: [{ version: saved.current_version ?? 1, content: code, created_at: saved.created_at ?? new Date().toISOString() }],
      });
      setOpen(false);
      addToast({ type: "success", title: "Saved to this chat", description: `${title} is in Artifacts.` });
    } catch (error) {
      addToast({
        type: "error",
        title: "Could not save the artifact",
        description: `${error instanceof Error ? error.message : String(error)}. Try again.`,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="-mt-2 mb-3 flex justify-end">
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Eye aria-hidden="true" />
        Preview
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-4xl max-h-[90dvh] overflow-auto">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              Runs in a sandbox: it can load from the web, but it cannot reach your MIZAN account.
            </DialogDescription>
          </DialogHeader>
          {open && (
            <Suspense fallback={<p className="p-4 text-sm text-muted-foreground">Loading preview…</p>}>
              <ArtifactPreview kind={target.kind} language={target.language} content={code} view="preview" title={title} />
            </Suspense>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
            <Button onClick={save} disabled={saving || !sessionId}>
              {saving ? "Saving…" : "Save to chat"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
