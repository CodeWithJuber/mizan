/** Turn the store's flat path list into a sorted folder tree. */

export interface WorkspaceEntry {
  path: string;
  kind: "file" | "directory";
  size: number;
}

export interface TreeNode {
  name: string;
  path: string;
  kind: "file" | "directory";
  size: number;
  children: TreeNode[];
}

export function buildTree(entries: WorkspaceEntry[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", kind: "directory", size: 0, children: [] };
  const index = new Map<string, TreeNode>([["", root]]);
  const ensureDirectory = (path: string): TreeNode => {
    const existing = index.get(path);
    if (existing) return existing;
    const slash = path.lastIndexOf("/");
    const parent = ensureDirectory(slash < 0 ? "" : path.slice(0, slash));
    const node: TreeNode = { name: path.slice(slash + 1), path, kind: "directory", size: 0, children: [] };
    parent.children.push(node);
    index.set(path, node);
    return node;
  };
  for (const entry of entries) {
    if (entry.kind === "directory") {
      ensureDirectory(entry.path);
      continue;
    }
    const slash = entry.path.lastIndexOf("/");
    const parent = ensureDirectory(slash < 0 ? "" : entry.path.slice(0, slash));
    if (!parent.children.some((child) => child.path === entry.path)) {
      parent.children.push({ name: entry.path.slice(slash + 1), path: entry.path, kind: "file", size: entry.size, children: [] });
    }
  }
  const sort = (node: TreeNode) => {
    node.children.sort((a, b) =>
      a.kind !== b.kind ? (a.kind === "directory" ? -1 : 1) : a.name.localeCompare(b.name));
    node.children.forEach(sort);
  };
  sort(root);
  return root.children;
}

/** Folders that should start open: the parents of the open file. */
export function ancestors(path: string): string[] {
  const parts = path.split("/");
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join("/"));
}

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "jsx",
  ts: "typescript", tsx: "tsx", py: "python", html: "html", htm: "html",
  css: "css", json: "json", md: "markdown", markdown: "markdown",
};

export function languageOf(path: string): string {
  const extension = path.split(".").pop()?.toLowerCase() ?? "";
  return LANGUAGE_BY_EXTENSION[extension] ?? "text";
}
