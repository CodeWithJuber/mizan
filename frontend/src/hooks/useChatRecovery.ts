import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "../utils/authFetch";
import { config } from "../config";
import { canDiscardRecoveredDraft, recoverChatRun, recoveryBlocksSend, type ChatRecoveryState } from "../utils/chatRecovery.ts";

export function useChatRecovery(options: {
  sessionId: string;
  authRevision: number;
  readHistory: (sessionId: string) => Promise<boolean>;
  onResolved: (sessionId: string, requestId?: string) => void;
}) {
  const [state, setState] = useState<ChatRecoveryState | null>(null);
  const stateRef = useRef(state);
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const previousScope = useRef({ sessionId: options.sessionId, authRevision: options.authRevision });
  const update = useCallback((next: ChatRecoveryState | null) => { stateRef.current = next; setState(next); }, []);
  const reset = useCallback(() => {
    sequence.current++;
    controller.current?.abort();
    update(null);
  }, [update]);
  useEffect(() => {
    const changedOwner = previousScope.current.authRevision !== options.authRevision;
    previousScope.current = { sessionId: options.sessionId, authRevision: options.authRevision };
    // Cache hydration may already have begun a check for the newly selected
    // session before this effect runs. Do not abort that new scoped check.
    if (changedOwner || stateRef.current?.sessionId !== options.sessionId) reset();
  }, [options.sessionId, options.authRevision, reset]);
  useEffect(() => () => { sequence.current++; controller.current?.abort(); }, []);

  const refresh = useCallback(async (requestId?: string, originRequestId?: string, targetSessionId?: string) => {
    const sessionId = targetSessionId ?? optionsRef.current.sessionId;
    const token = localStorage.getItem("mizan_token");
    if (!token) return;
    const target = requestId ?? (stateRef.current?.sessionId === sessionId ? stateRef.current.requestId : undefined);
    const origin = originRequestId ?? (stateRef.current?.sessionId === sessionId ? stateRef.current.originRequestId : undefined) ?? target;
    const id = ++sequence.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    update({ ...stateRef.current, sessionId, requestId: target, originRequestId: origin, state: "checking", message: undefined });
    const current = () => !abort.signal.aborted && sequence.current === id &&
      sessionId === optionsRef.current.sessionId && token === localStorage.getItem("mizan_token");
    const deadline = setTimeout(() => {
      if (!current()) return;
      update({ sessionId, requestId: target, originRequestId: origin, state: "unknown",
        message: "The status check timed out. The model request was not retried; refresh to check again." });
      sequence.current++;
      abort.abort();
    }, 15_000);
    try {
      const result = await recoverChatRun({
        sessionId,
        readState: () => authFetch(`${config.API_URL}/chat/${encodeURIComponent(sessionId)}/run-state${target ? `?request_id=${encodeURIComponent(target)}` : ""}`, { signal: abort.signal }),
        readHistory: () => current() ? optionsRef.current.readHistory(sessionId) : Promise.resolve(false),
      });
      if (!current()) return;
      update({ sessionId, requestId: result.request?.request_id ?? target, originRequestId: origin, request: result.request,
        state: result.state, historySaved: result.history_saved, checkedAt: Date.now() });
      // A local run can end without saving its reply. Keep the browser draft
      // until primary history is confirmed; unlocking Send is independent.
      if (canDiscardRecoveredDraft(result))
        optionsRef.current.onResolved(sessionId, result.request!.request_id);
    } catch (error) {
      if (current()) update({ sessionId, requestId: target, originRequestId: origin, state: "unknown",
        message: error instanceof Error ? error.message : "Run status is unavailable. Refresh to check again." });
    } finally { clearTimeout(deadline); }
  }, [update]);

  // Poll only a confirmed active run. Unknown outcomes stay visible for manual
  // refresh; failed GETs never unlock Send or cause another POST.
  useEffect(() => {
    if (state?.state !== "active") return;
    const timer = setTimeout(() => void refresh(), 5000);
    return () => clearTimeout(timer);
  }, [state, refresh]);

  const begin = useCallback((requestId?: string, originRequestId?: string, sessionId?: string) => {
    void refresh(requestId, originRequestId, sessionId);
  }, [refresh]);
  const isBlocked = useCallback(() => recoveryBlocksSend(stateRef.current, optionsRef.current.sessionId), []);
  const blocked = recoveryBlocksSend(state, options.sessionId);
  return { state: state?.sessionId === options.sessionId ? state : null, blocked, isBlocked, begin, refresh, reset };
}
