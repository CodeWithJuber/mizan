export const CHAT_INPUT_LIMIT = 50_000;

export type RunPhase = "accepted" | "context_preparation" | "queued" | "agent_execution" | "delivery";
export interface ChatRun {
  request_id: string;
  message_id?: string;
  session_id: string;
  status: string;
  phase?: RunPhase;
  elapsed_ms?: number;
  provider_attempt_count?: number;
}
export interface ChatRunState {
  state: "active" | "terminal" | "unknown" | "idle";
  request: ChatRun | null;
  history_saved: boolean | null;
}
export interface ChatRecoveryState {
  sessionId: string;
  requestId?: string;
  originRequestId?: string;
  state: ChatRunState["state"] | "checking";
  request?: ChatRun | null;
  checkedAt?: number;
  historySaved?: boolean | null;
  message?: string;
}

const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
export const phaseLabel = (phase?: string): string => ({
  accepted: "Request accepted",
  context_preparation: "Preparing conversation context",
  queued: "Waiting for the agent",
  agent_execution: "Agent is working",
  delivery: "Saving and delivering the reply",
  receiving: "Receiving the reply",
}[phase ?? ""] ?? "Waiting for a response");

export function parseChatRun(value: unknown, sessionId: string): ChatRun | null {
  if (!object(value) || value.session_id !== sessionId ||
      typeof value.request_id !== "string" || !value.request_id || value.request_id.length > 100 ||
      typeof value.status !== "string") return null;
  const phase = ["accepted", "context_preparation", "queued", "agent_execution", "delivery"].includes(String(value.phase))
    ? value.phase as RunPhase : undefined;
  return {
    request_id: value.request_id, session_id: sessionId, status: value.status,
    message_id: typeof value.message_id === "string" ? value.message_id : undefined,
    phase,
    elapsed_ms: typeof value.elapsed_ms === "number" && Number.isFinite(value.elapsed_ms) && value.elapsed_ms >= 0
      ? value.elapsed_ms : undefined,
    provider_attempt_count: typeof value.provider_attempt_count === "number" && Number.isSafeInteger(value.provider_attempt_count) && value.provider_attempt_count >= 0
      ? value.provider_attempt_count : undefined,
  };
}

export function parseRunState(value: unknown, sessionId: string): ChatRunState {
  if (!object(value) || !["active", "terminal", "unknown", "idle"].includes(String(value.state)))
    throw new Error("The server did not return a valid run status.");
  const request = value.request === null ? null : parseChatRun(value.request, sessionId);
  if ((value.request != null && !request) || (value.state === "active" && !request))
    throw new Error("Run status did not match this conversation.");
  const history_saved = typeof value.history_saved === "boolean" ? value.history_saved : null;
  // A terminal receipt without confirmed history cannot establish safe recovery.
  const state = value.state === "terminal" && (!request || history_saved === null)
    ? "unknown" : value.state as ChatRunState["state"];
  if (state === "idle" && request) throw new Error("Idle run status contained an unexpected request.");
  return { state, request, history_saved };
}

export function recoveryBlocksSend(state: ChatRecoveryState | null, sessionId: string): boolean {
  return state?.sessionId === sessionId && ["checking", "active", "unknown"].includes(state.state);
}

export function canDiscardRecoveredDraft(state: ChatRunState): boolean {
  return state.state === "terminal" && state.history_saved === true && state.request !== null;
}

export function chatFailureNeedsRecovery(event: Record<string, unknown>): boolean {
  const code = String(event.code);
  // Capacity rejection is definite non-execution, not an uncertain active run.
  if (["chat_capacity", "chat_capacity_reached"].includes(code)) return false;
  return event.history_saved === false || [
    "chat_transport_error", "chat_stream_active", "chat_request_conflict",
    "request_already_submitted", "history_save_failed", "delivery_stopped",
    "stream_failed", "provider_timeout", "chat_run_timeout",
  ].includes(code);
}

/** All recovery operations are GETs. An uncertain POST is never repeated. */
export async function recoverChatRun(options: {
  sessionId: string;
  readState: () => Promise<Response>;
  readHistory: () => Promise<boolean>;
}): Promise<ChatRunState> {
  const response = await options.readState();
  if (!response.ok) throw new Error("Run status is unavailable. Refresh to check again.");
  const state = parseRunState(await response.json(), options.sessionId);
  const historyRead = await options.readHistory();
  if (!historyRead && state.state !== "active")
    return { ...state, state: "unknown" };
  return state;
}
