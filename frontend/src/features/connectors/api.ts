/** Server state for the connectors page: the list, presets, registry, and each connector's extras. */
import { useCallback, useMemo } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, useApi } from "../../hooks/useApi";
import { useAuth } from "../../app/auth";
import {
  type Capabilities, type Connector, type ConnectorTool, type ToolPolicy,
  normalizeCapabilities, normalizeConnector, normalizePreset, normalizePrompts, normalizeRegistryServer,
  normalizeResources, normalizeTest, usableTools,
} from "./types";

export const CONNECTORS_KEY = ["connectors"] as const;

export interface ConnectorList {
  connectors: Connector[];
  capabilities: Capabilities;
}

const rows = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

/** A reply that is a connector (most actions answer with the connector as it is now). */
const isConnector = (value: Record<string, unknown>) => typeof value.id === "string" && Array.isArray(value.tools);

export const notFound = (problem: unknown) =>
  problem instanceof ApiError && (problem.status === 404 || problem.status === 405);

export function useConnectorList() {
  const api = useApi();
  const { token, revision } = useAuth();
  return useQuery({
    queryKey: [...CONNECTORS_KEY, "list", revision],
    enabled: Boolean(token),
    staleTime: 10_000,
    queryFn: async (): Promise<ConnectorList> => {
      const data = await api.get("/connectors");
      return {
        connectors: rows(data.connectors).map(normalizeConnector),
        capabilities: normalizeCapabilities(data.capabilities),
      };
    },
  });
}

export function usePresets() {
  const api = useApi();
  return useQuery({
    queryKey: [...CONNECTORS_KEY, "presets"],
    staleTime: 60 * 60_000,
    queryFn: async () => {
      try {
        return rows((await api.get("/connectors/presets")).presets).map(normalizePreset).filter((preset) => preset.id);
      } catch (problem) {
        // A server without presets: the gallery says so instead of failing.
        if (notFound(problem)) return [];
        throw problem;
      }
    },
  });
}

export function useRegistry(search: string) {
  const api = useApi();
  return useInfiniteQuery({
    queryKey: [...CONNECTORS_KEY, "registry", search],
    staleTime: 10 * 60_000,
    initialPageParam: "",
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams({ search, limit: "30", ...(pageParam ? { cursor: pageParam } : {}) });
      const data = await api.get(`/connectors/registry?${params}`);
      return {
        servers: rows(data.servers).map(normalizeRegistryServer),
        next: typeof data.next_cursor === "string" && data.next_cursor ? data.next_cursor : null,
      };
    },
    getNextPageParam: (last) => last.next,
  });
}

export function useResources(id: string, enabled: boolean) {
  const api = useApi();
  return useQuery({
    queryKey: [...CONNECTORS_KEY, id, "resources"],
    enabled,
    queryFn: async () => normalizeResources(await api.get(`/connectors/${id}/resources`)),
  });
}

export function usePrompts(id: string, enabled: boolean) {
  const api = useApi();
  return useQuery({
    queryKey: [...CONNECTORS_KEY, id, "prompts"],
    enabled,
    queryFn: async () => normalizePrompts(await api.get(`/connectors/${id}/prompts`)),
  });
}

export function useLogs(id: string, enabled: boolean) {
  const api = useApi();
  return useQuery({
    queryKey: [...CONNECTORS_KEY, id, "logs"],
    enabled,
    staleTime: 0,
    queryFn: async () => rows((await api.get(`/connectors/${id}/logs`)).lines).filter((line): line is string => typeof line === "string"),
  });
}

function withTools(connector: Connector, tools: ConnectorTool[]): Connector {
  return {
    ...connector,
    tools,
    counts: {
      total: tools.length,
      enabled: usableTools(tools),
      held: tools.filter((tool) => tool.held).length,
      new: tools.filter((tool) => tool.new).length,
    },
  };
}

