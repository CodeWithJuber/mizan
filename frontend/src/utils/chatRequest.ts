import { consumeChatStream, type ChatStreamEvent } from "./chatSse.ts";

/** One owned POST attempt. Transport failures are persistent chat events, never retries. */
export async function runChatRequest(options: {
  request: () => Promise<Response>;
  sessionId: string;
  requestId: string;
  signal: AbortSignal;
  isCurrent: () => boolean;
  /** Consume one-shot state synchronously, before the request can become stale. */
  onStart?: () => void;
  onEvent: (event: ChatStreamEvent) => void;
}): Promise<void> {
  const ownsRequest = () => !options.signal.aborted && options.isCurrent();
  if (!ownsRequest()) return;
  try {
    options.onStart?.();
    const response = await options.request();
    if (!ownsRequest()) {
      await response.body?.cancel().catch(() => {});
      return;
    }
    await consumeChatStream(response, {
      sessionId: options.sessionId,
      requestId: options.requestId,
      signal: options.signal,
      onEvent: (event) => {
        if (ownsRequest()) options.onEvent(event);
      },
    });
  } catch (error) {
    // User Stop/session changes already settle their own UI; a late request
    // must never append an error to another session or stop its new request.
    if (!ownsRequest()) return;
    const detail = error instanceof Error && error.message.trim()
      ? error.message.trim().slice(0, 600)
      : "Connection interrupted. Check chat history before retrying.";
    options.onEvent({
      type: "error",
      code: "chat_transport_error",
      message: detail,
      completion_status: "incomplete",
      answer_delivered: false,
      task_verified: false,
      session_id: options.sessionId,
      request_id: options.requestId,
    });
  }
}
