import { chatFailureFields, failureEnvelope, messageUsage, restoredMessageFields } from "./chatFailure.ts";

let checks = 0;
function check(name: string, ok: boolean) {
  if (!ok) throw new Error(name);
  checks++;
}
const event = {
  type: "error",
  request_id: "request-1",
  message_id: "message-1",
  code: "output_budget_exhausted",
  message: "The model reached its output limit before producing an answer. Try a smaller request or another model.",
  completion_status: "incomplete",
  answer_delivered: false,
  task_verified: false,
  usage: {
    model: "mizan-owned",
    input_tokens: 100,
    output_tokens: 200,
    reasoning_tokens: 200,
    visible_output_tokens: 0,
    timings: { provider_ms: 1200, total_ms: 2300, tool_ms: 0 },
    calls: [{ model: "mizan-owned", output_tokens: 200 }],
    owned_checkpoint: { source: "registry", sha256: "a".repeat(64), generation: 2 },
  },
};
const live = chatFailureFields(event);
check("empty failure does not invent answer text", live.content === "");
check("empty failure has a visible separate notice", live.error?.message === event.message);
check("terminal receipts are attached to live usage", live.meta?.completion_status === "incomplete" && live.meta.answer_delivered === false && live.meta.task_verified === false && live.meta.error_code === event.code);
check("failed provider counts remain inspectable", live.meta?.output_tokens === 200 && live.meta.reasoning_tokens === 200 && live.meta.visible_output_tokens === 0);
check("failure timings survive normalization", live.meta?.timings?.provider_ms === 1200 && live.meta.timings.total_ms === 2300);
check("failure checkpoint and call receipts survive", live.meta?.owned_checkpoint?.generation === 2 && live.meta.calls?.[0].output_tokens === 200);
check("failed response still identifies the selected model", live.model === "mizan-owned");
check("live failure retains stable transport identities", live.requestId === "request-1" && live.messageId === "message-1");

const partial = "  Partial answer\n```python\nprint('unfinished')\n";
const partialFailure = chatFailureFields(event, partial);
check("partial text is byte-for-byte preserved", partialFailure.content === partial);
check("error notice stays outside an unfinished markdown fence", partialFailure.content === partial && !partialFailure.content.includes(event.message) && partialFailure.error?.message === event.message);
check("longer buffered prefix survives a shorter server partial", chatFailureFields({ ...event, response: "  Partial" }, partial).content === partial);
check("longer saved partial can restore tokens absent from buffer", chatFailureFields({ ...event, content: partial }, "  Partial").content === partial);
check("unknown error keeps its safe API notice", chatFailureFields({ code: "agent_failed", message: "The request failed safely." }).error?.message === "The request failed safely.");
check("legacy failure fallback is visible without invented measurements", Boolean(chatFailureFields({}).error?.message) && chatFailureFields({}).meta === undefined);
check("legacy output-limit failure gets the known safe message", chatFailureFields({ code: event.code }).error?.message === event.message);

const restored = restoredMessageFields("", { ...event, status: "error", partial: true });
check("empty stored failure renders the same notice as live", restored.content === "" && restored.error?.message === live.error?.message);
check("stored failure restores usage and completion receipt", JSON.stringify(restored.meta) === JSON.stringify(live.meta));
check("stored failure retains identities for resync", restored.requestId === live.requestId && restored.messageId === live.messageId);
check("failure history is not mislabeled user-stopped", restored.stopped === false);
const restoredPartial = restoredMessageFields(partial, { ...event, status: "error", partial: true });
check("stored partial failure preserves both text and notice", restoredPartial.content === partial && restoredPartial.error?.message === event.message && restoredPartial.stopped === false);
const cancelled = restoredMessageFields(partial, { status: "cancelled", partial: true });
check("server cancellation is interrupted without falsely claiming user Stop", cancelled.interrupted === true && cancelled.stopped === false && cancelled.error === undefined);
const emptyCancelled = restoredMessageFields("", { status: "cancelled", completion_status: "incomplete", answer_delivered: false });
check("empty cancelled history retains interruption and incomplete receipt", emptyCancelled.interrupted === true && emptyCancelled.content === "" && emptyCancelled.meta?.completion_status === "incomplete" && emptyCancelled.stopped === false);
check("normal history is not turned into a failure", restoredMessageFields("Answer", { usage: event.usage }).error === undefined && restoredMessageFields("Answer").meta === undefined);

const corrected = messageUsage({ ...event, usage: { ...event.usage, completion_status: "evidence_observed", task_verified: true } });
check("final receipt overrides stale usage receipt", corrected?.completion_status === "incomplete" && corrected.task_verified === false);
check("normalizing does not mutate original usage", !("completion_status" in event.usage));
check("absent telemetry does not fabricate zero counters", messageUsage({}) === undefined);
check("direct canonical JSON error is recognized", failureEnvelope(event) === event);
check("nested HTTP error is recognized", failureEnvelope({ detail: event }) === event);
check("ordinary HTTP detail stays an HTTP failure", failureEnvelope({ detail: "Unauthorized" }) === undefined);
check("non-object JSON does not become a chat failure", failureEnvelope(null) === undefined && failureEnvelope([]) === undefined);
console.log(`${checks} failure/history checks passed`);