/** Every action on connectors; each keeps the cached list in step with the server's answer. */
export function useConnectorActions() {
  const api = useApi();
  const queryClient = useQueryClient();

  const put = useCallback((connector: Connector) => {
    queryClient.setQueriesData<ConnectorList>({ queryKey: [...CONNECTORS_KEY, "list"] }, (old) => old && ({
      ...old,
      connectors: old.connectors.some((item) => item.id === connector.id)
        ? old.connectors.map((item) => (item.id === connector.id ? connector : item))
        : [...old.connectors, connector],
    }));
  }, [queryClient]);

  const drop = useCallback((id: string) => {
    queryClient.setQueriesData<ConnectorList>({ queryKey: [...CONNECTORS_KEY, "list"] }, (old) => old && ({
      ...old,
      connectors: old.connectors.filter((item) => item.id !== id),
    }));
  }, [queryClient]);

  const refresh = useCallback(() => queryClient.invalidateQueries({ queryKey: [...CONNECTORS_KEY, "list"] }), [queryClient]);

  /** Keep the server's answer when it is a connector, else apply `local` to the cached one. */
  const settle = useCallback((data: Record<string, unknown>, connector: Connector, local: (c: Connector) => Connector) => {
    const next = isConnector(data) ? normalizeConnector(data) : local(connector);
    put(next);
    return next;
  }, [put]);

  return useMemo(() => ({
    put,
    refresh,
    get: async (id: string) => {
      const next = normalizeConnector(await api.get(`/connectors/${id}`));
      put(next);
      return next;
    },
    create: async (body: Record<string, unknown>) => {
      const created = normalizeConnector(await api.post("/connectors", body));
      put(created);
      return created;
    },
    update: async (connector: Connector, body: Record<string, unknown>) => {
      const data = await api.patch(`/connectors/${connector.id}`, body);
      return settle(data, connector, (c) => ({ ...c, ...(typeof body.enabled === "boolean" ? { enabled: body.enabled } : {}) }));
    },
    remove: async (connector: Connector) => {
      await api.del(`/connectors/${connector.id}`);
      drop(connector.id);
    },
    connect: async (connector: Connector) => {
      const data = await api.post(`/connectors/${connector.id}/connect`);
      if (data.connector && typeof data.connector === "object") put(normalizeConnector(data.connector));
      return {
        status: typeof data.status === "string" ? data.status : "",
        authorizationUrl: typeof data.authorization_url === "string" ? data.authorization_url : "",
      };
    },
    disconnect: async (connector: Connector) => {
      const data = await api.post(`/connectors/${connector.id}/disconnect`);
      return settle(data, connector, (c) => ({ ...c, status: "disconnected" }));
    },
    signOut: async (connector: Connector) => {
      await api.post(`/connectors/${connector.id}/signout`);
      void refresh();
    },
    test: async (connector: Connector) => {
      const result = normalizeTest(await api.post(`/connectors/${connector.id}/test`));
      void refresh();
      return result;
    },
    oauthStatus: (connector: Connector) => api.get(`/connectors/${connector.id}/oauth/status`),
    trust: async (connector: Connector, tool: string) => {
      const data = await api.post(`/connectors/${connector.id}/tools/trust`, { tool });
      return settle(data, connector, (c) => withTools(c, c.tools.map((t) => (t.name === tool ? { ...t, held: false, held_reason: null, previous: null } : t))));
    },
    policy: async (connector: Connector, tool: string, policy: ToolPolicy) => {
      const data = await api.post(`/connectors/${connector.id}/tools/policy`, { tool, policy });
      return settle(data, connector, (c) => withTools(c, c.tools.map((t) => (t.name === tool ? { ...t, policy, enabled: policy !== "never" } : t))));
    },
    ack: async (connector: Connector, tools: string[]) => {
      const data = await api.post(`/connectors/${connector.id}/tools/ack`, { tools });
      const seen = new Set(tools);
      return settle(data, connector, (c) => withTools(c, c.tools.map((t) => (seen.has(t.name) ? { ...t, new: false } : t))));
    },
  }), [api, put, drop, refresh, settle]);
}

export type ConnectorActions = ReturnType<typeof useConnectorActions>;
