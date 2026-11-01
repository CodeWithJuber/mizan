import { SseDecoder, consumeChatStream } from "./chatSse.ts";
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
const failure = {
  type: "error",
  code: "output_budget_exhausted",
  message: "The model reached its output limit before producing an answer.",
  completion_status: "incomplete",
  answer_delivered: false,
  task_verified: false,
  usage: {
    model: "test-model", output_tokens: 200, reasoning_tokens: 200,
    timings: { provider_ms: 1200, total_ms: 2300 },
    owned_checkpoint: { source: "registry", sha256: "a".repeat(64), generation: 2 },
  },
};
const failureEvents: Record<string, unknown>[] = [];
const failureOptions = {
  sessionId: "session", requestId: "request",
  signal: new AbortController().signal,
  onEvent: (event: Record<string, unknown>) => { failureEvents.push(event); },
};
await consumeChatStream(new Response(
  frame("chat_stream", { chunk: "partial" }) + frame("error", failure) + frame("error", failure),
  { headers: { "Content-Type": "text/event-stream" } },
), failureOptions);
check("partial then terminal error dispatches only once", failureEvents.length === 2 && failureEvents[0].chunk === "partial" && failureEvents[1].type === "error");
check("SSE error preserves all counters and timings", JSON.stringify(failureEvents[1].usage) === JSON.stringify(failure.usage));
check("SSE error preserves explicit incomplete receipt", failureEvents[1].completion_status === "incomplete" && failureEvents[1].answer_delivered === false && failureEvents[1].task_verified === false);
for (const status of [200, 422, 500]) {
  const received: Record<string, unknown>[] = [];
  await consumeChatStream(new Response(JSON.stringify(status === 422 ? { detail: failure } : failure), {
    status, headers: { "Content-Type": "application/json" },
  }), { ...failureOptions, onEvent: (event) => { received.push(event); } });
  check(`JSON ${status} failure is one terminal event with full usage`, received.length === 1 && received[0].type === "error" && JSON.stringify(received[0].usage) === JSON.stringify(failure.usage));
  check(`JSON ${status} failure inherits only its owned request scope`, received[0].session_id === "session" && received[0].request_id === "request");
}
for (const wrongScope of [{ session_id: "other" }, { request_id: "other" }]) {
  let rejected = false;
  try {
    await consumeChatStream(new Response(JSON.stringify({ ...failure, ...wrongScope }), {
      headers: { "Content-Type": "application/json" },
    }), { ...failureOptions, onEvent: () => { throw new Error("Unexpected dispatch"); } });
  } catch (error) {
    rejected = (error as Error).message.includes("another request");
  }
  check("JSON failure with mismatched scope is rejected", rejected);
}
let unauthorized = false;
try {
  await consumeChatStream(new Response(JSON.stringify({ detail: "Unauthorized" }), {
    status: 401, headers: { "Content-Type": "application/json" },
  }), { ...failureOptions, onEvent: () => { throw new Error("Unexpected dispatch"); } });
} catch (error) {
  unauthorized = (error as Error).message === "Unauthorized";
}
check("ordinary HTTP authorization failure remains an exception", unauthorized);
console.log(`${checks} SSE checks passed`);
