/**
 * /code/:projectId — the project beside its chat. The chat on the left is the
 * project's chat (?chat=<id>, else its newest, else a new one bound to it); the right
 * shows Preview, Code, Changes and Terminal. On a phone a switch shows one at a time.
 */
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Link, useBlocker, useSearchParams } from "react-router-dom";
import { ArrowLeft, FolderCode, MessageSquare } from "lucide-react";
import { Group, Panel, Separator, useDefaultLayout } from "react-resizable-panels";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { confirmDialog } from "@/components/ui/confirm";
import { useIsMobile } from "../../hooks/use-mobile";
import { useChatActions, useChatState } from "../../features/chat/ChatProvider";
import { ChatThread } from "../../features/chat/ChatThread";
import { Composer } from "../../features/chat/Composer";
import { projectChats, useProjects } from "../../features/code/projects";
import { type FixRequest, ProjectWorkspace } from "../../features/code/ProjectWorkspace";
import type { Artifact } from "../../types";

const ArtifactsPanel = lazy(() =>
  import("../../components/ArtifactsPanel").then((module) => ({ default: module.ArtifactsPanel })),
);

/** Layout sizes are a convenience: a browser that refuses storage still works. */
const layoutStorage = {
  getItem: (key: string) => {
    try { return localStorage.getItem(key); } catch { return null; }
  },
  setItem: (key: string, value: string) => {
    try { localStorage.setItem(key, value); } catch { /* not remembered */ }
  },
};

