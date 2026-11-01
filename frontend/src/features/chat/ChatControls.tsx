/**
 * Chat controls under the thread: what the person allowed "always" in this chat (each
 * can be taken back), and the button that runs a plan MIZAN proposed in plan mode.
 */
import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { config } from "../../config";
import { authFetch } from "../../utils/authFetch";
import { addToast } from "../../components/Toast";
import { savePermissionMode } from "../../components/PermissionModeSwitch";
import { allowedLabel } from "../../utils/agentActivity";
import { useChatActions, useChatState } from "./ChatProvider";

interface Allowed {
  tool: string;
  created?: string;
}

const alwaysKey = (sessionId: string) => ["chat-always", sessionId] as const;

/** The chat's "always" grants; refreshed when the person answers a prompt with Always. */
export function useAllowedAlways() {
  const { sessionId, activity } = useChatState();
  const queryClient = useQueryClient();
  const granted = activity.approvals.filter((approval) => approval.decision === "always").length;
  const query = useQuery({
    queryKey: alwaysKey(sessionId),
    enabled: Boolean(sessionId),
    staleTime: 30_000,
    retry: false,
    queryFn: async () => {
      const response = await authFetch(`${config.API_URL}/chat/${encodeURIComponent(sessionId)}/always`);
      if (!response.ok) return [] as Allowed[];
      const body = await response.json().catch(() => ({}));
      return (Array.isArray(body.always) ? body.always : []) as Allowed[];
    },
  });
  useEffect(() => {
    if (granted) void queryClient.invalidateQueries({ queryKey: alwaysKey(sessionId) });
  }, [granted, queryClient, sessionId]);

  const revoke = async (key: string) => {
    const response = await authFetch(
      `${config.API_URL}/chat/${encodeURIComponent(sessionId)}/always/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    );
    if (!response.ok && response.status !== 404) {
      addToast({ type: "error", title: "Could not take it back", description: `The server answered ${response.status}.` });
      return;
    }
    queryClient.setQueryData<Allowed[]>(alwaysKey(sessionId), (items = []) => items.filter((item) => item.tool !== key));
    addToast({ type: "info", title: `MIZAN asks again before: ${allowedLabel(key)}` });
  };
  return { allowed: query.data ?? [], revoke };
}

/**
 * After a plan-mode answer about the chat's project: run it. The run leaves plan mode
 * (edits allowed, everything else still asks), and the server is told by the button,
 * never by the words, that the plan was approved.
 */
export function PlanApproval() {
  const { messages, streaming, workspaceId, permissionMode } = useChatState();
  const actions = useChatActions();
  const last = messages[messages.length - 1];
  const asked = [...messages].reverse().find((message) => message.role === "user");
  if (streaming || !workspaceId || !last || last.role !== "assistant" || last.error || asked?.mode !== "plan") {
    return null;
  }
  const run = () => {
    const mode = permissionMode === "plan" ? "auto_edits" : permissionMode;
    if (permissionMode === "plan") {
      savePermissionMode(mode);
      actions.setPermissionMode(mode);
    }
    void actions.sendMessage("Run the approved plan", { planApproved: true, permissionMode: mode });
  };
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 rounded-xl border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
      <CheckCheck className="size-4 shrink-0 text-brand" />
      <span className="min-w-0 flex-1 text-muted-foreground">
        This is a plan: nothing in the project has changed yet.
      </span>
      <Button size="sm" onClick={run}>
        <Play /> Approve plan and run
      </Button>
    </div>
  );
}
