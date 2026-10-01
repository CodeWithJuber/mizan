/** Authenticated chat uses fetch streams; a POST is never retried automatically. */
export type ChatStreamEvent = Record<string, unknown> & { type: string };
const MAX_FRAME_CHARS = 8 * 1024 * 1024;

export class SseDecoder {
  private buffered = "";

  push(text: string): ChatStreamEvent[] {
    this.buffered += text;
    const events: ChatStreamEvent[] = [];
    for (;;) {
      const separator = /\r?\n\r?\n/.exec(this.buffered);
      if (!separator) break;
      const frame = this.buffered.slice(0, separator.index);
      this.buffered = this.buffered.slice(
        separator.index + separator[0].length,
      );
      if (frame.length > MAX_FRAME_CHARS)
        throw new Error("Chat event exceeded the size limit");
      let type = "message";
      const data: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (!line || line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon < 0 ? line : line.slice(0, colon);
        const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "event") type = value;
        if (field === "data") data.push(value);
      }
      if (!data.length) continue;
      const parsed: unknown = JSON.parse(data.join("\n"));
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Invalid chat event");
      }
      const event = parsed as Record<string, unknown>;
      if (event.type != null && event.type !== type)
        throw new Error("Chat event type mismatch");
      events.push({ ...event, type });
    }
    if (this.buffered.length > MAX_FRAME_CHARS)
      throw new Error("Chat event exceeded the size limit");
    return events;
  }
}

export async function consumeChatStream(
  response: Response,
  options: {
    sessionId: string;
    requestId: string;
    signal: AbortSignal;
    onEvent: (event: ChatStreamEvent) => void;
  },
): Promise<void> {
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail.slice(0, 300);
      else if (typeof body.detail?.message === "string")
        detail = `${body.detail.message.slice(0, 300)} Check chat history before retrying.`;
    } catch {
      /* HTTP status remains useful */
    }
    throw new Error(detail || `Chat request failed (${response.status})`);
  }
  if (
    !response.headers.get("content-type")?.includes("text/event-stream") ||
    !response.body
  ) {
    throw new Error("The server did not return a chat stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const frames = new SseDecoder();
  let terminal = false;
  try {
    while (!terminal) {
      if (options.signal.aborted)
        throw new DOMException("Generation stopped", "AbortError");
      const { value, done } = await reader.read();
      const events = frames.push(decoder.decode(value, { stream: !done }));
      for (const event of events) {
        if (
          event.session_id !== options.sessionId ||
          event.request_id !== options.requestId
        ) {
          throw new Error("Chat stream belongs to another request");
        }
        options.onEvent(event);
        if (event.type === "chat_complete" || event.type === "error") {
          terminal = true;
          break;
        }
      }
      if (done) break;
    }
    if (!terminal)
      throw new Error(
        "Connection interrupted. Your partial response is preserved; check history before retrying.",
      );
  } finally {
    // Any parse/protocol error also closes this owned stream and cancels its producer.
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
