/**
 * Agents: the person's team. Pick who answers in chat; build, edit, clone,
 * export and import agents; choose the default one. Everyone may build their
 * own (private) agents; an admin may also share one with everyone.
 */
import { useRef, useState } from "react";
import { Copy, Download, Ellipsis, Plus, Settings2, Star, Trash2, Upload, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AgentCard } from "../components/AgentCard";
import { AgentModal } from "../components/AgentModal";
import { SkeletonCard } from "../components/Skeleton";
import { addToast } from "../components/Toast";
import { confirmDialog } from "../components/ui/confirm";
import { useApi } from "../hooks/useApi";
import {
  agentCreatePayload, agentExportFilename, agentFormData, agentSettingsScope, agentToolCatalog, parseAgentImport,
  saveAgentEdits, type AgentFormData,
} from "../utils/agentSettings.ts";
import { downloadExport } from "../utils/exportChat";
import { useAuth, useIsAdmin, useMe } from "../app/auth";
import { useAgents, useRefreshAgents, useSelectedAgent, useSelectedAgentId } from "../features/agents/agents";
import type { Agent } from "../types";
import { PageHeader } from "../app/PageHeader";

const IMPORT_MAX_BYTES = 1024 * 1024;

const agentName = (value: Record<string, unknown>, fallback: string) =>
  typeof value.name === "string" && value.name ? value.name : fallback;

