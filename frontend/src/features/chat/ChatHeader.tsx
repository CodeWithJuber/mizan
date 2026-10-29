/** The chat's title, who answers, and what can be done with the chat. */
import { lazy, Suspense, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Check, ChevronDown, Download, Ellipsis, FileStack, FolderCode, PencilLine, SquarePen, Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { NAFS_LEVELS } from "../../components/AgentCard";
import { useAgents, useSelectedAgent, useSelectedAgentId } from "../agents/agents";
import { useChatActions, useChatState } from "./ChatProvider";
import { chatTitle, useChatRow } from "./sessions";
import { RenameDialog } from "./RenameDialog";

const ArtifactsPanel = lazy(() =>
  import("../../components/ArtifactsPanel").then((module) => ({ default: module.ArtifactsPanel })),
);

export function ChatHeader() {
  const state = useChatState();
  const actions = useChatActions();
  const navigate = useNavigate();
  const { data: agents = [] } = useAgents();
  const selected = useSelectedAgent();
  const select = useSelectedAgentId((store) => store.select);
  const row = useChatRow(state.sessionId);
  const [renaming, setRenaming] = useState(false);
  const hasChat = state.messages.length > 0;
  const previewReady = Boolean(state.workspaceId) && state.livePreview?.workspaceId === state.workspaceId;
  const title = hasChat ? chatTitle(row ?? { first_message: state.messages.find((m) => m.role === "user")?.content }) : "New chat";

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 sm:px-4">
      <SidebarTrigger className="-ml-1 md:hidden" />
      <h1 className="min-w-0 flex-1 truncate text-sm font-medium" title={title}>{title}</h1>

      {state.workspaceId && (
        <Link
          to={`/code/${encodeURIComponent(state.workspaceId)}?chat=${encodeURIComponent(state.sessionId)}`}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          aria-label={previewReady ? "Open project (preview ready)" : "Open project"}
          title={previewReady ? "The project's server is running: open it beside this chat" : "Open the project beside this chat"}
        >
          <FolderCode className="text-brand" />
          <span className="hidden sm:inline">Open project</span>
          {previewReady && <span className="size-2 rounded-full bg-success" />}
        </Link>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button variant="ghost" size="sm" className="max-w-48 gap-1.5" title="Choose who answers" />}
        >
          <span className="truncate">{selected?.name ?? "MIZAN"}</span>
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuGroup>
            <DropdownMenuLabel>Who answers</DropdownMenuLabel>
            {agents.map((agent) => (
              <DropdownMenuItem key={agent.id} onClick={() => select(agent.id)}>
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-brand">
                  {agent.name[0]?.toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{agent.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    Level {agent.nafs_level} · {NAFS_LEVELS[agent.nafs_level]?.latin ?? agent.role}
                  </span>
                </span>
                {selected?.id === agent.id && <Check className="size-4 text-brand" />}
              </DropdownMenuItem>
            ))}
            {agents.length === 0 && <DropdownMenuItem disabled>No agents loaded</DropdownMenuItem>}
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => navigate("/agents")}>Manage agents</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Button
        variant="ghost"
        size="icon"
        aria-label="New chat"
        title="New chat"
        className="md:hidden"
        onClick={() => {
          actions.startNewSession();
          navigate("/chat");
        }}
      >
        <SquarePen />
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="Chat options" />}>
          <Ellipsis />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuItem disabled={!hasChat} onClick={() => setRenaming(true)}>
            <PencilLine /> Rename
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => actions.setShowArtifacts(!state.showArtifacts)}>
            <FileStack /> Artifacts{state.artifacts.length ? ` (${state.artifacts.length})` : ""}
          </DropdownMenuItem>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger disabled={!hasChat}>
              <Download /> Export
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem onClick={() => void actions.exportChat("markdown")}>Markdown (.md)</DropdownMenuItem>
              <DropdownMenuItem onClick={() => void actions.exportChat("text")}>Plain text (.txt)</DropdownMenuItem>
              <DropdownMenuItem onClick={() => void actions.exportChat("json")}>JSON (.json)</DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            disabled={!hasChat}
            onClick={async () => {
              if (await actions.deleteSession(state.sessionId)) navigate("/chat");
            }}
          >
            <Trash2 /> Delete chat
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <RenameDialog sessionId={state.sessionId} current={hasChat ? title : ""} open={renaming} onOpenChange={setRenaming} />
      {state.showArtifacts && (
        <Suspense fallback={null}>
          <ArtifactsPanel
            artifacts={state.artifacts}
            sessionId={state.sessionId}
            onClose={() => actions.setShowArtifacts(false)}
          />
        </Suspense>
      )}
    </header>
  );
}
