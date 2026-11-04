/**
 * The chat: one conversation at a time, its messages, the live run and how a
 * message is sent, stopped, continued and recovered after a dropped
 * connection or a deploy.
 *
 * Moved out of App.tsx unchanged in behaviour. It is mounted once by the root
 * layout, so a reply keeps streaming while the person opens another page.
 * The streaming text itself lives in `liveStore` and the shell reads
 * `useChatSummary`, so neither re-renders on every chunk.
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ChatMessage, CognitiveMetadata, PerceptionResult, ProviderStatus, MessageUsageMeta,
  Artifact, ArtifactKind, ArtifactWsPayload,
} from "../../types";
import type { ThinkingTrace, ThinkingStep } from "../../types/ruh";
import { config } from "../../config";
import { useApi } from "../../hooks/useApi";
import { authFetch } from "../../utils/authFetch";
import { runChatRequest } from "../../utils/chatRequest.ts";
import { CHAT_INPUT_LIMIT, chatFailureNeedsRecovery, parseChatRun } from "../../utils/chatRecovery.ts";
import { useChatRecovery } from "../../hooks/useChatRecovery.ts";
import { keptArtifacts, keptImages, chatFailureFields, messageUsage, restoredMessageFields } from "../../utils/chatFailure.ts";
import { checkLine, isReceipt, removedLine } from "../../utils/mahw.ts";
import type { AgentMode } from "../../components/ModeSwitcher";
import type { ApprovalDecision } from "../../components/AgentActivity";
import { loadPermissionMode } from "../../components/PermissionModeSwitch";
import {
  ACTIVITY_EVENTS, emptyActivity, hasActivity, reduceActivity,
  type AgentActivity, type PermissionMode,
} from "../../utils/agentActivity";
import {
  exportMarkdown, exportText, exportJSON, buildExportFilename, downloadExport, type ExportFormatId,
} from "../../utils/exportChat";
import { StreamBuffer } from "../../utils/streaming";
import { timeZoneField } from "../../utils/timezone.ts";
import { chatWorkspace, clearChatWorkspaces, migrateLegacyWorkspace, setChatWorkspace } from "../../utils/chatWorkspaces";
import {
  fetchChatHistoryWithRetry, hydrateCachedMessages, createHistoryLoadTracker, mergeHistoryMessages,
} from "../../utils/historySync";
import {
  cacheMessages, readCachedMessages, cacheChatDraft, cacheChatDraftNow, readCachedChatDrafts, clearCachedChatDraft,
} from "../../utils/sessionCache";
import { addToast } from "../../components/Toast";
import { confirmDialog } from "../../components/ui/confirm";
import { useAuth } from "../../app/auth";
import { setSocketHandlers, sendSocket, useSocketStatus } from "../../realtime/socket";
import { addTerminalLine, useTerminal } from "../../realtime/terminal";
import { useRefreshAgents, useSelectedAgent } from "../agents/agents";
import { setLiveText, useChatSummary } from "./liveStore";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] || result);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// The backend chat session survives a page refresh via localStorage.
// Key renamed from "mizan_session_id" (legacy, still read as fallback).
const CHAT_SESSION_STORAGE_KEY = "mizan_chat_session_id";
const LEGACY_CHAT_SESSION_KEY = "mizan_session_id";

export function readStoredChatSessionId(): string | null {
  try {
    return localStorage.getItem(CHAT_SESSION_STORAGE_KEY) || localStorage.getItem(LEGACY_CHAT_SESSION_KEY);
  } catch {
    return null;
  }
}

const newSessionId = () => `session_${crypto.randomUUID()}`;

/** A chat opened by its link (/chat/<id>) starts there, else the last chat. */
function initialSessionId(): string {
  const match = /^\/chat\/([^/]+)\/?$/.exec(window.location.pathname);
  if (match) {
    try {
      return decodeURIComponent(match[1]);
    } catch {
      /* fall through */
    }
  }
  return readStoredChatSessionId() || newSessionId();
}

// Length-limited replies continue only when the user chooses Continue.
const CONTINUE_PROMPT = "Continue from exactly where you stopped. Do not repeat what you already wrote.";

export const CHAT_SESSIONS_KEY = ["chat-sessions"] as const;

export interface RunProgress {
  startedAt: number;
  phase?: string;
  /** Deep research stage and spend, or "waiting for the model's full answer". */
  note?: string;
}

export interface ChatState {
  sessionId: string;
  messages: ChatMessage[];
  input: string;
  streaming: boolean;
  /** No text yet: the model is still working on the first token. */
  awaitingText: boolean;
  activity: AgentActivity;
  thinkingTraces: Record<string, ThinkingTrace>;
  activeThinkingId: string | null;
  runProgress: RunProgress | null;
  agentMode: AgentMode;
  deepResearchConfirmed: boolean;
  permissionMode: PermissionMode;
  chatModelOverride: string;
  attachedFiles: File[];
  /** The project this chat works on ("" for none); the server's binding wins. */
  workspaceId: string;
  /** A dev server MIZAN or the model started in this chat's project. */
  livePreview: LivePreview | null;
  artifacts: Artifact[];
  showArtifacts: boolean;
  debugAllowed: boolean;
  debugOn: boolean;
  debugPrompt: string | undefined;
  historyLoadError: boolean;
  historyLoading: boolean;
  hasOlderHistory: boolean;
  olderHistoryLoading: boolean;
  draftStorageFailed: boolean;
  truncatedContinue: { messageId: string } | null;
  recovery: ReturnType<typeof useChatRecovery>;
}

export interface LivePreview {
  workspaceId: string;
  port: number;
  url: string;
}

/** What a button sends with a message; never read from its words. */
export interface SendOptions {
  /** "Approve plan and run": carry out the plan of the previous answer. */
  planApproved?: boolean;
  /** "Fix with MIZAN": an error the project showed. */
  fix?: { source: "preview" | "server" | "terminal"; error: string };
  /** The mode for this message only (the buttons need one that may change files). */
  permissionMode?: PermissionMode;
}

export interface ChatActions {
  setInput: (value: string | ((previous: string) => string)) => void;
  sendMessage: (contentOverride?: string, options?: SendOptions) => Promise<void>;
  stopGeneration: () => void;
  continueAnswer: () => void;
  dismissContinue: () => void;
  decideApproval: (approvalId: string, decision: ApprovalDecision) => Promise<void>;
  startNewSession: () => void;
  switchSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<boolean>;
  reloadHistory: () => void;
  loadOlderHistory: () => Promise<void>;
  exportChat: (format: ExportFormatId) => Promise<void>;
  setAgentMode: (mode: AgentMode) => void;
  setDeepResearchConfirmed: (confirmed: boolean) => void;
  setPermissionMode: (mode: PermissionMode) => void;
  setChatModelOverride: (model: string) => void;
  setAttachedFiles: (files: File[] | ((previous: File[]) => File[])) => void;
  selectWorkspace: (id: string) => void;
  setShowArtifacts: (show: boolean) => void;
  addArtifact: (artifact: Artifact) => void;
  toggleDebug: () => void;
  setDebugPrompt: (prompt: string | undefined) => void;
  stopRecoveredRun: () => void;
  /** The composer registers its textarea so others (IDE "Ask agent", suggestions) can focus it. */
  registerComposer: (element: HTMLTextAreaElement | null) => void;
  focusComposer: () => void;
}

const ChatStateContext = createContext<ChatState | null>(null);
const ChatActionsContext = createContext<ChatActions | null>(null);

export function useChatState(): ChatState {
  const value = useContext(ChatStateContext);
  if (!value) throw new Error("useChatState outside ChatProvider");
  return value;
}

