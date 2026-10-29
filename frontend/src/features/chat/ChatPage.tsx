/**
 * /chat and /chat/:sessionId. The URL names the open chat: opening a link
 * switches to it, a new chat is /chat until its first message, and Back and
 * Forward move between chats.
 */
import { useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useChatActions, useChatState } from "./ChatProvider";
import { ChatHeader } from "./ChatHeader";
import { ChatThread } from "./ChatThread";
import { Composer } from "./Composer";

const UNSET = Symbol("unset");

export default function ChatPage() {
  const { sessionId: param } = useParams();
  const navigate = useNavigate();
  const { sessionId, messages, streaming } = useChatState();
  const { switchSession, startNewSession } = useChatActions();
  const hasChat = messages.length > 0 || streaming;

  // The URL changed (a link, Back/Forward, the sidebar): open that chat.
  const lastParam = useRef<string | undefined | typeof UNSET>(UNSET);
  useEffect(() => {
    if (param === lastParam.current) return;
    lastParam.current = param;
    if (param) {
      if (param !== sessionId) void switchSession(param);
    } else if (hasChat && !streaming) {
      startNewSession();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [param]);

  // The chat changed (first message sent, /new, deleted): the URL follows.
  useEffect(() => {
    if (hasChat) {
      if (param !== sessionId) {
        lastParam.current = sessionId;
        navigate(`/chat/${encodeURIComponent(sessionId)}`, { replace: true });
      }
    } else if (param && param !== sessionId) {
      lastParam.current = undefined;
      navigate("/chat", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, hasChat]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatHeader />
      <ChatThread />
      <Composer />
    </div>
  );
}
