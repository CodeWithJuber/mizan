import { runChatRequest } from "./chatRequest.ts";
import { parseChatRun } from "./chatRecovery.ts";
let checks = 0;
function check(name: string, value: boolean) { if (!value) throw new Error(name); checks++; }
const active = { request_id: "older-request", message_id: "older-message", session_id: "session", status: "running", phase: "context_preparation", elapsed_ms: 64000 };
for (const [status, code, extra] of [
  [409, "chat_stream_active", { active_request: active }],
  [409, "request_already_submitted", { status: "running", same_request: true }],
  [429, "chat_capacity_reached", {}],
  [429, "chat_capacity", {}],
] as const) {
  let posts = 0;
  const events: Record<string, unknown>[] = [];
  await runChatRequest({
    request: async () => { posts++; return Response.json({ detail: { code, message: "Server status notice", request_id: "submitted-request", session_id: "session", ...extra } }, { status }); },
    sessionId: "session", requestId: "submitted-request", signal: new AbortController().signal,
    isCurrent: () => true, onEvent: (event) => { events.push(event); },
  });
  check(`${code} keeps its own classification instead of pretending a network failure`, events.length === 1 && events[0].code === code && events[0].http_status === status);
  check(`${code} does not resubmit the POST`, posts === 1);
  check(`${code} remains scoped to the rejected/submitted request`, events[0].request_id === "submitted-request");
  if (code === "chat_stream_active")
    check("active run identity is kept separately for GET recovery", parseChatRun(events[0].active_request, "session")?.request_id === "older-request");
}
const legacy: Record<string, unknown>[] = [];
await runChatRequest({
  request: async () => Response.json({ detail: "A chat stream is already active; read session history" }, { status: 409 }),
  sessionId: "session", requestId: "submitted-request", signal: new AbortController().signal,
  isCurrent: () => true, onEvent: (event) => { legacy.push(event); },
});
check("legacy deployed active409 remains recoverable during rollout", legacy[0]?.code === "chat_stream_active");
const foreign: Record<string, unknown>[] = [];
await runChatRequest({
  request: async () => Response.json({ detail: { code: "chat_stream_active", session_id: "another-session", request_id: "submitted-request", active_request: active } }, { status: 409 }),
  sessionId: "session", requestId: "submitted-request", signal: new AbortController().signal,
  isCurrent: () => true, onEvent: (event) => { foreign.push(event); },
});
check("a mismatched rejection envelope cannot inject another session's active run", foreign[0]?.code === "chat_transport_error" && foreign[0]?.active_request === undefined);
console.log(`${checks} recovery transport checks passed`);
