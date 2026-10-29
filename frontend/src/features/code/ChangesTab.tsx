/**
 * What changed in the project since a checkpoint (by default the one saved before the
 * chat's latest message): each file can be reviewed hunk by hunk, or undone.
 */
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import { DiffView } from "../../components/AgentActivity";
import { addToast } from "../../components/Toast";
import { type Checkpoint, type FileChange, type Restored, restoreCheckpoint, workspaceApi, WorkspaceError } from "./projects";

const MergeEditor = lazy(() => import("./MergeEditor"));

interface Props {
  projectId: string;
  /** The checkpoint saved before the chat's latest message in this project. */
  turnCheckpoint?: string;
  revision: number;
  onChanged: () => void;
}

const LABELS: Record<string, string> = {
  manual: "Saved by you",
  agent: "Saved by MIZAN",
  turn: "Before a chat message",
  restore: "Before a restore",
};

export function ChangesTab({ projectId, turnCheckpoint, revision, onChanged }: Props) {
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [base, setBase] = useState("");
  const [files, setFiles] = useState<FileChange[] | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [review, setReview] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const root = `/${encodeURIComponent(projectId)}`;

  useEffect(() => {
    let cancelled = false;
    workspaceApi<{ checkpoints: Checkpoint[] }>(`${root}/checkpoints`)
      .then((data) => {
        if (cancelled) return;
        const list = data.checkpoints ?? [];
        setCheckpoints(list);
        setBase((current) => {
          if (current && list.some((item) => item.id === current)) return current;
          if (turnCheckpoint && list.some((item) => item.id === turnCheckpoint)) return turnCheckpoint;
          return (list.find((item) => item.kind === "turn") ?? list[0])?.id ?? "";
        });
      })
      .catch((problem: Error) => !cancelled && setError(problem.message));
    return () => { cancelled = true; };
  }, [root, revision, turnCheckpoint]);

  const loadDiff = useCallback(async () => {
    if (!base) {
      setFiles(null);
      return;
    }
    const data = await workspaceApi<{ files: FileChange[]; truncated: boolean }>(
      `${root}/diff?checkpoint_id=${encodeURIComponent(base)}`,
    );
    setFiles(data.files ?? []);
    setTruncated(Boolean(data.truncated));
  }, [base, root]);
  useEffect(() => {
    loadDiff().then(() => setError(""), (problem: Error) => setError(problem.message));
  }, [loadDiff, revision]);

  const afterRestore = (result: Restored, what: string) => {
    onChanged();
    void loadDiff();
    addToast({
      type: "success",
      title: what,
      description: `${result.restored.length + result.removed.length} file(s) changed back.`,
      action: {
        label: "Undo",
        onClick: () => void restoreCheckpoint(projectId, result.before.id)
          .then(() => { onChanged(); void loadDiff(); })
          .catch((problem: Error) => addToast({ type: "error", title: "Could not undo", description: problem.message })),
      },
    });
  };
  const failed = (problem: unknown) => {
    const busyNow = problem instanceof WorkspaceError && problem.status === 409;
    addToast({
      type: busyNow ? "warning" : "error",
      title: busyNow ? "A chat is working in this project" : "Could not undo the change",
      description: busyNow ? "Try again when that message finishes." : (problem as Error).message,
    });
  };

  const undoFile = async (file: FileChange) => {
    const confirmed = await confirmDialog({
      title: `Undo the changes to ${file.path}?`,
      description: file.status === "added" ? "The file did not exist then, so it is deleted." : "It goes back to how it was at the checkpoint.",
      confirmLabel: "Undo",
      destructive: true,
    });
    if (!confirmed) return;
    setBusy(true);
    try {
      afterRestore(await restoreCheckpoint(projectId, base, [file.path]), `${file.path} put back`);
    } catch (problem) {
      failed(problem);
    } finally {
      setBusy(false);
    }
  };

  const undoAll = async () => {
    const confirmed = await confirmDialog({
      title: "Undo every change since this checkpoint?",
      description: "The whole project goes back. The current files are saved first, so you can undo this too.",
      confirmLabel: "Undo all",
      destructive: true,
    });
    if (!confirmed) return;
    setBusy(true);
    try {
      afterRestore(await restoreCheckpoint(projectId, base), "Project put back");
    } catch (problem) {
      failed(problem);
    } finally {
      setBusy(false);
    }
  };

  if (error) return <p role="alert" className="p-3 text-sm text-destructive">{error}</p>;
  if (!checkpoints.length) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        No checkpoints yet. One is saved before each chat message, so changes appear here after the first.
      </p>
    );
  }

  return (
    <div className="space-y-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-muted-foreground" htmlFor="changes-base">Compared with</label>
        <select
          id="changes-base"
          className="min-w-0 flex-1 rounded-lg border bg-background px-2 py-1 text-sm focus-ring"
          value={base}
          onChange={(event) => { setBase(event.target.value); setReview(null); }}
        >
          {checkpoints.map((item) => (
            <option key={item.id} value={item.id}>
              {item.id === turnCheckpoint ? "Before your last message" : LABELS[item.kind ?? ""] ?? item.message}
              {" · "}{new Date(item.created_at).toLocaleString()}
            </option>
          ))}
        </select>
        <Button size="sm" variant="outline" disabled={busy || !files?.length} onClick={() => void undoAll()}>
          <RotateCcw /> Undo all
        </Button>
      </div>
      {truncated && <p className="text-xs text-muted-foreground">Some of the diff was left out (too long).</p>}
      {files === null ? (
        <p className="text-sm text-muted-foreground">Loading changes…</p>
      ) : files.length === 0 ? (
        <p className="text-sm text-muted-foreground">No changes since this checkpoint.</p>
      ) : (
        <ul className="space-y-2" aria-label="Changed files">
          {files.map((file) => {
            const open = review === file.path;
            const reviewable = file.status !== "deleted" && !file.diff.startsWith("Large or binary");
            return (
              <li key={file.path} className="rounded-lg border">
                <div className="flex items-center gap-2 px-3 py-2">
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 text-left focus-ring rounded"
                    aria-expanded={open}
                    onClick={() => setReview(open ? null : file.path)}
                  >
                    {open ? <ChevronDown className="size-4 shrink-0" /> : <ChevronRight className="size-4 shrink-0" />}
                    <span className="badge-info shrink-0">{file.status}</span>
                    <span className="truncate font-mono text-xs">{file.path}</span>
                  </button>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => void undoFile(file)}>
                    <RotateCcw /> Undo
                  </Button>
                </div>
                {open && (
                  <div className="border-t p-2">
                    {reviewable ? (
                      <Suspense fallback={<p className="p-2 text-xs text-muted-foreground">Loading editor…</p>}>
                        <MergeEditor
                          key={`${base}:${file.path}`}
                          projectId={projectId}
                          checkpointId={base}
                          path={file.path}
                          added={file.status === "added"}
                          onSaved={() => { onChanged(); void loadDiff(); }}
                        />
                      </Suspense>
                    ) : (
                      <DiffView diff={file.diff} />
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
