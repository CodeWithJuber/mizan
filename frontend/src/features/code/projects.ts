/** The person's coding projects: list, create, rename, delete, export, and their chats. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { config } from "../../config";
import { authFetch } from "../../utils/authFetch";
import { useAuth } from "../../app/auth";

export interface Project {
  id: string;
  name: string;
  created_at?: string;
  updated_at?: string;
  reserved?: boolean;
  /** Niyyah: what the project is for ("" or absent: its chat's first request). */
  goal?: string;
}

export interface Capabilities {
  execution_available: boolean;
  execution_detail?: string;
  hardware_inspection: boolean;
}

export interface Checkpoint {
  id: string;
  message: string;
  kind?: "manual" | "agent" | "turn" | "restore";
  created_at: string;
  reused?: boolean;
}

export interface FileChange {
  path: string;
  status: string;
  diff: string;
}

export interface Restored {
  restored: string[];
  removed: string[];
  /** The project as it was just before the restore: restoring it undoes the restore. */
  before: Checkpoint;
}

/** An answer the workspace API refused, with its HTTP status (409: busy, 404: gone). */
export class WorkspaceError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export async function workspaceApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(`${config.API_URL}/workspaces${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Workspace request failed (${response.status})`;
    throw new WorkspaceError(detail, response.status);
  }
  return body as T;
}

export const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const PROJECTS_KEY = ["workspaces"] as const;

export function useProjects() {
  const { token, revision } = useAuth();
  return useQuery({
    queryKey: [...PROJECTS_KEY, revision],
    enabled: Boolean(token),
    staleTime: 10_000,
    queryFn: () => workspaceApi<{ workspaces: Project[]; capabilities: Capabilities }>(""),
  });
}

/** A project's chats, newest first (the split view opens the newest). */
export async function projectChats(projectId: string, limit = 20) {
  const params = new URLSearchParams({ workspace_id: projectId, limit: String(limit) });
  const response = await authFetch(`${config.API_URL}/chat/sessions/list?${params}`);
  if (!response.ok) return [];
  const body = await response.json().catch(() => ({}));
  return (Array.isArray(body.sessions) ? body.sessions : []) as {
    session_id: string;
    title?: string | null;
    first_message?: string;
    last_message_at?: string;
  }[];
}

export function useProjectActions() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: PROJECTS_KEY });
  const create = useMutation({
    mutationFn: (name: string) => workspaceApi<Project>("", jsonBody("POST", { name })),
    onSuccess: refresh,
  });
  const rename = useMutation({
    mutationFn: ({ id, name, goal }: { id: string; name: string; goal?: string }) =>
      workspaceApi<Project>(`/${encodeURIComponent(id)}`, jsonBody("PATCH", { name, ...(goal === undefined ? {} : { goal }) })),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => workspaceApi(`/${encodeURIComponent(id)}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return { create, rename, remove };
}

/** Download the project's files as a zip (the browser saves it). */
export async function exportProject(project: Pick<Project, "id" | "name">) {
  const response = await authFetch(`${config.API_URL}/workspaces/${encodeURIComponent(project.id)}/export.zip`);
  if (!response.ok) throw new WorkspaceError(`Export failed (${response.status})`, response.status);
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const named = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = named || `${project.name.replace(/[^\w.-]+/g, "-") || "project"}.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
}

/** Put files back to a checkpoint (all of them, or `paths`); the current state is saved first. */
export async function restoreCheckpoint(projectId: string, checkpointId: string, paths?: string[]) {
  const restored = await workspaceApi<Restored>(
    `/${encodeURIComponent(projectId)}/checkpoints/${encodeURIComponent(checkpointId)}/restore`,
    jsonBody("POST", paths ? { paths } : {}),
  );
  projectChanged(projectId);
  return restored;
}

const CHANGED = "mizan:project-changed";

/** Tell an open project view that its files changed outside it (a rewind from the chat). */
export function projectChanged(projectId: string) {
  window.dispatchEvent(new CustomEvent(CHANGED, { detail: projectId }));
}

export function onProjectChanged(projectId: string, listener: () => void): () => void {
  const handler = (event: Event) => {
    if ((event as CustomEvent<string>).detail === projectId) listener();
  };
  window.addEventListener(CHANGED, handler);
  return () => window.removeEventListener(CHANGED, handler);
}
