/**
 * The conversation: earlier messages, the live reply, and the notices that
 * belong to the chat (history failed to load, the answer hit its length
 * limit, a run is being recovered).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowDown, LoaderCircle, RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatMessageBubble, MizanMark } from "../../components/ChatMessage";
import { StreamingMarkdown } from "../../components/StreamingMarkdown";
import { ChatRunStatus } from "../../components/ChatRunStatus";
import { recoveryWorthShowing } from "../../utils/chatRecovery.ts";
import { routeForLegacyTab } from "../../app/legacyTabs";
import { useAgents, useSelectedAgent } from "../agents/agents";
import { useChatActions, useChatState } from "./ChatProvider";
import { RunTimeline } from "./RunTimeline";
import { useLiveText } from "./liveStore";
import { EmptyState } from "./EmptyState";

/** The reply that is arriving right now. Only this re-renders on each chunk. */
function LiveReply({ agentName, onNear }: { agentName: string; onNear: () => void }) {
  const text = useLiveText((state) => state.text);
  const { activity, thinkingTraces, activeThinkingId, runProgress, awaitingText } = useChatState();
  const { decideApproval, answerElicitation } = useChatActions();
  const startedAt = useRef(Date.now());
  useEffect(onNear, [text, activity, onNear]);
  return (
    <div className="chat-message-row">
      <div className="chat-message-container">
        <div className="flex gap-3">
          <MizanMark className="mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex h-7 items-center">
              <span className="text-sm font-medium">{agentName}</span>
            </div>
            <RunTimeline
              activity={activity}
              trace={activeThinkingId ? thinkingTraces[activeThinkingId] : undefined}
              progress={runProgress ?? { startedAt: startedAt.current }}
              awaitingText={awaitingText || !text}
              onDecision={decideApproval}
              onElicitation={answerElicitation}
            />
            {text && <StreamingMarkdown content={text} />}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ChatThread() {
  const state = useChatState();
  const actions = useChatActions();
  const navigate = useNavigate();
  const { data: agents } = useAgents();
  const selectedAgent = useSelectedAgent();
  const agentName = selectedAgent?.name || "MIZAN";
  const scrollRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const [showScrollDown, setShowScrollDown] = useState(false);

  const scrollToEnd = useCallback((smooth = false) => {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);
  // Follow new text only while the reader is at the bottom: never yank them
  // away from history they scrolled up to read.
  const followIfNear = useCallback(() => {
    if (nearBottom.current) scrollToEnd();
  }, [scrollToEnd]);
  useEffect(followIfNear, [state.messages, state.streaming, followIfNear]);
  // A different chat opens at its end.
  useEffect(() => {
    nearBottom.current = true;
    requestAnimationFrame(() => scrollToEnd());
  }, [state.sessionId, scrollToEnd]);

  const onScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    nearBottom.current = distance < 150;
    setShowScrollDown(distance > 300);
  }, []);

  const onNavigateTab = useCallback((tab: string) => navigate(routeForLegacyTab(tab)), [navigate]);
  const onEdit = useCallback((text: string) => {
    actions.setInput(text);
    actions.focusComposer();
  }, [actions]);
  const onRewind = useCallback((checkpoint: { workspace_id: string; id: string }) => {
    void import("../code/rewind").then(({ rewindTo }) => rewindTo(checkpoint));
  }, []);
  const onCompare = useCallback((text: string) => {
    actions.setDebugPrompt(text);
    navigate("/settings/developer/debug");
  }, [actions, navigate]);

  const { messages, streaming } = state;
  const lastAssistant = messages.reduce((last, message, index) => (message.role === "assistant" ? index : last), -1);
  const retryText = (() => {
    for (let index = lastAssistant - 1; index >= 0; index--) {
      if (messages[index].role === "user") return messages[index].content;
    }
    return "";
  })();
  const empty = messages.length === 0 && !streaming;

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onScroll={onScroll} className="absolute inset-0 overflow-y-auto [scrollbar-gutter:stable]">
        {state.historyLoadError && (
          <div className="chat-message-row">
            <div className="chat-message-container flex items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/8 p-3">
              <TriangleAlert className="size-5 shrink-0 text-destructive" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">Could not load this chat</p>
                <p className="text-xs text-muted-foreground">Check the connection, then try again.</p>
              </div>
              <Button size="sm" variant="outline" onClick={actions.reloadHistory}>
                <RotateCcw /> Retry
              </Button>
            </div>
          </div>
        )}

        {empty ? (
          state.historyLoading ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
              <LoaderCircle className="size-6 animate-spin text-brand" />
              Loading chat…
            </div>
          ) : (
            <EmptyState />
          )
        ) : (
          <div className="pb-6 pt-4">
            {state.hasOlderHistory && (
              <div className="flex justify-center pb-3">
                <Button variant="outline" size="sm" onClick={() => void actions.loadOlderHistory()} disabled={state.olderHistoryLoading}>
                  {state.olderHistoryLoading ? "Loading…" : "Load earlier messages"}
                </Button>
              </div>
            )}
            {messages.map((message, index) => (
              <ChatMessageBubble
                key={message.id}
                msg={message}
                agentName={agentName}
                agents={agents}
                debug={state.debugAllowed && state.debugOn}
                onNavigateTab={onNavigateTab}
                trace={message.thinkingMessageId ? state.thinkingTraces[message.thinkingMessageId] : undefined}
                onEdit={message.role === "user" && !streaming ? onEdit : undefined}
                onCompare={message.role === "user" && state.debugAllowed && state.debugOn ? onCompare : undefined}
                onRewind={message.role === "user" && message.checkpoint && !streaming ? onRewind : undefined}
                onRetry={index === lastAssistant && !streaming && retryText ? () => void actions.sendMessage(retryText) : undefined}
              />
            ))}
            {streaming && <LiveReply agentName={agentName} onNear={followIfNear} />}
            {state.truncatedContinue && !streaming && (
              <div className="chat-message-row">
                <div className="chat-message-container flex flex-wrap items-center gap-3 rounded-xl border border-primary/40 bg-primary/8 p-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">The answer reached its length limit</p>
                    <p className="text-xs text-muted-foreground">Continue to get the rest of it.</p>
                  </div>
                  <Button size="sm" onClick={actions.continueAnswer}>Continue</Button>
                  <Button size="sm" variant="ghost" onClick={actions.dismissContinue}>Dismiss</Button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="chat-message-row pb-2">
          <div className="chat-message-container">
            <ChatRunStatus
              progress={null}
              recovery={recoveryWorthShowing(state.recovery.state) ? state.recovery.state : null}
              storageUnavailable={state.draftStorageFailed}
              onRefresh={() => void state.recovery.refresh()}
              onStop={actions.stopRecoveredRun}
            />
          </div>
        </div>
      </div>

      {showScrollDown && (
        <Button
          variant="outline"
          size="icon"
          aria-label="Scroll to the latest message"
          onClick={() => {
            nearBottom.current = true;
            scrollToEnd(true);
          }}
          className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full bg-background shadow-md"
        >
          <ArrowDown />
        </Button>
      )}
    </div>
  );
}
