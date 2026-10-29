import { canDiscardRecoveredDraft, chatFailureNeedsRecovery, CHAT_INPUT_LIMIT, parseChatRun, parseRunState, phaseLabel, recoverChatRun, recoveryBlocksSend, recoveryWorthShowing } from "./chatRecovery.ts";
import type { ChatRecoveryState } from "./chatRecovery.ts";

let checks = 0;
function check(name: string, value: boolean) { if (!value) throw new Error(name); checks++; }
const request = { request_id: "existing-request", message_id: "message", session_id: "session", status: "running", phase: "queued", elapsed_ms: 64000, provider_attempt_count: 0 };
const active = parseRunState({ state: "active", request, history_saved: false }, "session");
check("active run uses server identity even if a different new POST was rejected", active.request?.request_id === "existing-request");
check("measured zero attempts remains distinguishable from missing usage", active.request?.provider_attempt_count === 0);
check("unknown provider count is not invented", parseChatRun({ ...request, provider_attempt_count: null }, "session")?.provider_attempt_count === undefined);
check("negative timing is not shown", parseChatRun({ ...request, elapsed_ms: -1 }, "session")?.elapsed_ms === undefined);
check("different session run identity is rejected", parseChatRun(request, "another-session") === null);
for (const body of [null, { state: "finished" }, { state: "active", request: null }, { state: "active", request: { ...request, session_id: "other" } }, { state: "idle", request }]) {
  let rejected = false;
  try { parseRunState(body, "session"); } catch { rejected = true; }
  check("invalid or cross-session run state fails closed", rejected);
}
for (const state of ["checking", "active", "unknown"] as const) {
  const snapshot: ChatRecoveryState = { sessionId: "session", state, checkedAt: 0 };
  check(`${state} keeps Send locked regardless of age`, recoveryBlocksSend(snapshot, "session"));
  check(`${state} from a different session does not lock this one`, !recoveryBlocksSend(snapshot, "another"));
}
for (const state of ["idle", "terminal"] as const)
  check(`${state} allows an explicit new user action`, !recoveryBlocksSend({ sessionId: "session", state }, "session"));
check("no recovery does not block a new session", !recoveryBlocksSend(null, "session"));
const saved = parseRunState({ state: "terminal", request: { ...request, status: "complete" }, history_saved: true }, "session");
const unsaved = parseRunState({ state: "terminal", request: { ...request, status: "error" }, history_saved: false }, "session");
check("terminal missing-history receipt allows ended status without claiming a saved reply", unsaved.state === "terminal" && unsaved.history_saved === false);
check("terminal missing-history receipt never discards the local-only partial draft", !canDiscardRecoveredDraft(unsaved));
check("confirmed saved terminal reply can clear its browser draft", canDiscardRecoveredDraft(saved));
check("idle does not discard possibly local-only text", !canDiscardRecoveredDraft({ state: "idle", request: null, history_saved: null }));
check("unconfirmed terminal persistence fails closed", parseRunState({ state: "terminal", request, history_saved: null }, "session").state === "unknown");
check("phase label reflects actual queued stage", phaseLabel("queued") === "Waiting for the agent");
check("unrecognized phase does not invent progress", phaseLabel("almost_done") === "Waiting for a response");
check("input limit matches the API's explicit content bound", CHAT_INPUT_LIMIT === 50_000);
for (const code of ["chat_transport_error", "chat_stream_active", "request_already_submitted", "history_save_failed", "delivery_stopped", "stream_failed", "provider_timeout", "chat_run_timeout"])
  check(`${code} checks run/history before allowing another uncertain submission`, chatFailureNeedsRecovery({ code }));
check("known global capacity rejection does not lock this session as an active run", !chatFailureNeedsRecovery({ code: "chat_capacity_reached", history_saved: false }));
check("a saved output-limit error does not invent an uncertain transport", !chatFailureNeedsRecovery({ code: "output_budget_exhausted", history_saved: true }));

const calls: string[] = [];
const recovered = await recoverChatRun({
  sessionId: "session",
  readState: async () => { calls.push("GET status"); return Response.json(saved); },
  readHistory: async () => { calls.push("GET history"); return true; },
});
check("recovery uses only the two read operations and never retries a POST", calls.join() === "GET status,GET history" && recovered.state === "terminal");
const historyUnavailable = await recoverChatRun({ sessionId: "session", readState: async () => Response.json(saved), readHistory: async () => false });
check("failed history refresh keeps terminal recovery uncertain", historyUnavailable.state === "unknown" && !canDiscardRecoveredDraft(historyUnavailable));
const activeHistoryUnavailable = await recoverChatRun({ sessionId: "session", readState: async () => Response.json(active), readHistory: async () => false });
check("a confirmed active lease stays locked even if history refresh fails", activeHistoryUnavailable.state === "active");
const missingHistoryRow = await recoverChatRun({ sessionId: "session", readState: async () => Response.json(unsaved), readHistory: async () => true });
check("successful empty history read does not erase missing-persistence distinction", missingHistoryRow.history_saved === false && !canDiscardRecoveredDraft(missingHistoryRow));
let failedStatus = false;
try { await recoverChatRun({ sessionId: "session", readState: async () => new Response("", { status: 404 }), readHistory: async () => { throw new Error("Must not infer idle from 404"); } }); } catch { failedStatus = true; }
check("404 is not inferred to mean idle", failedStatus);
const background = { sessionId: "session" };
check("opening a finished chat from history shows no notice",
  !recoveryWorthShowing({ ...background, state: "terminal", historySaved: true })
  && !recoveryWorthShowing({ ...background, state: "idle" })
  && !recoveryWorthShowing({ ...background, state: "checking" }));
check("a run still going, an unknown outcome or an unsaved reply is shown",
  recoveryWorthShowing({ ...background, state: "active" })
  && recoveryWorthShowing({ ...background, state: "unknown" })
  && recoveryWorthShowing({ ...background, state: "terminal", historySaved: false }));
check("recovering a request sent from this browser always shows its state",
  recoveryWorthShowing({ ...background, originRequestId: "r1", state: "checking" })
  && recoveryWorthShowing({ ...background, originRequestId: "r1", state: "terminal", historySaved: true }));
console.log(`${checks} recovery checks passed`);
