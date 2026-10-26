import type { ChatMessage } from "../types.ts";
import { chatFailureFields } from "./chatFailure.ts";
import { runChatRequest } from "./chatRequest.ts";
import { StreamBuffer } from "./streaming.ts";

let checks = 0;
function check(name: string, ok: boolean) {
  if (!ok) throw new Error(name);
  checks++;
}
const frame = (type: string, data: Record<string, unknown> = {}) =>
  `event: ${type}\ndata: ${JSON.stringify({ session_id: "session", request_id: "request", ...data })}\n\n`;
const stream = (body: string) => new Response(body, { headers: { "Content-Type": "text/event-stream" } });

function chatView() {
  let current = true;
  let loading = true;
  const controller = new AbortController();
  const buffer = new StreamBuffer(() => {});
  const events: string[] = [];
  const messages: ChatMessage[] = [{ id: 1, role: "user", content: "2+2?", ts: "" }];
  return {
    controller, events, messages,
    loading: () => loading,
    supersede: () => { current = false; },
    run: (request: () => Promise<Response>) => runChatRequest({
      request, sessionId: "session", requestId: "request", signal: controller.signal,
      isCurrent: () => current,
      onEvent: (event) => {
        events.push(event.type);
        if (event.type === "chat_stream") buffer.push(event.chunk as string);
        if (event.type === "error") {
          messages.push({ id: 2, role: "assistant", ts: "", ...chatFailureFields(event, buffer.finalize()) });
          loading = false;
        }
        if (event.type === "chat_complete") {
          messages.push({ id: 2, role: "assistant", ts: "", content: event.response as string });
          loading = false;
        }
      },
    }),
  };
}

// Reproduces production: valid SSE headers, then EOF without any answer/terminal event.
const empty = chatView();
let attempts = 0;
await empty.run(async () => { attempts++; return stream(": heartbeat\n\n"); });
check("empty SSE interruption creates a persistent assistant notice", empty.messages.length === 2 && empty.messages[1].error?.message.includes("Connection interrupted") === true);
check("empty interruption does not invent answer bytes", empty.messages[1].content === "");
check("transport interruption clears loading without a user-stopped label", !empty.loading() && empty.messages[1].stopped !== true);
check("transport failure is incomplete and unverified", empty.messages[1].meta?.completion_status === "incomplete" && empty.messages[1].meta?.task_verified === false);
check("chat POST is never silently retried", attempts === 1);

const partial = chatView();
const bytes = "  Partial\n```python\nprint('unfinished')\n";
await partial.run(async () => stream(frame("chat_stream", { chunk: bytes })));
check("EOF after a partial preserves exact text plus an error notice", partial.messages[1].content === bytes && Boolean(partial.messages[1].error));
check("partial interruption has one terminal error", partial.events.join(",") === "chat_stream,error");

const rejected = chatView();
await rejected.run(async () => { throw new TypeError("Failed to fetch"); });
check("pre-stream fetch rejection is visible in chat", rejected.messages[1].error?.message === "Failed to fetch" && !rejected.loading());
const http = chatView();
await http.run(async () => new Response(JSON.stringify({ detail: "Service temporarily unavailable" }), { status: 503, headers: { "Content-Type": "application/json" } }));
check("HTTP failure is visible without waiting for history", http.messages[1].error?.message === "Service temporarily unavailable");
const malformed = chatView();
await malformed.run(async () => stream("event: chat_stream\ndata: {invalid\n\n"));
check("malformed stream becomes a single persistent failure", malformed.events.join() === "error" && malformed.messages.length === 2);

const known = chatView();
await known.run(async () => stream(frame("error", {
  code: "output_budget_exhausted", message: "Output limit reached", completion_status: "incomplete",
  usage: { output_tokens: 200, timings: { total_ms: 1000 } },
})));
check("canonical server error is not replaced or duplicated", known.events.join() === "error" && known.messages[1].error?.code === "output_budget_exhausted" && known.messages[1].meta?.output_tokens === 200);
const success = chatView();
await success.run(async () => stream(frame("chat_complete", { response: "4" })));
check("successful response stays successful", success.events.join() === "chat_complete" && success.messages[1].content === "4" && success.messages[1].error === undefined);

const aborted = chatView();
await aborted.run(async () => {
  aborted.controller.abort();
  throw new DOMException("Stopped", "AbortError");
});
check("intentional Stop does not create a transport error", aborted.events.length === 0 && aborted.messages.length === 1);
const lateFailure = chatView();
await lateFailure.run(async () => { lateFailure.supersede(); throw new Error("Late error from old chat"); });
check("late failure cannot append to a later session", lateFailure.events.length === 0);
const lateContinuation = chatView();
let cancelled = false;
await lateContinuation.run(async () => {
  lateContinuation.supersede();
  return new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode(frame("chat_complete", { response: "Late continuation" }))); },
    cancel() { cancelled = true; },
  }), { headers: { "Content-Type": "text/event-stream" } });
});
check("superseded continuation cannot append to the new session", lateContinuation.events.length === 0);
check("superseded response producer is closed", cancelled);
let ownsStream = true;
const switchedEvents: string[] = [];
await runChatRequest({
  request: async () => stream(frame("chat_stream", { chunk: "old partial" }) + frame("chat_complete", { response: "old answer" })),
  sessionId: "session", requestId: "request", signal: new AbortController().signal,
  isCurrent: () => ownsStream,
  onEvent: (event) => { switchedEvents.push(event.type); ownsStream = false; },
});
check("session switch during streaming suppresses the old terminal event", switchedEvents.join() === "chat_stream");
const alreadyStopped = chatView();
alreadyStopped.controller.abort();
let requested = false;
await alreadyStopped.run(async () => { requested = true; return stream(""); });
check("an already aborted request does not send a POST", !requested);

// One-shot overrides are consumed before awaiting A; a later B selection is
// untouched when A settles, even when B selects the exact same model string.
for (const nextOverride of ["model-B", "model-A"]) {
  let override = "model-A";
  const captured = override;
  let owns = true;
  let sentModel = "";
  let resolveResponse!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => { resolveResponse = resolve; });
  const pending = runChatRequest({
    sessionId: "session-A", requestId: "request-A", signal: new AbortController().signal,
    isCurrent: () => owns,
    onStart: () => { if (override === captured) override = ""; },
    request: () => { sentModel = captured; return response; },
    onEvent: () => { throw new Error("Old request dispatched into new session"); },
  });
  check("one-shot override is consumed synchronously at request start", override === "" && sentModel === "model-A");
  owns = false;
  override = nextOverride;
  resolveResponse(stream(frame("chat_complete", { response: "late A" })));
  await pending;
  check(`late request A cannot clear newer ${nextOverride} selection`, override === nextOverride);
}
let staleStart = false;
await runChatRequest({
  sessionId: "old", requestId: "old", signal: new AbortController().signal,
  isCurrent: () => false,
  onStart: () => { staleStart = true; },
  request: async () => { throw new Error("Unexpected POST"); },
  onEvent: () => { throw new Error("Unexpected dispatch"); },
});
check("already superseded request cannot consume a newer override", !staleStart);
console.log(`${checks} chat request lifecycle checks passed`);
