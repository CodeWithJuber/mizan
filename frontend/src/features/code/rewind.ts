/** "Rewind code to before this message": show what changes back, restore, offer Undo. */
import { confirmDialog } from "@/components/ui/confirm";
import { addToast } from "../../components/Toast";
import { type FileChange, restoreCheckpoint, workspaceApi, WorkspaceError } from "./projects";

export async function rewindTo(checkpoint: { workspace_id: string; id: string }) {
  const project = checkpoint.workspace_id;
  let files: FileChange[];
  try {
    const diff = await workspaceApi<{ files: FileChange[] }>(
      `/${encodeURIComponent(project)}/diff?checkpoint_id=${encodeURIComponent(checkpoint.id)}`,
    );
    files = diff.files ?? [];
  } catch (problem) {
    addToast({ type: "error", title: "Could not read the checkpoint", description: (problem as Error).message });
    return;
  }
  if (!files.length) {
    addToast({ type: "info", title: "Nothing to rewind", description: "The code is already as it was before this message." });
    return;
  }
  const shown = files.slice(0, 6).map((file) => `${file.path} (${file.status})`).join(", ");
  const more = files.length > 6 ? ` and ${files.length - 6} more` : "";
  const confirmed = await confirmDialog({
    title: "Rewind the code to before this message?",
    description: `${files.length} file(s) go back: ${shown}${more}. The current files are saved first, so you can undo this.`,
    confirmLabel: "Rewind",
    destructive: true,
  });
  if (!confirmed) return;
  try {
    const result = await restoreCheckpoint(project, checkpoint.id);
    addToast({
      type: "success",
      title: "Code rewound",
      description: `${result.restored.length + result.removed.length} file(s) changed back. The chat itself is unchanged.`,
      action: {
        label: "Undo",
        onClick: () => void restoreCheckpoint(project, result.before.id).catch((problem: Error) =>
          addToast({ type: "error", title: "Could not undo the rewind", description: problem.message })),
      },
    });
  } catch (problem) {
    const busy = problem instanceof WorkspaceError && problem.status === 409;
    addToast({
      type: busy ? "warning" : "error",
      title: busy ? "A chat is working in this project" : "Could not rewind the code",
      description: busy ? "Rewind when that message finishes." : (problem as Error).message,
    });
  }
}
