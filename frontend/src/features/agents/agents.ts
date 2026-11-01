/** The person's agents and which one chats. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { create } from "zustand";
import { config } from "../../config";
import { authFetch } from "../../utils/authFetch";
import { useAuth } from "../../app/auth";
import type { Agent } from "../../types";

const KEY = "mizan_selected_agent";

const readSelected = (): string | null => {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
};

export const useSelectedAgentId = create<{ id: string | null; select: (id: string | null) => void }>((set) => ({
  id: readSelected(),
  select: (id) => {
    try {
      if (id) localStorage.setItem(KEY, id);
      else localStorage.removeItem(KEY);
    } catch {
      // The choice still applies for this visit.
    }
    set({ id });
  },
}));

export function agentsQueryKey(revision: number) {
  return ["agents", revision] as const;
}

/** GET /api/agents, refreshed while the page is open (levels and state change as agents work). */
export function useAgents() {
  const { token, revision } = useAuth();
  return useQuery({
    queryKey: agentsQueryKey(revision),
    enabled: Boolean(token),
    refetchInterval: 15_000,
    queryFn: async (): Promise<Agent[]> => {
      const response = await authFetch(`${config.API_URL}/agents`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      return (data.agents || []) as Agent[];
    },
  });
}

/** The chatting agent: the saved choice when it still exists, else the first. */
export function useSelectedAgent(): Agent | null {
  const { data: agents } = useAgents();
  const id = useSelectedAgentId((state) => state.id);
  if (!agents?.length) return null;
  return agents.find((agent) => agent.id === id) ?? agents[0];
}

export function useRefreshAgents() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["agents"] });
}
