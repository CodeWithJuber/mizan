/** /code: the person's projects. Open one beside its chat, or rename, export or delete it. */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Download, FolderCode, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { PageHeader } from "../../app/PageHeader";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { confirmDialog } from "@/components/ui/confirm";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { addToast } from "../../components/Toast";
import { exportProject, type Project, useProjectActions, useProjects, WorkspaceError } from "../../features/code/projects";

function when(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}

export default function ProjectList() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useProjects();
  const { create, rename, remove } = useProjectActions();
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState<Project | null>(null);
  const [newName, setNewName] = useState("");
  const [newGoal, setNewGoal] = useState("");
  const projects = (data?.workspaces ?? []).filter((project) => !project.reserved);

  const failed = (title: string) => (problem: unknown) =>
    addToast({ type: "error", title, description: problem instanceof Error ? problem.message : undefined });

  const deleteProject = async (project: Project) => {
    const confirmed = await confirmDialog({
      title: `Delete ${project.name}?`,
      description: "Its files, checkpoints and server session are removed. Chats that used it keep their messages.",
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;
    remove.mutate(project.id, {
      onSuccess: () => addToast({ type: "success", title: `${project.name} deleted` }),
      onError: (problem) =>
        problem instanceof WorkspaceError && problem.status === 409
          ? addToast({ type: "warning", title: "A chat is working in this project", description: "Delete it when that message finishes." })
          : failed("Could not delete the project")(problem),
    });
  };

  return (
    <div className="page-wrapper">
      <PageHeader title="Code" description="Your projects. Open one to work on it beside its chat." />
      <div className="mx-auto w-full max-w-3xl flex-1 space-y-6 overflow-y-auto px-4 py-6 sm:px-6">
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const trimmed = name.trim();
            if (!trimmed) return;
            create.mutate(trimmed, {
              onSuccess: (project) => {
                setName("");
                navigate(`/code/${encodeURIComponent(project.id)}`);
              },
              onError: failed("Could not create the project"),
            });
          }}
        >
          <Input
            aria-label="New project name"
            placeholder="New project name"
            value={name}
            maxLength={100}
            onChange={(event) => setName(event.target.value)}
          />
          <Button type="submit" disabled={!name.trim() || create.isPending}>
            <Plus /> Create
          </Button>
        </form>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading projects…</p>
        ) : error ? (
          <p role="alert" className="text-sm text-destructive">Could not load your projects.</p>
        ) : projects.length === 0 ? (
          <div className="rounded-xl border border-dashed p-8 text-center">
            <FolderCode className="mx-auto size-8 text-brand" />
            <p className="mt-3 font-medium">No projects yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Create one above, or ask in a chat: "Build me a todo app in React".
            </p>
          </div>
        ) : (
          <ul className="divide-y rounded-xl border" aria-label="Projects">
            {projects.map((project) => (
              <li key={project.id} className="flex items-center gap-3 p-3 sm:p-4">
                <FolderCode className="size-5 shrink-0 text-brand" />
                <Link to={`/code/${encodeURIComponent(project.id)}`} className="min-w-0 flex-1 focus-ring rounded">
                  <span className="block truncate font-medium">{project.name}</span>
                  {project.updated_at && (
                    <span className="block text-xs text-muted-foreground">Changed {when(project.updated_at)}</span>
                  )}
                </Link>
                <Link to={`/code/${encodeURIComponent(project.id)}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                  Open
                </Link>
                <DropdownMenu>
                  <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label={`More for ${project.name}`} />}>
                    <MoreHorizontal />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => { setRenaming(project); setNewName(project.name); setNewGoal(project.goal ?? ""); }}>
                      <Pencil /> Rename or set goal
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void exportProject(project).catch(failed("Could not export the project"))}>
                      <Download /> Export as zip
                    </DropdownMenuItem>
                    <DropdownMenuItem variant="destructive" onClick={() => void deleteProject(project)}>
                      <Trash2 /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Dialog open={renaming !== null} onOpenChange={(open) => !open && setRenaming(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename project or set its goal</DialogTitle>
            <DialogDescription>
              The name is shown here and in the project's chats. MIZAN reads each answer's work against the goal and
              notes under the answer when work drifts from it; it never stops anything.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const trimmed = newName.trim();
              if (!renaming || !trimmed) return;
              rename.mutate({ id: renaming.id, name: trimmed, goal: newGoal.trim() }, { onError: failed("Could not save the project") });
              setRenaming(null);
            }}
          >
            <Input autoFocus aria-label="Project name" value={newName} maxLength={100} onChange={(event) => setNewName(event.target.value)} />
            <div className="mt-3 space-y-1">
              <Label htmlFor="project-goal">Goal</Label>
              <Textarea id="project-goal" value={newGoal} maxLength={1000} aria-describedby="project-goal-hint"
                placeholder="For example: a prayer-times app for my masjid" onChange={(event) => setNewGoal(event.target.value)} />
              <p id="project-goal-hint" className="text-xs text-muted-foreground">
                Empty: the first request of the project's chat is its goal.
              </p>
            </div>
            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setRenaming(null)}>Cancel</Button>
              <Button type="submit" disabled={!newName.trim()}>Save</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
