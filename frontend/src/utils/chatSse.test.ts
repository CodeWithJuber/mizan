import { SseDecoder, consumeChatStream } from "./chatSse.ts";
declare const process: { exit(code: number): void };
let checks = 0;
function check(name: string, ok: boolean) {
  if (!ok) throw new Error(name);
  checks++;
}
const envelope = { session_id: "session", request_id: "request" };
const frame = (type: string, data: Record<string, unknown>) =>
  `event: ${type}\r\ndata: ${JSON.stringify({ ...envelope, ...data })}\r\n\r\n`;
const decoder = new SseDecoder();
const raw =
  ": heartbeat\n\n" +
  frame("chat_stream", { chunk: "السلام" }) +
  frame("chat_complete", { response: "السلام" });
const parsed = [];
for (const character of raw) parsed.push(...decoder.push(character));
check(
  "fragmented CRLF frames and comments",
  parsed.length === 2 && parsed[0].chunk === "السلام",
);
const bytes = new TextEncoder().encode(raw);
const response = () =>
  new Response(
    new ReadableStream({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
const seen: string[] = [];
await consumeChatStream(response(), {
  sessionId: "session",
  requestId: "request",
  signal: new AbortController().signal,
  onEvent: (event) => seen.push(event.type),
});
check(
  "UTF8 byte fragmentation and terminal event",
  seen.join(",") === "chat_stream,chat_complete",
);
let mismatch = false;
try {
  await consumeChatStream(response(), {
    sessionId: "other",
    requestId: "request",
    signal: new AbortController().signal,
    onEvent: () => {
      throw new Error("Unexpected dispatch");
    },
  });
} catch (error) {
  mismatch = (error as Error).message.includes("another request");
}
check("cross-request frame rejected before UI dispatch", mismatch);
let interrupted = false;
try {
  await consumeChatStream(
    new Response(frame("chat_stream", { chunk: "partial" }), {
      headers: { "Content-Type": "text/event-stream" },
    }),
    {
      sessionId: "session",
      requestId: "request",
      signal: new AbortController().signal,
      onEvent: () => {},
    },
  );
} catch (error) {
  interrupted = (error as Error).message.includes("partial response");
}
check("missing terminal event is visible interruption", interrupted);
let malformed = false;
try {
  new SseDecoder().push('event: chat_stream\ndata: {"type":"error"}\n\n');
} catch {
  malformed = true;
}
check("disagreeing event type rejected", malformed);
let oversized = false;
try {
  new SseDecoder().push("x".repeat(8 * 1024 * 1024 + 1));
} catch {
  oversized = true;
}
check("unbounded event rejected", oversized);
let duplicate = 0;
await consumeChatStream(
  new Response(
    frame("chat_complete", { response: "done" }) +
      frame("chat_complete", { response: "duplicate" }),
    { headers: { "Content-Type": "text/event-stream" } },
  ),
  {
    sessionId: "session",
    requestId: "request",
    signal: new AbortController().signal,
    onEvent: () => duplicate++,
  },
);
check("only first terminal event dispatched", duplicate === 1);
let producerCancelled = false;
try {
  await consumeChatStream(
    new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode(
              frame("chat_stream", { chunk: "wrong scope" }),
            ),
          );
        },
        cancel() {
          producerCancelled = true;
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    ),
    {
      sessionId: "another-session",
      requestId: "request",
      signal: new AbortController().signal,
      onEvent: () => {},
    },
  );
} catch {
  /* request scope rejection is expected */
}
check("protocol rejection closes the owned producer", producerCancelled);
console.log(`${checks} SSE checks passed`);