export default function ProjectView({ projectId }: { projectId: string }) {
  const [params] = useSearchParams();
  const chatParam = params.get("chat");
  const isMobile = useIsMobile();
  const state = useChatState();
  const actions = useChatActions();
  const { data, isLoading } = useProjects();
  const project = data?.workspaces.find((item) => item.id === projectId);
  const [view, setView] = useState<"chat" | "project">("project");
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({ id: "mizan-code-split", storage: layoutStorage });

  // Leaving with unsaved editor changes asks first.
  const dirty = useRef(false);
  const setDirty = useCallback((value: boolean) => {
    dirty.current = value;
  }, []);
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty.current && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    void confirmDialog({
      title: "Leave the editor?",
      description: "Unsaved changes in the editor will be lost.",
      confirmLabel: "Leave",
      destructive: true,
    }).then((leave) => {
      if (leave) {
        dirty.current = false;
        blocker.proceed();
      } else blocker.reset();
    });
  }, [blocker]);

  // The chat on the left is this project's chat. Sending waits until it is settled:
  // a message sent while it was still being looked up would be dropped by the switch.
  const chatKey = `${projectId}:${chatParam ?? ""}`;
  const [readyChat, setReadyChat] = useState("");
  useEffect(() => {
    let cancelled = false;
    const settled = () => {
      if (!cancelled) setReadyChat(chatKey);
    };
    if (state.streaming) {
      settled();
      return;
    }
    void (async () => {
      try {
        if (chatParam) {
          if (chatParam !== state.sessionId) await actions.switchSession(chatParam);
          return;
        }
        if (state.workspaceId === projectId) return;
        const [newest] = await projectChats(projectId, 1);
        if (cancelled) return;
        if (newest) {
          await actions.switchSession(newest.session_id);
        } else {
          actions.startNewSession();
          actions.selectWorkspace(projectId);
        }
      } finally {
        settled();
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, chatParam]);

  // A reply that finished may have changed files: the project reloads them.
  const [filesRevision, setFilesRevision] = useState(0);
  const wasStreaming = useRef(state.streaming);
  useEffect(() => {
    if (wasStreaming.current && !state.streaming) setFilesRevision((value) => value + 1);
    wasStreaming.current = state.streaming;
  }, [state.streaming]);

  const turnCheckpoint = [...state.messages]
    .reverse()
    .find((message) => message.role === "user" && message.checkpoint?.workspace_id === projectId)
    ?.checkpoint?.id;
  const livePreviewUrl = state.livePreview?.workspaceId === projectId ? state.livePreview.url : undefined;
  const bound = state.workspaceId === projectId;

  const onFix = useCallback((fix: FixRequest) => {
    if (state.streaming) return;
    void actions.sendMessage("Fix this error", {
      fix,
      ...(state.permissionMode === "plan" ? { permissionMode: "auto_edits" as const } : {}),
    });
    setView("chat");
  }, [actions, state.permissionMode, state.streaming]);

  const onArtifact = useCallback((artifact: Artifact) => {
    if (artifact.session_id !== state.sessionId) return;
    actions.addArtifact({
      ...artifact,
      versions: artifact.versions ?? (typeof artifact.content === "string"
        ? [{
            version: artifact.current_version ?? 1,
            content: artifact.content,
            created_at: artifact.created_at ?? new Date().toISOString(),
          }]
        : []),
    } as Artifact);
  }, [actions, state.sessionId]);

  if (!isLoading && data && !project) {
    return (
      <div className="page-wrapper items-center justify-center gap-3 p-6 text-center">
        <p className="font-medium">This project is gone</p>
        <p className="text-sm text-muted-foreground">It was deleted, or it belongs to someone else.</p>
        <Link to="/code" className="text-sm text-brand underline">Back to your projects</Link>
      </div>
    );
  }

  const chat = (
    <div className="flex h-full min-h-0 flex-col">
      <ChatThread />
      {readyChat === chatKey ? (
        <Composer />
      ) : (
        <p aria-live="polite" className="border-t p-3 text-sm text-muted-foreground">Opening this project's chat…</p>
      )}
    </div>
  );
  const workspace = (
    <ProjectWorkspace
      projectId={projectId}
      sessionId={state.sessionId}
      capabilities={data?.capabilities ?? null}
      turnCheckpoint={turnCheckpoint}
      livePreviewUrl={livePreviewUrl}
      filesRevision={filesRevision}
      onArtifact={onArtifact}
      onDirtyChange={setDirty}
      onFix={bound ? onFix : undefined}
    />
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
        <SidebarTrigger className="-ml-1 md:hidden" />
        <Link to="/code" className="rounded p-1 text-muted-foreground hover:text-foreground focus-ring" aria-label="All projects">
          <ArrowLeft className="size-4" />
        </Link>
        <FolderCode className="size-4 shrink-0 text-brand" />
        <h1 className="min-w-0 flex-1 truncate text-sm font-medium" title={project?.name}>{project?.name ?? "Project"}</h1>
        {isMobile && (
          <fieldset className="flex overflow-hidden rounded-lg border text-sm">
            <legend className="sr-only">Show</legend>
            {(["chat", "project"] as const).map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={view === item}
                onClick={() => setView(item)}
                className={`flex items-center gap-1 px-2.5 py-1 ${view === item ? "bg-muted font-medium" : "text-muted-foreground"}`}
              >
                {item === "chat" ? <MessageSquare className="size-3.5" /> : <FolderCode className="size-3.5" />}
                {item === "chat" ? "Chat" : "Project"}
                {item === "chat" && view === "project" && state.activity.approvals.some((entry) => !entry.decision) && (
                  <>
                    <span className="size-2 rounded-full bg-primary" aria-hidden />
                    <span className="sr-only">approval needed</span>
                  </>
                )}
              </button>
            ))}
          </fieldset>
        )}
      </header>
      {isMobile ? (
        <div className="min-h-0 flex-1">{view === "chat" ? chat : workspace}</div>
      ) : (
        <Group orientation="horizontal" defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged} className="min-h-0 flex-1">
          <Panel id="chat" defaultSize="40" minSize={300}>
            {chat}
          </Panel>
          <Separator className="w-px bg-border transition-colors outline-none hover:bg-primary/60 data-[separator=active]:bg-primary focus-visible:bg-primary" />
          <Panel id="project" minSize={360}>
            {workspace}
          </Panel>
        </Group>
      )}
      {/* "To chat" from the project opens its artifacts here, not on the next /chat visit. */}
      {state.showArtifacts && (
        <Suspense fallback={null}>
          <ArtifactsPanel
            artifacts={state.artifacts}
            sessionId={state.sessionId}
            onClose={() => actions.setShowArtifacts(false)}
          />
        </Suspense>
      )}
    </div>
  );
}
