/**
 * One changed file, hunk by hunk: the editor holds the file as it is now, each change
 * against the checkpoint has Accept / Reject, and Save writes what is kept. Loaded only
 * on the Changes tab (CodeMirror's merge view is not in the main bundle).
 */
import { useEffect, useMemo, useState } from "react";
import CodeMirror, { EditorView } from "@uiw/react-codemirror";
import { unifiedMergeView } from "@codemirror/merge";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { oneDark } from "@codemirror/theme-one-dark";
import { Save, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "../../hooks/useTheme";
import { languageOf } from "../../utils/workspaceTree";
import { addToast } from "../../components/Toast";
import { jsonBody, workspaceApi, WorkspaceError } from "./projects";

/** Accept / Reject on their own row above each change (never over the code), in the
 * app's colours, and usable from the keyboard as well as the mouse. */
const chunkTheme = EditorView.theme({
  ".cm-deletedChunk .cm-chunkButtons": { position: "static", display: "flex", gap: "4px", padding: "2px 0" },
  ".cm-deletedChunk button": {
    background: "var(--card)", border: "1px solid var(--border)", borderRadius: "6px", margin: "0", padding: "0 8px",
    font: "500 12px/20px var(--font-sans, system-ui)",
  },
  ".cm-deletedChunk button:hover": { background: "var(--muted)" },
  ".cm-deletedChunk button[name=accept]": { background: "var(--card)", color: "var(--success)" },
  ".cm-deletedChunk button[name=reject]": { background: "var(--card)", color: "var(--destructive)" },
  ".cm-deletedChunk button[name=accept]:hover, .cm-deletedChunk button[name=reject]:hover": { background: "var(--muted)" },
});

function chunkButton(type: "accept" | "reject", action: (event: MouseEvent) => void): HTMLElement {
  const button = document.createElement("button");
  button.type = "button";
  button.name = type;
  button.textContent = type === "accept" ? "Accept" : "Reject";
  button.className = "focus-ring";
  button.onmousedown = action;
  // Enter or Space on a focused button (a click with no pointer, detail 0).
  button.onclick = (event) => {
    if (event.detail === 0) action(event);
  };
  return button;
}

function languageExtension(path: string) {
  switch (languageOf(path)) {
    case "javascript": return [javascript()];
    case "jsx": return [javascript({ jsx: true })];
    case "typescript": return [javascript({ typescript: true })];
    case "tsx": return [javascript({ jsx: true, typescript: true })];
    case "python": return [python()];
    case "html": return [html()];
    case "css": return [css()];
    case "json": return [json()];
    case "markdown": return [markdown()];
    default: return [];
  }
}

interface Props {
  projectId: string;
  checkpointId: string;
  path: string;
  /** A file the checkpoint did not have is compared with an empty one. */
  added: boolean;
  onSaved: () => void;
}

interface Loaded {
  original: string;
  current: string;
  sha: string;
}

export default function MergeEditor({ projectId, checkpointId, path, added, onSaved }: Props) {
  const { isDark } = useTheme();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [doc, setDoc] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const base = `/${encodeURIComponent(projectId)}`;
  const query = `path=${encodeURIComponent(path)}`;

  useEffect(() => {
    // A new file or checkpoint mounts a new editor (keyed by the list); a reload keeps
    // showing the old text until the new one arrives.
    let cancelled = false;
    Promise.all([
      added
        ? Promise.resolve({ content: "" })
        : workspaceApi<{ content: string }>(`${base}/checkpoints/${encodeURIComponent(checkpointId)}/file?${query}`),
      workspaceApi<{ content: string; sha256: string }>(`${base}/file?${query}`),
    ])
      .then(([before, now]) => {
        if (cancelled) return;
        setError("");
        setLoaded({ original: before.content, current: now.content, sha: now.sha256 });
        setDoc(now.content);
      })
      .catch((problem: Error) => !cancelled && setError(problem.message));
    return () => { cancelled = true; };
  }, [base, checkpointId, query, added, reload]);

  const extensions = useMemo(
    () => loaded
      ? [
          ...languageExtension(path),
          EditorView.contentAttributes.of({ "aria-label": `Changes in ${path}` }),
          chunkTheme,
          unifiedMergeView({ original: loaded.original, mergeControls: chunkButton, gutter: true, collapseUnchanged: {} }),
        ]
      : [],
    [loaded, path],
  );

  if (error) return <p role="alert" className="p-3 text-sm text-destructive">{error}</p>;
  if (!loaded) return <p className="p-3 text-sm text-muted-foreground">Loading {path}…</p>;

  const changed = doc !== loaded.current;
  const save = async () => {
    setSaving(true);
    try {
      await workspaceApi(`${base}/file`, jsonBody("PUT", { path, content: doc, expected_sha256: loaded.sha }));
      addToast({ type: "success", title: `${path} saved` });
      setReload((value) => value + 1); // what is saved is the new "now"
      onSaved();
    } catch (problem) {
      if (problem instanceof WorkspaceError && problem.status === 409) {
        addToast({ type: "warning", title: `${path} changed meanwhile`, description: "It was reloaded; review it again." });
        setReload((value) => value + 1);
      } else {
        addToast({ type: "error", title: `Could not save ${path}`, description: (problem as Error).message });
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-3 py-1.5">
        <span className="mr-auto text-xs text-muted-foreground">
          Accept or reject each change, then save. {changed ? "Unsaved." : ""}
        </span>
        <Button size="sm" variant="ghost" disabled={doc === loaded.original} onClick={() => setDoc(loaded.original)}>
          <Undo2 /> Reject all
        </Button>
        <Button size="sm" disabled={!changed || saving} onClick={() => void save()}>
          <Save /> {saving ? "Saving…" : "Save"}
        </Button>
      </div>
      <CodeMirror
        key={`${path}:${reload}`}
        value={doc}
        theme={isDark ? oneDark : "light"}
        extensions={extensions}
        onChange={setDoc}
        basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: false }}
        className="max-h-[60vh] overflow-auto text-sm"
      />
    </div>
  );
}
