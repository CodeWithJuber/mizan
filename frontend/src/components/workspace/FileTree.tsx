/** Folder tree for a coding project with create, rename and delete. */
import { useMemo, useState } from "react";
import {
  ChevronDown, ChevronRight, FilePlus, FileText, Folder, FolderOpen, FolderPlus, Pencil, Trash2,
} from "lucide-react";
import { ancestors, buildTree, type TreeNode, type WorkspaceEntry } from "../../utils/workspaceTree";
import { confirmDialog } from "@/components/ui/confirm";

interface Props {
  entries: WorkspaceEntry[];
  selected: string;
  disabled?: boolean;
  onOpen: (path: string) => void;
  onCreate: (kind: "file" | "directory", path: string) => void;
  onRename: (path: string, next: string) => void;
  onDelete: (path: string) => void;
}

export default function FileTree({ entries, selected, disabled, onOpen, onCreate, onRename, onDelete }: Props) {
  const tree = useMemo(() => buildTree(entries), [entries]);
  const [open, setOpen] = useState<Set<string>>(() => new Set(ancestors(selected)));
  const [draft, setDraft] = useState<{ kind: "file" | "directory"; value: string } | null>(null);

  const toggle = (path: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });

  const render = (nodes: TreeNode[], depth: number) => nodes.map((node) => {
    const isOpen = open.has(node.path) || ancestors(selected).includes(node.path);
    const active = node.path === selected;
    return (
      <li key={node.path}>
        <div className={`group flex items-center gap-1 rounded-md pr-1 ${active ? "bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300" : "hover:bg-gray-100 dark:hover:bg-zinc-900"}`} style={{ paddingLeft: depth * 12 + 4 }}>
          <button
            type="button"
            disabled={disabled}
            className="flex-1 min-w-0 flex items-center gap-1 py-1 text-left text-xs font-mono focus-ring"
            onClick={() => node.kind === "directory" ? toggle(node.path) : onOpen(node.path)}
            title={node.path}
            aria-expanded={node.kind === "directory" ? isOpen : undefined}
          >
            {node.kind === "directory" ? (
              <>
                {isOpen ? <ChevronDown className="w-3 h-3 shrink-0" /> : <ChevronRight className="w-3 h-3 shrink-0" />}
                {isOpen ? <FolderOpen className="w-3.5 h-3.5 shrink-0 text-amber-600" /> : <Folder className="w-3.5 h-3.5 shrink-0 text-amber-600" />}
              </>
            ) : (
              <>
                <span className="w-3" />
                <FileText className="w-3.5 h-3.5 shrink-0 text-gray-400" />
              </>
            )}
            <span className="truncate">{node.name}</span>
          </button>
          {node.kind === "file" && !disabled && (
            <span className="hidden group-hover:flex group-focus-within:flex gap-0.5">
              <button
                type="button"
                className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-zinc-800"
                aria-label={`Rename ${node.path}`}
                onClick={() => {
                  const next = window.prompt("New path", node.path)?.trim();
                  if (next && next !== node.path) onRename(node.path, next);
                }}
              >
                <Pencil className="w-3 h-3" />
              </button>
              <button
                type="button"
                className="p-0.5 rounded hover:bg-rose-100 dark:hover:bg-rose-950 text-rose-600"
                aria-label={`Delete ${node.path}`}
                onClick={async () => { if (await confirmDialog({ title: `Delete ${node.path}?`, destructive: true })) onDelete(node.path); }}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </span>
          )}
        </div>
        {node.kind === "directory" && isOpen && node.children.length > 0 && (
          <ul>{render(node.children, depth + 1)}</ul>
        )}
      </li>
    );
  });

  return (
    <div className="flex flex-col min-h-0">
      <div className="flex items-center justify-between px-2 py-2">
        <h2 className="text-2xs uppercase tracking-wider font-semibold text-gray-500">Files</h2>
        <div className="flex gap-1">
          <button type="button" className="p-1 rounded hover:bg-gray-100 dark:hover:bg-zinc-800" aria-label="New file" disabled={disabled} onClick={() => setDraft({ kind: "file", value: "" })}>
            <FilePlus className="w-3.5 h-3.5" />
          </button>
          <button type="button" className="p-1 rounded hover:bg-gray-100 dark:hover:bg-zinc-800" aria-label="New folder" disabled={disabled} onClick={() => setDraft({ kind: "directory", value: "" })}>
            <FolderPlus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      {draft && (
        <form
          className="px-2 pb-2"
          onSubmit={(event) => {
            event.preventDefault();
            const value = draft.value.trim().replace(/^\/+/, "");
            if (value) onCreate(draft.kind, value);
            setDraft(null);
          }}
        >
          <input
            autoFocus
            className="w-full px-2 py-1 rounded-md border border-border bg-background text-xs font-mono focus-ring"
            placeholder={draft.kind === "file" ? "src/main.py" : "src/components"}
            value={draft.value}
            onChange={(event) => setDraft({ ...draft, value: event.target.value })}
            onBlur={() => setDraft(null)}
            onKeyDown={(event) => { if (event.key === "Escape") setDraft(null); }}
            aria-label={draft.kind === "file" ? "New file path" : "New folder path"}
          />
        </form>
      )}
      {tree.length ? (
        <ul className="px-1 pb-3 overflow-auto">{render(tree, 0)}</ul>
      ) : (
        <p className="px-3 py-3 text-xs text-gray-400">No files yet. Create one, or ask the agent.</p>
      )}
    </div>
  );
}