export default function AgentsPage() {
  const api = useApi();
  const { data: agents = [], isLoading } = useAgents();
  const { data: me } = useMe();
  const isAdmin = useIsAdmin();
  const selected = useSelectedAgent();
  const select = useSelectedAgentId((state) => state.select);
  const refresh = useRefreshAgents();
  const [editing, setEditing] = useState<Agent | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [initial, setInitial] = useState<AgentFormData>(() => agentFormData());
  const importRef = useRef<HTMLInputElement | null>(null);
  const scope = () => agentSettingsScope(() => localStorage.getItem("mizan_token"), () => useAuth.getState().revision);
  // Older servers send no `editable`: there only admins could change agents.
  const canEdit = (agent: Agent) => agent.editable ?? isAdmin;
  const toolCatalog = agentToolCatalog(agents);
  // A person who sees only agents others made is invited to build their own.
  const ownsNone = !isAdmin && !!me
    && agents.some((agent) => agent.owner_id !== undefined)
    && !agents.some((agent) => agent.owner_id === me.user_id);

  const openNew = () => {
    setEditing(null);
    // An admin's new agent is shared unless they turn it off; anyone else's is private.
    setInitial({ ...agentFormData(), shared: isAdmin });
    setModalOpen(true);
  };
  const openEdit = (agent: Agent) => {
    setEditing(agent);
    setInitial(agentFormData(agent));
    setModalOpen(true);
  };

  const create = async (data: AgentFormData) => {
    const isCurrent = scope();
    try {
      await api.post("/agents", agentCreatePayload(data));
      if (!isCurrent()) return;
      setModalOpen(false);
      refresh();
      addToast({ type: "success", title: "Agent created", description: `${data.name} is ready` });
    } catch (error) {
      if (isCurrent()) addToast({ type: "error", title: "Failed to create agent", description: (error as Error).message });
    }
  };

  const update = async (data: AgentFormData) => {
    if (!editing) return;
    const isCurrent = scope();
    try {
      const saved = await saveAgentEdits(api, editing, data, isCurrent);
      if (!saved || !isCurrent()) return;
      setModalOpen(false);
      setEditing(null);
      refresh();
      addToast({ type: "success", title: "Agent updated" });
    } catch (error) {
      if (!isCurrent()) return;
      // A model change can succeed before a separate name/prompt save fails:
      // refresh so the cards show the server's actual settings.
      refresh();
      addToast({ type: "error", title: "Failed to update agent", description: (error as Error).message });
    }
  };

  const remove = async (agent: Agent) => {
    if (!(await confirmDialog({ title: `Delete ${agent.name}?`, destructive: true }))) return;
    try {
      await api.del(`/agents/${encodeURIComponent(agent.id)}`);
      if (selected?.id === agent.id) select(null);
      refresh();
      addToast({ type: "success", title: "Agent deleted" });
    } catch (error) {
      addToast({ type: "error", title: "Agent not deleted", description: (error as Error).message });
    }
  };

  const clone = async (agent: Agent) => {
    try {
      const copy = (await api.post(`/agents/${encodeURIComponent(agent.id)}/clone`)) as unknown as Agent;
      refresh();
      addToast({
        type: "success",
        title: `Copied as ${agentName(copy as unknown as Record<string, unknown>, `${agent.name} (copy)`)}`,
        description: "The copy is yours to change.",
        ...(copy && typeof copy.id === "string" ? { action: { label: "Edit", onClick: () => openEdit(copy) } } : {}),
      });
    } catch (error) {
      addToast({ type: "error", title: "Agent not copied", description: (error as Error).message });
    }
  };

  const exportAgent = async (agent: Agent) => {
    try {
      const data = await api.get(`/agents/${encodeURIComponent(agent.id)}/export`);
      downloadExport(agentExportFilename(agent.name), "application/json", `${JSON.stringify(data, null, 2)}\n`);
    } catch (error) {
      addToast({ type: "error", title: "Agent not exported", description: (error as Error).message });
    }
  };

  const makeDefault = async (agent: Agent) => {
    try {
      await api.put("/agents/default", { agent_id: agent.id });
      select(agent.id);
      refresh();
      addToast({ type: "success", title: `${agent.name} is your default agent`, description: "It answers when you have not picked another." });
    } catch (error) {
      addToast({ type: "error", title: "Default not changed", description: (error as Error).message });
    }
  };

  const importFile = async (file: File) => {
    try {
      if (file.size > IMPORT_MAX_BYTES) throw new Error("This file is larger than 1 MB: an agent file is much smaller.");
      const body = parseAgentImport(await file.text());
      const created = await api.post("/agents/import", body);
      refresh();
      addToast({ type: "success", title: "Agent imported", description: `${agentName(created, agentName(body.agent, "The agent"))} is ready` });
    } catch (error) {
      addToast({ type: "error", title: "Agent not imported", description: (error as Error).message });
    }
  };

  return (
    <div className="page-wrapper">
      <PageHeader
        sub
        description="Your AI team. The selected agent answers in chat."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => importRef.current?.click()}>
              <Upload /> Import agent
            </Button>
            <Button onClick={openNew}>
              <Plus /> New agent
            </Button>
          </div>
        }
      />
      <input
        ref={importRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        aria-label="Agent file to import"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) void importFile(file);
        }}
      />
      <div className="page-body">
        {ownsNone && (
          <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-primary/30 bg-primary/5 p-4">
            <Users className="size-5 shrink-0 text-brand" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">Build an agent of your own</p>
              <p className="text-xs text-muted-foreground">
                These agents are shared by your server. Make one with your own instructions, model, tools and starter
                prompts: only you will see it.
              </p>
            </div>
            <Button size="sm" onClick={openNew}>
              <Plus /> New agent
            </Button>
          </div>
        )}
        {agents.length === 0 && !isLoading ? (
          <div className="empty-state">
            <Users className="size-8 text-muted-foreground" />
            <p className="empty-text mt-3">No agents yet</p>
            <p className="empty-sub">Create your first agent, or check that the server is running.</p>
            <Button className="mt-4" onClick={openNew}>
              <Plus /> New agent
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {agents.length === 0 && isLoading && <SkeletonCard count={3} />}
            {agents.map((agent) => {
              const editable = canEdit(agent);
              return (
                <div key={agent.id} className="group relative">
                  <AgentCard agent={agent} selected={selected?.id === agent.id} onClick={() => select(agent.id)} />
                  <div className="absolute right-3 top-3 flex items-center gap-0.5 rounded-md bg-card/90 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 md:has-[[data-popup-open]]:opacity-100">
                    {editable && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Edit ${agent.name}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          openEdit(agent);
                        }}
                      >
                        <Settings2 />
                      </Button>
                    )}
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={<Button variant="ghost" size="icon-sm" aria-label={`More for ${agent.name}`} />}
                        onClick={(event) => event.stopPropagation()}
                      >
                        <Ellipsis />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48">
                        <DropdownMenuItem onClick={() => void clone(agent)}>
                          <Copy /> Clone
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => void exportAgent(agent)}>
                          <Download /> Export
                        </DropdownMenuItem>
                        <DropdownMenuItem disabled={agent.is_default === true} onClick={() => void makeDefault(agent)}>
                          <Star /> {agent.is_default ? "Default agent" : "Make default"}
                        </DropdownMenuItem>
                        {editable && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem variant="destructive" onClick={() => void remove(agent)}>
                              <Trash2 /> Delete
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {modalOpen && (
        <AgentModal
          key={editing?.id ?? "new"}
          editingAgent={editing}
          initialData={initial}
          api={api}
          canShare={isAdmin}
          toolCatalog={toolCatalog}
          onSave={(data) => (editing ? update(data) : create(data))}
          onClose={() => {
            setModalOpen(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}