export function useChatActions(): ChatActions {
  const value = useContext(ChatActionsContext);
  if (!value) throw new Error("useChatActions outside ChatProvider");
  return value;
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const authRevision = useAuth((state) => state.revision);
  const selectedAgent = useSelectedAgent();
  const refreshAgents = useRefreshAgents();
  const wsStatus = useSocketStatus((state) => state.status);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  // "single" = the default path; "deep_research" = planner→workers→aggregator→verifier (gated + budgeted).
  const [agentMode, setAgentMode] = useState<AgentMode>("single");
  const [deepResearchConfirmed, setDeepResearchConfirmed] = useState(false);
  const [awaitingText, setAwaitingText] = useState(false);
  const [sessionId, setSessionId] = useState<string>(initialSessionId);
  // Live tool calls, plan and approval prompts of the current reply.
  const [activity, setActivity] = useState<AgentActivity>(emptyActivity);
  const activityRef = useRef<AgentActivity>(emptyActivity());
  const [permissionMode, setPermissionMode] = useState<PermissionMode>(loadPermissionMode);
  const applyActivity = useCallback((event: Record<string, unknown>) => {
    const next = reduceActivity(activityRef.current, event);
    if (next !== activityRef.current) {
      activityRef.current = next;
      setActivity(next);
    }
  }, []);
  const resetActivity = useCallback(() => {
    activityRef.current = emptyActivity();
    setActivity(activityRef.current);
  }, []);
  const decideApproval = useCallback(async (approvalId: string, decision: ApprovalDecision) => {
    const response = await authFetch(`${config.API_URL}/chat/approvals/${approvalId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    if (!response.ok) applyActivity({ type: "approval_resolved", approval_id: approvalId, decision: "expired" });
  }, [applyActivity]);
  const [thinkingTraces, setThinkingTraces] = useState<Record<string, ThinkingTrace>>({});
  const [activeThinkingId, setActiveThinkingId] = useState<string | null>(null);
  const [chatModelOverride, setChatModelOverride] = useState("");
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  // Each chat owns its project: a new chat starts with none.
  const [workspaceId, setWorkspaceId] = useState(() => {
    migrateLegacyWorkspace(sessionId);
    return chatWorkspace(sessionId);
  });
  const [livePreview, setLivePreview] = useState<LivePreview | null>(null);
  /** The server said which project a chat works on: it wins over the browser's map. */
  const bindChatWorkspace = useCallback((sid: string, id: string) => {
    setChatWorkspace(sid, id);
    if (sid === sessionIdRef.current) setWorkspaceId(id);
  }, []);
  /** The chat a stream event belongs to (the person may have opened another since). */
  const eventSession = (data: Record<string, unknown>) =>
    typeof data.session_id === "string" && data.session_id ? data.session_id : sessionIdRef.current;
  const selectWorkspace = useCallback((id: string) => {
    const sid = sessionIdRef.current;
    setWorkspaceId(id);
    setChatWorkspace(sid, id);
    setLivePreview(null);
    // A chat the server already has keeps its project there (a new chat is bound by
    // its first message), so removing the project also stops later messages using it.
    if (!sid || !useChatSummary.getState().hasMessages) return;
    void authFetch(`${config.API_URL}/chat/${encodeURIComponent(sid)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_id: id || null }),
    }).catch(() => undefined);
  }, []);

  // Provider check before sending: guide the person to settings when none is configured.
  const { data: providerStatus } = useQuery({
    queryKey: ["providers", authRevision],
    staleTime: 5 * 60_000,
    queryFn: async () => (await api.get("/providers")) as unknown as ProviderStatus,
  });

  // Debug mode: compare one message with the base model alone (Muqabala).
  const { data: debugAllowed = false } = useQuery({
    queryKey: ["debug-status", authRevision],
    staleTime: 5 * 60_000,
    queryFn: async () => Boolean((await api.get("/debug/status")).enabled),
  });
  const [debugOn, setDebugOn] = useState(() => {
    try {
      return localStorage.getItem("mizan_debug_mode") === "on";
    } catch {
      return false;
    }
  });
  const [debugPrompt, setDebugPrompt] = useState<string | undefined>();
  const toggleDebug = useCallback(() => {
    setDebugOn((previous) => {
      const next = !previous;
      try {
        localStorage.setItem("mizan_debug_mode", next ? "on" : "off");
      } catch {
        // A per-browser convenience only.
      }
      return next;
    });
  }, []);

  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  // ===== Session hardening + streaming refs =====
  const streamBufferRef = useRef<StreamBuffer | null>(null);
  const sendControllerRef = useRef<AbortController | null>(null);
  const activeMessageIdRef = useRef<string>("");
  const activeRequestIdRef = useRef<string>("");
  const chatEventHandlerRef = useRef<(data: Record<string, unknown>) => void>(() => {});
  const stopFallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionIdRef = useRef<string>(sessionId);
  const startNewSessionRef = useRef<(() => void) | null>(null);
  const resyncRef = useRef<(() => void) | null>(null);
  // Bounded continuations when a stream ends with finish_reason=length.
  const continuationRef = useRef(0);
  const [historyLoadError, setHistoryLoadError] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  // Older server messages exist beyond the loaded page (paged on demand).
  const [hasOlderHistory, setHasOlderHistory] = useState(false);
  const [olderHistoryLoading, setOlderHistoryLoading] = useState(false);
  const [historyLoads] = useState(() => createHistoryLoadTracker(setHistoryLoading));
  const [runProgress, setRunProgress] = useState<RunProgress | null>(null);
  const [draftStorageFailed, setDraftStorageFailed] = useState(false);
  const draftStorageFailures = useRef(new Set<string>());
  const recoveryHistoryRef = useRef<(sid: string) => Promise<boolean>>(async () => false);
  const activeDraftRef = useRef<{
    sessionId: string; ownerToken: string; message: ChatMessage; live: boolean; lastSaved?: string; pendingSave?: string;
  } | null>(null);
  const pendingInputRef = useRef<{ requestId: string; content: string } | null>(null);
  const recovery = useChatRecovery({
    sessionId, authRevision,
    readHistory: (sid) => recoveryHistoryRef.current(sid),
    onResolved: (sid, requestId) => {
      const token = localStorage.getItem("mizan_token");
      if (token && requestId) void clearCachedChatDraft(sid, requestId, token);
      if (requestId) draftStorageFailures.current.delete(`${sid}:${requestId}`);
      setDraftStorageFailed([...draftStorageFailures.current].some((key) => key.startsWith(`${sessionIdRef.current}:`)));
      if (activeDraftRef.current?.sessionId === sid && activeDraftRef.current.message.requestId === requestId)
        activeDraftRef.current = null;
    },
  });
  const persistActiveDraft = useCallback((immediate = false) => {
    const draft = activeDraftRef.current;
    if (!draft || draft.ownerToken !== localStorage.getItem("mizan_token")) return;
    if (draft.live) draft.message = {
      ...draft.message,
      content: streamBufferRef.current?.getText() ?? draft.message.content,
      messageId: activeMessageIdRef.current || draft.message.messageId,
    };
    const signature = `${draft.message.content.length}:${draft.message.messageId ?? ""}:${draft.message.error?.code ?? ""}:${draft.message.stopped ?? false}`;
    const storageResult = (saved: boolean) => {
      if (activeDraftRef.current !== draft || draft.ownerToken !== localStorage.getItem("mizan_token")) return;
      const key = `${draft.sessionId}:${draft.message.requestId}`;
      if (saved) draftStorageFailures.current.delete(key);
      else draftStorageFailures.current.add(key);
      setDraftStorageFailed([...draftStorageFailures.current].some((entry) => entry.startsWith(`${sessionIdRef.current}:`)));
    };
    if (immediate) {
      const saved = cacheChatDraftNow(draft.sessionId, draft.message, draft.ownerToken);
      if (saved) draft.lastSaved = signature;
      storageResult(saved);
    } else if (signature !== draft.lastSaved && signature !== draft.pendingSave) {
      draft.pendingSave = signature;
      void cacheChatDraft(draft.sessionId, draft.message, draft.ownerToken).then((saved) => {
        if (draft.pendingSave === signature) { draft.pendingSave = undefined; storageResult(saved); }
        if (saved) draft.lastSaved = signature;
      });
    }
  }, []);
  useEffect(() => {
    const timer = setInterval(() => { if (activeDraftRef.current?.live) persistActiveDraft(); }, 500);
    const save = () => persistActiveDraft(true);
    window.addEventListener("pagehide", save);
    return () => { save(); clearInterval(timer); window.removeEventListener("pagehide", save); };
  }, [persistActiveDraft]);

  const refreshSessions = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: CHAT_SESSIONS_KEY });
  }, [queryClient]);

  // A different person signed in (or out): nothing of the previous one stays.
  const firstRevision = useRef(authRevision);
  useEffect(() => {
    if (authRevision === firstRevision.current) return;
    historyLoads.reset();
    sendControllerRef.current?.abort();
    activeRequestIdRef.current = "";
    activeMessageIdRef.current = "";
    activeDraftRef.current = null;
    draftStorageFailures.current.clear();
    setDraftStorageFailed(false);
    setRunProgress(null);
    recovery.reset();
    streamBufferRef.current?.discard();
    streamBufferRef.current = null;
    setLiveText("");
    setMessages([]);
    setArtifacts([]);
    setShowArtifacts(false);
    setAttachedFiles([]);
    setWorkspaceId("");
    setLivePreview(null);
    clearChatWorkspaces();
    setStreaming(false);
    setAwaitingText(false);
    setActiveThinkingId(null);
    setThinkingTraces({});
    useTerminal.getState().clear();
    setHistoryLoadError(false);
    const id = newSessionId();
    setSessionId(id);
    sessionIdRef.current = id;
    localStorage.removeItem(LEGACY_CHAT_SESSION_KEY);
    localStorage.setItem(CHAT_SESSION_STORAGE_KEY, id);
    queryClient.removeQueries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRevision]);

  // ===== streaming / stop helpers =====
  // Mirrors `streaming` for stable callbacks and timeouts.
  const streamingRef = useRef(false);
  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  const clearStopFallback = useCallback(() => {
    if (stopFallbackRef.current) {
      clearTimeout(stopFallbackRef.current);
      stopFallbackRef.current = null;
    }
  }, []);

  /**
   * Finalize the in-flight generation locally: discard the stream buffer,
   * settle UI state, and keep whatever text arrived as an assistant message
   * marked `stopped` — never silently dropped. Idempotent.
   */
  const finalizeStop = useCallback(
    (text: string, userRequested = false) => {
      if (!streamingRef.current) return;
      const requestId = activeRequestIdRef.current || activeDraftRef.current?.message.requestId;
      const messageId = activeMessageIdRef.current || activeDraftRef.current?.message.messageId;
      streamingRef.current = false;
      clearStopFallback();
      streamBufferRef.current?.discard();
      streamBufferRef.current = null;
      setLiveText("");
      setStreaming(false);
      setAwaitingText(false);
      setActiveThinkingId(null);
      sendControllerRef.current = null;
      activeMessageIdRef.current = "";
      activeRequestIdRef.current = "";
      setRunProgress(null);
      if (text || requestId) {
        const stoppedMsg: ChatMessage = {
          id: activeDraftRef.current?.message.id ?? Date.now(),
          role: "assistant",
          content: text,
          agent: selectedAgent?.name,
          ts: new Date().toLocaleTimeString(),
          requestId, messageId,
          activity: hasActivity(activityRef.current) ? activityRef.current : undefined,
          stopped: userRequested,
          interrupted: !userRequested,
          meta: { completion_status: "incomplete", task_verified: false, answer_delivered: false },
        };
        setMessages((prev) => [...prev, stoppedMsg]);
        if (activeDraftRef.current) {
          activeDraftRef.current.message = stoppedMsg;
          activeDraftRef.current.live = false;
          persistActiveDraft();
        }
      }
      if (requestId) recovery.begin(requestId, requestId);
      addTerminalLine(userRequested ? "Stop requested — checking the server run" : "Response interrupted — checking the server run", "warn");
    },
    [clearStopFallback, selectedAgent, persistActiveDraft, recovery.begin],
  );

  // When true, the next chat_complete extends the last assistant message
  // (same bubble) instead of appending a new one — used for continuations.
  const appendToLastRef = useRef(false);
  const [truncatedContinue, setTruncatedContinue] = useState<{ messageId: string } | null>(null);

  /** Send a "continue" request for a length-truncated answer (no user bubble). */
  const requestContinuation = useCallback(async () => {
    const sid = sessionIdRef.current;
    const token = localStorage.getItem("mizan_token");
    if (!sid || !token || streamingRef.current || recovery.isBlocked()) return;
    const controller = new AbortController();
    sendControllerRef.current = controller;
    appendToLastRef.current = true;
    streamBufferRef.current = new StreamBuffer(setLiveText);
    const requestId = crypto.randomUUID();
    activeRequestIdRef.current = requestId;
    activeMessageIdRef.current = "";
    activeDraftRef.current = { sessionId: sid, ownerToken: token, live: true, message: {
      id: -Date.now(), role: "assistant", content: "", ts: new Date().toLocaleTimeString(), requestId,
      agent: selectedAgent?.name, interrupted: true,
    } };
    persistActiveDraft();
    recovery.reset();
    setRunProgress({ startedAt: Date.now() });
    resetActivity();
    streamingRef.current = true;
    setStreaming(true);
    setAwaitingText(true);
    try {
      await runChatRequest({
        request: () => authFetch(`${config.API_URL}/chat/stream`, {
          method: "POST",
          signal: controller.signal,
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({
            session_id: sid,
            content: CONTINUE_PROMPT,
            agent_id: selectedAgent?.id,
            request_id: requestId,
            permission_mode: permissionMode,
            thinking: true,
            ...timeZoneField(),
            ...(workspaceId ? { workspace_id: workspaceId } : {}),
          }),
        }),
        sessionId: sid,
        requestId,
        signal: controller.signal,
        isCurrent: () => activeRequestIdRef.current === requestId && sessionIdRef.current === sid,
        onEvent: (event) => {
          activeMessageIdRef.current = (event.message_id as string) || activeMessageIdRef.current;
          chatEventHandlerRef.current(event);
        },
      });
    } finally {
      if (activeRequestIdRef.current === requestId && sessionIdRef.current === sid) {
        activeRequestIdRef.current = "";
        appendToLastRef.current = false;
        sendControllerRef.current = null;
        streamingRef.current = false;
        setStreaming(false);
        setAwaitingText(false);
      }
    }
  }, [selectedAgent, workspaceId, permissionMode, persistActiveDraft, recovery.isBlocked, recovery.reset, resetActivity]);

  /** Ask the server to stop this run, then close the stream. A dropped
   *  connection alone never stops a run: the server finishes and saves it. */
  const stopGeneration = useCallback(() => {
    const requestId = activeRequestIdRef.current;
    const sid = sessionIdRef.current;
    if (sid) {
      void authFetch(`${config.API_URL}/chat/${encodeURIComponent(sid)}/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestId ? { request_id: requestId } : {}),
      }).catch(() => undefined);
    }
    sendControllerRef.current?.abort();
    finalizeStop(streamBufferRef.current?.getText() ?? "", true);
  }, [finalizeStop]);

  const handleChatEvent = useCallback(
    (data: Record<string, unknown>) => {
      switch (data.type) {
        case "connected":
          addTerminalLine(`${data.message} — ${data.agents} agents online`, "gold");
          refreshAgents();
          break;
        case "stream":
        case "chat_stream":
          setAwaitingText(false);
          setRunProgress((current) => current ? { ...current, phase: "receiving" } : null);
          // Chunks are buffered; StreamBuffer flushes on animation frames, not per token.
          if (!streamBufferRef.current) streamBufferRef.current = new StreamBuffer(setLiveText);
          streamBufferRef.current.push(data.chunk as string);
          break;
        case "response":
          clearStopFallback();
          streamBufferRef.current?.finalize();
          streamBufferRef.current = null;
          sendControllerRef.current = null;
          activeMessageIdRef.current = "";
          setLiveText("");
          setStreaming(false);
          setAwaitingText(false);
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: "assistant" as const,
              content: data.content as string,
              agent: data.agent as string,
              ts: new Date().toLocaleTimeString(),
            },
          ]);
          addTerminalLine(`Response from ${data.agent}`, "info");
          setActiveThinkingId(null);
          break;
        case "chat_complete": {
          // A project MIZAN made for this chat is now the chat's project.
          if (typeof data.workspace_id === "string" && data.workspace_id) {
            bindChatWorkspace(eventSession(data), data.workspace_id);
          }
          const finishedDraft = activeDraftRef.current;
          if (finishedDraft && finishedDraft.message.requestId === data.request_id) {
            void clearCachedChatDraft(finishedDraft.sessionId, finishedDraft.message.requestId!, finishedDraft.ownerToken);
            draftStorageFailures.current.delete(`${finishedDraft.sessionId}:${finishedDraft.message.requestId}`);
            setDraftStorageFailed([...draftStorageFailures.current].some((key) => key.startsWith(`${sessionIdRef.current}:`)));
            activeDraftRef.current = null;
          }
          setRunProgress(null);
          // Flush the stream buffer (the final text may exceed what was flushed) and settle stop state.
          clearStopFallback();
          const buffered = streamBufferRef.current?.finalize() ?? "";
          streamBufferRef.current = null;
          sendControllerRef.current = null;
          activeMessageIdRef.current = "";
          setLiveText("");
          setStreaming(false);
          setAwaitingText(false);
          const messageId = (data.message_id as string) || `msg_${Date.now()}`;
          const serverTrace = data.thinking_trace as Record<string, unknown> | undefined;
          if (serverTrace) {
            setThinkingTraces((prev) => ({
              ...prev,
              [messageId]: {
                request_id: (serverTrace.request_id as string) || messageId,
                steps: (serverTrace.steps as ThinkingStep[]) || [],
                duration_ms: (serverTrace.duration_ms as number) || 0,
                avg_confidence: (serverTrace.avg_confidence as number) || 0,
              },
            }));
          }
          setActiveThinkingId(null);
          const completeContent = (data.response as string) || (data.content as string) || buffered;
          // The backend's observed usage block; absent fields mean "not reported" — never filled in.
          const usageMeta = messageUsage(data);
          const newAssistantMsg: ChatMessage = {
            id: Date.now(),
            role: "assistant" as const,
            content: completeContent,
            agent: data.agent as string,
            model: usageMeta?.model as string | undefined,
            ts: new Date().toLocaleTimeString(),
            cognitive: data.cognitive as CognitiveMetadata | undefined,
            thinkingMessageId: messageId,
            activity: hasActivity(activityRef.current) ? activityRef.current : undefined,
            requestId: typeof data.request_id === "string" ? data.request_id : undefined,
            messageId: typeof data.message_id === "string" ? data.message_id : undefined,
            images: keptImages(data.images),
            artifacts: keptArtifacts(data.artifacts),
            meta: usageMeta,
          };
          if (appendToLastRef.current) {
            // Continuation — extend the SAME bubble, never a new one.
            appendToLastRef.current = false;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, content: last.content + completeContent };
              } else {
                next.push(newAssistantMsg);
              }
              return next;
            });
          } else {
            setMessages((prev) => [...prev, newAssistantMsg]);
          }
          // A max_tokens cutoff is never shown as a finished answer: offer Continue.
          const usageInfo = (data.usage ?? {}) as { finish_reason?: string };
          const finishReason = (data.finish_reason as string) || usageInfo.finish_reason || "";
          if (finishReason === "length" || finishReason === "max_tokens") {
            setTruncatedContinue({ messageId });
            addToast({
              type: "warning",
              title: "Response reached its length limit",
              description: "Choose Continue to request the remaining answer.",
            });
          }
          addTerminalLine(`Response from ${data.agent}`, "info");
          refreshSessions();
          break;
        }
        case "chat_stopped": {
          // The server cancelled generation (our stop request). Prefer its full
          // partial text over the local buffer, which may miss tail tokens.
          const serverPartial = (data.response as string) || "";
          const bufferedText = streamBufferRef.current?.finalize() ?? "";
          streamBufferRef.current = null;
          finalizeStop(serverPartial || bufferedText);
          refreshSessions();
          break;
        }
        case "stop_ack": {
          // No active generation (already finished / unknown id): finalize now.
          if (data.cancelled === false) finalizeStop(streamBufferRef.current?.getText() ?? "");
          break;
        }
        case "status":
          if (typeof data.phase === "string")
            setRunProgress((current) => current ? { ...current, phase: data.phase as string } : null);
          else if (data.status === "accepted")
            setRunProgress((current) => current ? { ...current, phase: "accepted" } : null);
          if (data.streaming_mode === "buffered")
            setRunProgress((current) => current ? { ...current, note: "Waiting for the model's complete response…" } : null);
          break;
        case "typing":
          setAwaitingText(true);
          break;
        case "thinking": {
          const thinkMsgId = (data.message_id as string) || "current";
          setActiveThinkingId(thinkMsgId);
          setThinkingTraces((prev) => {
            const existing = prev[thinkMsgId] || { request_id: thinkMsgId, steps: [], duration_ms: 0, avg_confidence: 0 };
            const newStep: ThinkingStep = {
              id: `step_${Date.now()}_${existing.steps.length}`,
              phase: data.phase as ThinkingStep["phase"],
              content: data.content as string,
              confidence: (data.confidence as number) ?? 0,
              timestamp: Date.now() / 1000,
              metadata: data.metadata as Record<string, unknown> | undefined,
            };
            const steps = [...existing.steps, newStep];
            const avgConf = steps.reduce((sum, s) => sum + s.confidence, 0) / steps.length;
            return { ...prev, [thinkMsgId]: { ...existing, steps, avg_confidence: avgConf } };
          });
          break;
        }
        case "tool_start":
        case "tool_result":
        case "todo":
        case "approval_request":
        case "approval_resolved":
        case "skill":
          if (ACTIVITY_EVENTS.has(data.type as string)) applyActivity(data);
          break;
        case "tool_use":
          addTerminalLine(`Tool: ${data.tool_name as string}`, "info");
          break;
        case "workspace":
          // MIZAN made a project for this message: the chat works on it from now on.
          if (typeof data.workspace_id === "string" && data.workspace_id) {
            bindChatWorkspace(eventSession(data), data.workspace_id);
            if (data.created) addTerminalLine(`Project created: ${String(data.name ?? "")}`, "gold");
          }
          break;
        case "checkpoint": {
          // The project as it was before this message: "Rewind" goes back to it.
          const workspace = data.workspace_id;
          const id = data.checkpoint_id;
          if (typeof workspace === "string" && typeof id === "string" && !data.error) {
            setMessages((prev) => prev.map((message) =>
              message.role === "user" && message.requestId === data.request_id
                ? { ...message, checkpoint: { workspace_id: workspace, id } }
                : message));
          }
          break;
        }
        case "preview":
          if (typeof data.workspace_id === "string" && typeof data.preview_url === "string"
            && eventSession(data) === sessionIdRef.current) {
            setLivePreview({ workspaceId: data.workspace_id, port: Number(data.port) || 0, url: data.preview_url });
          }
          break;
        case "mode_progress": {
          // Live deep-research progress and cost meter.
          const stage = (data.stage as string) || "working";
          const cost = Number(data.cost_so_far || 0);
          setRunProgress((current) => ({
            startedAt: current?.startedAt ?? Date.now(),
            phase: current?.phase,
            note: `Deep research: ${stage}… (~$${cost.toFixed(4)} spent)`,
          }));
          break;
        }
        case "command_result": {
          setStreaming(false);
          setLiveText("");
          setAwaitingText(false);
          const cmdContent = (data.content as string) || (data.result as string) || "done";
          if ((data.command as string) === "/new") {
            startNewSessionRef.current?.();
          } else {
            setMessages((prev) => [
              ...prev,
              { id: Date.now(), role: "system" as const, content: cmdContent, agent: "system", ts: new Date().toLocaleTimeString() },
            ]);
          }
          addTerminalLine(`Command: ${cmdContent.substring(0, 60)}`, "gold");
          break;
        }
        case "error": {
          const draft = activeDraftRef.current;
          const partial = streamBufferRef.current?.finalize() ?? "";
          clearStopFallback();
          streamingRef.current = false;
          appendToLastRef.current = false;
          streamBufferRef.current = null;
          sendControllerRef.current = null;
          activeMessageIdRef.current = "";
          activeRequestIdRef.current = "";
          setStreaming(false);
          setLiveText("");
          setAwaitingText(false);
          setActiveThinkingId(null);
          setTruncatedContinue(null);
          setRunProgress(null);
          const failure = chatFailureFields(data, partial);
          addTerminalLine(`Error: ${failure.error?.message}`, "error");
          const errMsg: ChatMessage = {
            id: Date.now(),
            role: "assistant",
            ...failure,
            agent: typeof data.agent === "string" ? data.agent : selectedAgent?.name,
            thinkingMessageId: typeof data.message_id === "string" ? data.message_id : undefined,
            activity: hasActivity(activityRef.current) ? activityRef.current : undefined,
            ts: new Date().toLocaleTimeString(),
          };
          setMessages((prev) => [...prev, errMsg]);
          if (draft) {
            draft.message = errMsg;
            draft.live = false;
            persistActiveDraft();
          }
          if (["chat_stream_active", "chat_capacity", "chat_capacity_reached"].includes(String(data.code))) {
            // This submitted request was rejected before model work; any active
            // run has its own identity and draft lifecycle.
            if (draft?.message.requestId) {
              void clearCachedChatDraft(draft.sessionId, draft.message.requestId, draft.ownerToken);
              activeDraftRef.current = null;
            }
            setMessages((prev) => prev.map((message) => message.role === "user" && message.requestId === data.request_id
              ? { ...message, notStarted: true } : message));
            const pendingInput = pendingInputRef.current;
            if (pendingInput && pendingInput.requestId === data.request_id) {
              const unsent = pendingInput.content;
              setInput((current) => current || unsent);
            }
          }
          if (chatFailureNeedsRecovery(data)) {
            const active = parseChatRun(data.active_request, sessionIdRef.current);
            const submitted = typeof data.request_id === "string" ? data.request_id : draft?.message.requestId;
            recovery.begin(active?.request_id ?? submitted, submitted);
          } else if (draft?.message.requestId) {
            void clearCachedChatDraft(draft.sessionId, draft.message.requestId, draft.ownerToken);
            activeDraftRef.current = null;
          }
          refreshSessions();
          break;
        }
        case "task_stream":
          addTerminalLine(data.chunk as string, "");
          break;
        case "task_done":
          addTerminalLine(`Task completed: ${(data.result as string)?.substring(0, 500)}`, "gold");
          refreshAgents();
          break;
        case "queue_update":
          addTerminalLine(`Queue: ${data.action as string} (${data.pending as number} pending)`, "info");
          break;
        case "queue_task_complete":
          addTerminalLine(`Queue task done by ${data.agent as string}: ${(data.result as string)?.substring(0, 60)}`, "gold");
          break;
        case "perception_result":
          setStreaming(false);
          setLiveText("");
          setAwaitingText(false);
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: "assistant" as const,
              content: (data.result as PerceptionResult)?.batin || "Perception analysis complete",
              agent: "Basirah",
              ts: new Date().toLocaleTimeString(),
              perception: data.result as PerceptionResult,
            },
          ]);
          addTerminalLine("Perception analysis complete", "gold");
          break;
        case "agent_created":
          addTerminalLine(`Agent created: ${(data.agent as Record<string, unknown>).name}`, "gold");
          refreshAgents();
          break;
        case "artifact": {
          // The agent pipeline emitted an artifact: add it and announce it.
          const payload = data.artifact as ArtifactWsPayload;
          const kind: ArtifactKind =
            payload.kind === "code" || payload.kind === "html" || payload.kind === "image" ? payload.kind : "markdown";
          const versionNum = (payload.version as number) ?? 1;
          const artifact: Artifact = {
            id: payload.id,
            session_id: payload.session_id ?? sessionIdRef.current,
            title: payload.title ?? "Untitled artifact",
            kind,
            language: payload.language,
            current_version: versionNum,
            versions: typeof payload.content === "string"
              ? [{ version: versionNum, content: payload.content ?? "", created_at: payload.created_at ?? new Date().toISOString() }]
              : [],
          };
          setArtifacts((prev) =>
            prev.some((a) => a.id === artifact.id)
              ? prev.map((a) => a.id === artifact.id
                ? { ...a, ...artifact, versions: [...a.versions.filter((v) => v.version !== versionNum), ...artifact.versions] }
                : a)
              : [...prev, artifact],
          );
          addTerminalLine(`Artifact ready: ${artifact.title} (v${versionNum})`, "gold");
          addToast({ type: "success", title: "Artifact ready", description: `${artifact.title} — v${versionNum}` });
          break;
        }
      }
    },
    [clearStopFallback, finalizeStop, selectedAgent, persistActiveDraft, recovery.begin, applyActivity, refreshAgents, refreshSessions, bindChatWorkspace],
  );

  useEffect(() => {
    chatEventHandlerRef.current = handleChatEvent;
  }, [handleChatEvent]);
  useEffect(() => () => {
    sendControllerRef.current?.abort();
    streamBufferRef.current?.discard();
  }, []);

  // Socket frames: chat has a single SSE owner, so a frame carrying a request
  // id or another session's id is not this chat's.
  useEffect(() => {
    setSocketHandlers(
      (data) => {
        if (data.request_id || (data.session_id && data.session_id !== sessionIdRef.current)) return;
        chatEventHandlerRef.current(data);
      },
      () => resyncRef.current?.(),
    );
  }, []);

  // ===== resilient history load =====
  // Retries GET /api/chat/{sid} with backoff; on final failure shows a visible
  // retry. Server history is MERGED with local messages, deduped.
  const mapServerMessage = (
    m: {
      id?: number;
      role: string;
      content: string;
      agent_id?: string;
      created_at?: string;
      metadata?: {
        usage?: MessageUsageMeta;
        status?: string;
        partial?: boolean;
        code?: string;
        message?: string;
        completion_status?: MessageUsageMeta["completion_status"];
        answer_delivered?: boolean;
        task_verified?: boolean;
        request_id?: string;
        message_id?: string;
      };
    },
    idx: number,
  ): ChatMessage => ({
    id: m.id ?? idx,
    role: m.role as "user" | "assistant" | "system",
    ...restoredMessageFields(m.content, m.metadata),
    agent: m.agent_id,
    ts: m.created_at ? new Date(m.created_at).toLocaleTimeString() : "",
  });

  const authEpochRef = useRef(authRevision);
  authEpochRef.current = authRevision;

  const loadChatHistory = useCallback(
    async (sid: string, opts?: { onMissing?: () => void; quiet?: boolean; onLoaded?: (count: number) => void }): Promise<boolean> => {
      const requestToken = localStorage.getItem("mizan_token");
      const authEpoch = authEpochRef.current;
      const sameContext = () => !!requestToken && requestToken === localStorage.getItem("mizan_token") &&
        authEpoch === authEpochRef.current && sid === sessionIdRef.current;
      if (!sameContext()) return false;
      const load = historyLoads.begin(sameContext);
      setHistoryLoadError(false);
      try {
        const result = await fetchChatHistoryWithRetry(
          () => authFetch(`${config.API_URL}/chat/${sid}`, { headers: { Authorization: `Bearer ${requestToken}` } }),
          3,
          600,
          sameContext,
        );
        if (!sameContext()) return false;
        if (result.missing) {
          // Session expired or deleted server-side: the caller decides how to start fresh.
          if (load.isCurrent()) opts?.onMissing?.();
          return true;
        }
        if (!result.ok) {
          if (!opts?.quiet) {
            setHistoryLoadError(true);
            addToast({
              type: "error",
              title: "Could not load chat history",
              description: result.error?.message || "Check the connection and try again",
            });
          }
          return false;
        }
        const history = (result.messages as Parameters<typeof mapServerMessage>[0][]).map(mapServerMessage);
        setMessages((prev) => mergeHistoryMessages(history, prev));
        if (result.workspaceId !== undefined) bindChatWorkspace(sid, result.workspaceId ?? "");
        setHasOlderHistory(result.hasMore === true);
        opts?.onLoaded?.(history.length);
        return true;
      } finally {
        load.finish();
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [historyLoads, bindChatWorkspace],
  );
  recoveryHistoryRef.current = (sid) => loadChatHistory(sid, { quiet: true });

  /** Prepend the page of server messages older than the oldest loaded one. */
  const loadOlderHistory = useCallback(async () => {
    const sid = sessionIdRef.current;
    const oldest = messages.find((m) => typeof m.id === "string");
    if (!sid || !oldest || olderHistoryLoading) return;
    setOlderHistoryLoading(true);
    try {
      const res = await authFetch(`${config.API_URL}/chat/${sid}?limit=50&before=${encodeURIComponent(String(oldest.id))}`);
      if (!res.ok || sid !== sessionIdRef.current) return;
      const data = await res.json();
      const older = (Array.isArray(data?.messages) ? data.messages : []).map(mapServerMessage);
      setMessages((prev) => {
        const known = new Set(prev.map((m) => m.id));
        return [...older.filter((m: ChatMessage) => !known.has(m.id)), ...prev];
      });
      setHasOlderHistory(data?.has_more === true);
    } catch {
      addToast({ type: "error", title: "Could not load earlier messages" });
    } finally {
      setOlderHistoryLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, olderHistoryLoading]);

  /** After a socket reconnect, stream events may have been missed. Quiet. */
  const resyncSession = useCallback(() => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    addTerminalLine("Reconnected — resyncing chat history", "info");
    void loadChatHistory(sid, { quiet: true });
  }, [loadChatHistory]);
  useEffect(() => {
    resyncRef.current = resyncSession;
  }, [resyncSession]);

  const switchSession = useCallback(
    async (sid: string) => {
      if (sid === sessionIdRef.current) return;
      const requestToken = localStorage.getItem("mizan_token");
      historyLoads.reset();
      persistActiveDraft(true);
      activeDraftRef.current = null;
      recovery.reset();
      setRunProgress(null);
      sessionIdRef.current = sid;
      setDraftStorageFailed([...draftStorageFailures.current].some((key) => key.startsWith(`${sid}:`)));
      sendControllerRef.current?.abort();
      activeRequestIdRef.current = "";
      activeMessageIdRef.current = "";
      streamBufferRef.current?.discard();
      streamBufferRef.current = null;
      streamingRef.current = false;
      setStreaming(false);
      setLiveText("");
      setAwaitingText(false);
      resetActivity();
      setArtifacts([]);
      setShowArtifacts(false);
      setSessionId(sid);
      setWorkspaceId(chatWorkspace(sid));
      setLivePreview(null);
      setMessages([]);
      setHistoryLoadError(false);
      setTruncatedContinue(null);
      // Render the local cache instantly, then merge server history.
      try {
        const [cached, drafts] = await Promise.all([readCachedMessages(sid), readCachedChatDrafts(sid)]);
        const draft = drafts[drafts.length - 1];
        const restored = drafts.length
          ? mergeHistoryMessages((cached ?? []) as ChatMessage[], drafts.map((row) => row.message as ChatMessage))
          : cached;
        setMessages((current) => hydrateCachedMessages(
          current, restored as ChatMessage[] | null,
          sid === sessionIdRef.current && requestToken === localStorage.getItem("mizan_token"),
        ));
        if (draft && sid === sessionIdRef.current && requestToken === localStorage.getItem("mizan_token")) {
          recovery.begin(draft.message.requestId, draft.message.requestId, sid);
          return;
        }
      } catch {
        /* cache is best-effort */
      }
      if (sid !== sessionIdRef.current || requestToken !== localStorage.getItem("mizan_token")) return;
      await loadChatHistory(sid, {
        onLoaded: (count) => {
          if (count && !streamingRef.current) recovery.begin(undefined, undefined, sid);
        },
      });
    },
    [loadChatHistory, persistActiveDraft, recovery.begin, recovery.reset, historyLoads, resetActivity],
  );

  const startNewSession = useCallback(() => {
    historyLoads.reset();
    persistActiveDraft(true);
    activeDraftRef.current = null;
    recovery.reset();
    setRunProgress(null);
    sendControllerRef.current?.abort();
    activeRequestIdRef.current = "";
    activeMessageIdRef.current = "";
    streamBufferRef.current?.discard();
    streamBufferRef.current = null;
    streamingRef.current = false;
    setStreaming(false);
    setAwaitingText(false);
    resetActivity();
    setArtifacts([]);
    setShowArtifacts(false);
    const newId = newSessionId();
    sessionIdRef.current = newId;
    setDraftStorageFailed(false);
    setSessionId(newId);
    setWorkspaceId("");
    setLivePreview(null);
    setMessages([]);
    setLiveText("");
    setHistoryLoadError(false);
    setHasOlderHistory(false);
    setTruncatedContinue(null);
    continuationRef.current = 0;
    addTerminalLine("New chat session started", "gold");
  }, [persistActiveDraft, recovery.reset, historyLoads, resetActivity]);
  startNewSessionRef.current = startNewSession;

  const deleteSession = useCallback(async (sid: string): Promise<boolean> => {
    const confirmed = await confirmDialog({
      title: "Delete this chat?",
      description: "The chat and everything MIZAN learned from it are erased. This cannot be undone.",
      destructive: true,
    });
    if (!confirmed) return false;
    try {
      const res = await authFetch(`${config.API_URL}/chat/${encodeURIComponent(sid)}`, { method: "DELETE" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !isReceipt(body)) {
        addToast({
          type: "error",
          title: "Chat not deleted",
          description: typeof body?.detail === "string" ? body.detail : "Please try again.",
        });
        return false;
      }
      addToast({
        type: body.traces ? "warning" : "success",
        title: "Chat deleted",
        description: `${removedLine(body)}. ${checkLine(body)}`,
      });
      if (sid === sessionIdRef.current) startNewSessionRef.current?.();
      refreshSessions();
      return true;
    } catch {
      addToast({ type: "error", title: "Chat not deleted", description: "Please try again." });
      return false;
    }
  }, [refreshSessions]);

  // Restore the previous chat after a refresh: render the cache at once, then
  // fetch server history and merge. A stored id the backend no longer knows
  // (404) starts fresh silently.
  useEffect(() => {
    if (!localStorage.getItem("mizan_token")) return;
    const storedSid = sessionIdRef.current;
    const requestToken = localStorage.getItem("mizan_token");
    void (async () => {
      try {
        const [cached, drafts] = await Promise.all([readCachedMessages(storedSid), readCachedChatDrafts(storedSid)]);
        const draft = drafts[drafts.length - 1];
        const restored = drafts.length
          ? mergeHistoryMessages((cached ?? []) as ChatMessage[], drafts.map((row) => row.message as ChatMessage))
          : cached;
        setMessages((current) => hydrateCachedMessages(
          current, restored as ChatMessage[] | null,
          storedSid === sessionIdRef.current && requestToken === localStorage.getItem("mizan_token"),
        ));
        if (draft && storedSid === sessionIdRef.current && requestToken === localStorage.getItem("mizan_token")) {
          recovery.begin(draft.message.requestId, draft.message.requestId, storedSid);
          return;
        }
      } catch {
        /* cache is best-effort — the server fetch still runs */
      }
      if (storedSid !== sessionIdRef.current || requestToken !== localStorage.getItem("mizan_token")) return;
      await loadChatHistory(storedSid, {
        onLoaded: (count) => {
          if (count && !streamingRef.current) recovery.begin(undefined, undefined, storedSid);
        },
        onMissing: () => {
          // Expired or deleted on the server: start fresh, silently.
          try {
            localStorage.removeItem(CHAT_SESSION_STORAGE_KEY);
            localStorage.removeItem(LEGACY_CHAT_SESSION_KEY);
          } catch {
            /* ignore */
          }
          startNewSessionRef.current?.();
        },
      });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRevision]);

  // Persist the chat id (migrates the legacy key) and keep the ref in sync.
  useEffect(() => {
    sessionIdRef.current = sessionId;
    try {
      localStorage.setItem(CHAT_SESSION_STORAGE_KEY, sessionId);
      localStorage.removeItem(LEGACY_CHAT_SESSION_KEY);
    } catch {
      // storage unavailable — the session just won't survive a refresh
    }
  }, [sessionId]);

  // Debounced write of the visible messages to IndexedDB (localStorage
  // fallback); they render instantly on the next visit.
  useEffect(() => {
    if (!sessionId || messages.length === 0) return;
    const ownerToken = localStorage.getItem("mizan_token");
    if (!ownerToken) return;
    const timer = setTimeout(() => {
      void cacheMessages(sessionId, messages, ownerToken);
    }, 500);
    return () => clearTimeout(timer);
  }, [sessionId, messages]);

  // What the shell shows (current chat, a run in progress) without re-rendering on chunks.
  useEffect(() => {
    useChatSummary.setState({ sessionId, streaming, hasMessages: messages.length > 0 });
  }, [sessionId, streaming, messages.length]);

  // Client-side only: the in-memory conversation as Markdown / text / JSON.
  const exportChat = useCallback(
    async (format: ExportFormatId) => {
      if (messages.length === 0) {
        addToast({ type: "info", title: "There are no messages to export" });
        return;
      }
      if (
        messages.length > 300 &&
        !(await confirmDialog({
          title: `Export ${messages.length} messages?`,
          confirmLabel: "Export",
        }))
      )
        return;
      const meta = { sessionId };
      const body = format === "markdown"
        ? exportMarkdown(messages, meta)
        : format === "text" ? exportText(messages, meta) : exportJSON(messages, meta);
      const mime: Record<ExportFormatId, string> = {
        markdown: "text/markdown;charset=utf-8",
        text: "text/plain;charset=utf-8",
        json: "application/json;charset=utf-8",
      };
      const filename = buildExportFilename(sessionId, format);
      downloadExport(filename, mime[format], body);
      addToast({ type: "success", title: `Chat exported — ${messages.length} messages`, description: filename });
    },
    [messages, sessionId],
  );

  /**
   * Deep research: routes the query to the planner→workers→aggregator→verifier
   * pipeline. The backend requires per-request confirmation (409 otherwise)
   * and enforces a server-side cost/token budget.
   */
  const runDeepResearch = async (query: string) => {
    const userMsg: ChatMessage = { id: Date.now(), role: "user", content: query, ts: new Date().toLocaleTimeString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);
    setAwaitingText(true);
    setRunProgress({ startedAt: Date.now(), note: "Starting deep research…" });
    try {
      const res = await authFetch(`${config.API_URL}/modes/deep-research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, session_id: sessionId, confirmed: deepResearchConfirmed }),
      });
      if (res.status === 409) {
        addToast({
          type: "warning",
          title: "Confirmation required",
          description: "Deep research costs more. Confirm the cost in the Deep research option before sending.",
        });
        return;
      }
      if (res.status === 402) {
        const err = (await res.json().catch(() => ({}))) as { detail?: string };
        addToast({ type: "error", title: "Budget reached", description: err.detail || "The deep-research budget is spent." });
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as {
        answer?: string; unsupported_claims?: string[]; tokens_used?: number; cost_usd?: number;
      };
      const unsupported = (data.unsupported_claims || []).length
        ? `\n\n⚠️ Unverified claims: ${(data.unsupported_claims || []).join("; ")}`
        : "";
      const assistantMsg: ChatMessage = {
        id: Date.now(),
        role: "assistant",
        content: (data.answer || "") + unsupported,
        agent: selectedAgent?.id,
        model: "deep_research",
        ts: new Date().toLocaleTimeString(),
        meta: { model: "deep_research", output_tokens: data.tokens_used, cost_usd: data.cost_usd, cost_estimated: true },
      };
      setMessages((prev) => [...prev, assistantMsg]);
      addTerminalLine(`Deep research done — ${data.tokens_used ?? "?"} tokens, ~$${(data.cost_usd ?? 0).toFixed(4)}`, "info");
    } catch (e) {
      addToast({ type: "error", title: "Deep research failed", description: e instanceof Error ? e.message : String(e) });
    } finally {
      setStreaming(false);
      setAwaitingText(false);
      setRunProgress(null);
    }
  };

  const sendMessage = async (contentOverride?: string, options: SendOptions = {}) => {
    const text = contentOverride ?? input;
    if ((!text.trim() && attachedFiles.length === 0) || streamingRef.current) return;
    if (recovery.isBlocked()) { void recovery.refresh(); return; }
    if (text.length > CHAT_INPUT_LIMIT) {
      addToast({ type: "error", title: `Messages are limited to ${CHAT_INPUT_LIMIT.toLocaleString()} characters` });
      return;
    }
    const authToken = localStorage.getItem("mizan_token");
    if (!authToken) {
      setMessages((prev) => [...prev, {
        id: Date.now(), role: "assistant",
        content: "Sign in is required. Sign in, then send your message again.",
        ts: new Date().toLocaleTimeString(),
      }]);
      return;
    }
    if (providerStatus && !providerStatus.providers.some((p) => p.configured)) {
      const providerMsg = {
        id: Date.now(),
        role: "assistant" as const,
        content: "No AI provider is configured. An administrator adds a provider key in Settings → Developer → Providers.",
        ts: new Date().toLocaleTimeString(),
        cta: { label: "Open providers", tab: "providers" },
      } as ChatMessage & { cta: { label: string; tab: string } };
      setMessages((prev) => [...prev, providerMsg]);
      return;
    }
    const content = text;
    if (agentMode === "deep_research") {
      await runDeepResearch(content);
      return;
    }
    const files = [...attachedFiles];
    // Images go with the chat message itself (Basar); audio still uses the older media connection.
    const images = files.filter((f) => f.type.startsWith("image/")).slice(0, 4);
    const hasMedia = files.some((f) => f.type.startsWith("audio/"));
    const hasImages = images.length > 0;

    if ((hasMedia || hasImages) && (chatModelOverride || selectedAgent?.model || providerStatus?.default_model || "").startsWith("ruh")) {
      addToast({
        type: "warning",
        title: "Ruh currently accepts text",
        description: "You can view this attachment, but image or audio analysis needs a compatible provider.",
      });
      return;
    }
    if (hasMedia && wsStatus !== "connected") {
      addToast({
        type: "warning",
        title: "Audio analysis needs an active media connection",
        description: "Text chat is still available. Keep your attachment and reconnect before sending it.",
      });
      return;
    }

    const requestId = crypto.randomUUID();
    const others = files.filter((f) => !f.type.startsWith("image/"));
    let imagePayload: { media_type: string; data: string }[] = [];
    try {
      imagePayload = await Promise.all(images.map(async (file) => ({ media_type: file.type, data: await fileToBase64(file) })));
    } catch {
      addToast({ type: "warning", title: "Could not read the image", description: "Try attaching it again." });
      return;
    }
    const userMsg: ChatMessage = {
      id: Date.now(),
      role: "user",
      requestId: hasMedia ? undefined : requestId,
      content: content + (others.length > 0 ? ` [${others.map((f) => f.name).join(", ")}]` : ""),
      ts: new Date().toLocaleTimeString(),
      mode: options.permissionMode ?? permissionMode,
      ...(hasImages ? { images: images.map((file) => ({ url: URL.createObjectURL(file) })) } : {}),
    };
    setMessages((prev) => [...prev, userMsg]);
    streamingRef.current = true;
    setStreaming(true);
    setLiveText("");
    setAwaitingText(true);
    setActiveThinkingId(null);
    // Per-send AbortController (Stop cancels the HTTP POST end-to-end) and a fresh stream buffer.
    const controller = new AbortController();
    sendControllerRef.current = controller;
    continuationRef.current = 0;
    setTruncatedContinue(null);
    streamBufferRef.current = new StreamBuffer(setLiveText);
    setInput("");
    setAttachedFiles([]);
    addTerminalLine(`> ${content.substring(0, 60)}...`, "info");

    // Audio goes as multimodal over the socket.
    if (hasMedia) {
      try {
        const payload: Record<string, unknown> = {
          type: "multimodal", text: content, content, agent_id: selectedAgent?.id, session_id: sessionId,
        };
        for (const file of files) {
          const b64 = await fileToBase64(file);
          if (file.type.startsWith("image/")) {
            payload.image_base64 = b64;
            payload.media_type = file.type;
          } else if (file.type.startsWith("audio/")) {
            payload.audio_base64 = b64;
          }
        }
        if (!sendSocket(payload)) throw new Error("socket closed");
      } catch {
        setStreaming(false);
        setAwaitingText(false);
        addTerminalLine("Failed to process media files", "error");
      }
      return;
    }

    activeRequestIdRef.current = requestId;
    pendingInputRef.current = { requestId, content };
    persistActiveDraft(true);
    activeMessageIdRef.current = "";
    activeDraftRef.current = { sessionId, ownerToken: authToken, live: true, message: {
      id: -Date.now(), role: "assistant", content: "", ts: new Date().toLocaleTimeString(), requestId,
      agent: selectedAgent?.name, interrupted: true,
    } };
    persistActiveDraft();
    recovery.reset();
    setRunProgress({ startedAt: Date.now() });
    resetActivity();
    const override = chatModelOverride;
    try {
      await runChatRequest({
        request: () => authFetch(`${config.API_URL}/chat/stream`, {
          method: "POST",
          signal: controller.signal,
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({
            session_id: sessionId,
            content,
            agent_id: selectedAgent?.id,
            request_id: requestId,
            permission_mode: options.permissionMode ?? permissionMode,
            thinking: true,
            ...timeZoneField(),
            ...(workspaceId ? { workspace_id: workspaceId } : {}),
            ...(options.planApproved ? { plan_approved: true } : {}),
            ...(options.fix ? { fix: options.fix } : {}),
            ...(override ? { model_override: override } : {}),
            ...(imagePayload.length ? { images: imagePayload } : {}),
          }),
        }),
        sessionId,
        requestId,
        signal: controller.signal,
        isCurrent: () => activeRequestIdRef.current === requestId && sessionIdRef.current === sessionId,
        onStart: () => {
          if (override) setChatModelOverride((current) => current === override ? "" : current);
        },
        onEvent: (event) => {
          activeMessageIdRef.current = (event.message_id as string) || activeMessageIdRef.current;
          chatEventHandlerRef.current(event);
        },
      });
    } finally {
      if (activeRequestIdRef.current === requestId) {
        activeRequestIdRef.current = "";
        sendControllerRef.current = null;
        streamingRef.current = false;
        setStreaming(false);
        setAwaitingText(false);
      }
    }
  };

  const stopRecoveredRun = useCallback(() => {
    const state = recovery.state;
    if (!state) return;
    const requestId = state.request?.request_id ?? state.requestId;
    void authFetch(`${config.API_URL}/chat/${encodeURIComponent(state.sessionId)}/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestId ? { request_id: requestId } : {}),
    }).catch(() => undefined).finally(() => void recovery.refresh());
  }, [recovery]);

  // Actions are stable for the whole visit; each call reaches the latest closure.
  const latest = useRef({
    sendMessage, stopGeneration, requestContinuation, decideApproval, startNewSession, switchSession, deleteSession,
    loadChatHistory, loadOlderHistory, exportChat, stopRecoveredRun,
  });
  latest.current = {
    sendMessage, stopGeneration, requestContinuation, decideApproval, startNewSession, switchSession, deleteSession,
    loadChatHistory, loadOlderHistory, exportChat, stopRecoveredRun,
  };

  const actions = useMemo<ChatActions>(() => ({
    setInput,
    sendMessage: (content, options) => latest.current.sendMessage(content, options),
    stopGeneration: () => latest.current.stopGeneration(),
    continueAnswer: () => {
      setTruncatedContinue(null);
      continuationRef.current += 1;
      void latest.current.requestContinuation();
    },
    dismissContinue: () => setTruncatedContinue(null),
    decideApproval: (id, decision) => latest.current.decideApproval(id, decision),
    startNewSession: () => latest.current.startNewSession(),
    switchSession: (sid) => latest.current.switchSession(sid),
    deleteSession: (sid) => latest.current.deleteSession(sid),
    reloadHistory: () => void latest.current.loadChatHistory(sessionIdRef.current),
    loadOlderHistory: () => latest.current.loadOlderHistory(),
    exportChat: (format) => latest.current.exportChat(format),
    setAgentMode,
    setDeepResearchConfirmed,
    setPermissionMode,
    setChatModelOverride,
    setAttachedFiles,
    selectWorkspace,
    setShowArtifacts,
    addArtifact: (artifact) => {
      setArtifacts((previous) => [...previous.filter((item) => item.id !== artifact.id), artifact]);
      setShowArtifacts(true);
    },
    toggleDebug,
    setDebugPrompt,
    stopRecoveredRun: () => latest.current.stopRecoveredRun(),
    registerComposer: (element) => {
      composerRef.current = element;
    },
    focusComposer: () => composerRef.current?.focus(),
  }), [selectWorkspace, toggleDebug]);

  const state: ChatState = {
    sessionId, messages, input, streaming, awaitingText, activity, thinkingTraces, activeThinkingId, runProgress,
    agentMode, deepResearchConfirmed, permissionMode, chatModelOverride, attachedFiles, workspaceId, livePreview, artifacts,
    showArtifacts, debugAllowed, debugOn, debugPrompt, historyLoadError, historyLoading, hasOlderHistory,
    olderHistoryLoading, draftStorageFailed, truncatedContinue, recovery,
  };

  return (
    <ChatActionsContext.Provider value={actions}>
      <ChatStateContext.Provider value={state}>{children}</ChatStateContext.Provider>
    </ChatActionsContext.Provider>
  );
}
