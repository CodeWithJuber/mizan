/** Agents: the person's team. Pick who answers in chat, create, edit, delete. */
import { useState } from "react";
import { Plus, Settings2, Trash2, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentCard } from "../components/AgentCard";
import { AgentModal } from "../components/AgentModal";
import { addToast } from "../components/Toast";
import { confirmDialog } from "../components/ui/confirm";
import { useApi } from "../hooks/useApi";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";
import { agentCreatePayload, agentFormData, agentSettingsScope, saveAgentEdits, type AgentFormData } from "../utils/agentSettings.ts";
import { useAuth } from "../app/auth";
import { useAgents, useRefreshAgents, useSelectedAgent, useSelectedAgentId } from "../features/agents/agents";
import type { Agent } from "../types";
import { PageHeader } from "../app/PageHeader";

export default function AgentsPage() {
  const api = useApi();
  const { data: agents = [], isLoading } = useAgents();
  const selected = useSelectedAgent();
  const select = useSelectedAgentId((state) => state.select);
  const refresh = useRefreshAgents();
  const [editing, setEditing] = useState<Agent | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [initial, setInitial] = useState<AgentFormData>(() => agentFormData());
  const scope = () => agentSettingsScope(() => localStorage.getItem("mizan_token"), () => useAuth.getState().revision);

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
      await authFetch(`${config.API_URL}/agents/${agent.id}`, { method: "DELETE" });
      if (selected?.id === agent.id) select(null);
      refresh();
      addToast({ type: "success", title: "Agent deleted" });
    } catch {
      addToast({ type: "error", title: "Agent not deleted" });
    }
  };

  return (
    <div className="page-wrapper">
      <PageHeader
        title="Agents"
        description="Your AI team. The selected agent answers in chat."
        actions={
          <Button
            onClick={() => {
              setEditing(null);
              setInitial(agentFormData());
              setModalOpen(true);
            }}
          >
            <Plus /> New agent
          </Button>
        }
      />
      <div className="page-body">
        {agents.length === 0 && !isLoading ? (
          <div className="empty-state">
            <Users className="size-8 text-muted-foreground" />
            <p className="empty-text mt-3">No agents yet</p>
            <p className="empty-sub">Create your first agent, or check that the server is running.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {agents.map((agent) => (
              <div key={agent.id} className="group relative">
                <AgentCard agent={agent} selected={selected?.id === agent.id} onClick={() => select(agent.id)} />
                <div className="absolute right-3 top-3 flex items-center gap-0.5 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Edit ${agent.name}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      setEditing(agent);
                      setInitial(agentFormData(agent));
                      setModalOpen(true);
                    }}
                  >
                    <Settings2 />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete ${agent.name}`}
                    className="hover:text-destructive"
                    onClick={(event) => {
                      event.stopPropagation();
                      void remove(agent);
                    }}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {modalOpen && (
        <AgentModal
          key={editing?.id ?? "new"}
          editingAgent={editing}
          initialData={initial}
          api={api}
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
