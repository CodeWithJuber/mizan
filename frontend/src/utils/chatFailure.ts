import type { ChatMessage, MessageUsageMeta } from "../types.ts";

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

/** Completion receipts live beside usage in both live events and stored metadata. */
export function messageUsage(event: Record<string, unknown>): MessageUsageMeta | undefined {
  const usage: MessageUsageMeta = record(event.usage) ? { ...event.usage } : {};
  const statuses = new Set([
    "abstained", "unverified_answer", "evidence_observed", "incomplete",
    "human_review_required", "reviewed_memory", "missing_receipt", "empty_response",
    "tool_request", "failed",
  ]);
  if (typeof event.completion_status === "string" && statuses.has(event.completion_status))
    usage.completion_status = event.completion_status as MessageUsageMeta["completion_status"];
  if (typeof event.answer_delivered === "boolean") usage.answer_delivered = event.answer_delivered;
  if (typeof event.task_verified === "boolean") usage.task_verified = event.task_verified;
  if (typeof event.finish_reason === "string") usage.finish_reason = event.finish_reason;
  if (typeof event.code === "string") usage.error_code = event.code;
  return Object.keys(usage).length ? usage : undefined;
}

/** Preserve answer bytes separately from a terminal failure notice. */
export function chatFailureFields(
  event: Record<string, unknown>,
  buffered = "",
): Pick<ChatMessage, "content" | "error" | "meta" | "model" | "requestId" | "messageId"> {
  const saved = typeof event.response === "string" ? event.response
    : typeof event.content === "string" ? event.content : "";
  const content = !saved || buffered.startsWith(saved) ? buffered : saved;
  const code = typeof event.code === "string" ? event.code : undefined;
  const message = typeof event.message === "string" && event.message.trim()
    ? event.message
    : code === "output_budget_exhausted"
      ? "The model reached its output limit before producing an answer. Try a smaller request or another model."
      : "The response could not be completed. Any partial text is preserved.";
  const meta = messageUsage(event);
  return {
    content, error: { code, message }, meta, model: meta?.model,
    requestId: typeof event.request_id === "string" ? event.request_id : undefined,
    messageId: typeof event.message_id === "string" ? event.message_id : undefined,
  };
}

/** History uses the same error/receipt mapping as live responses. */
export function restoredMessageFields(
  content: string,
  metadata: Record<string, unknown> = {},
): Pick<ChatMessage, "content" | "error" | "meta" | "model" | "stopped" | "interrupted" | "requestId" | "messageId"> {
  const failure = metadata.status === "error"
    ? chatFailureFields({ ...metadata, content }) : undefined;
  const meta = failure?.meta ?? messageUsage(metadata);
  return {
    content, meta, model: meta?.model, error: failure?.error,
    requestId: typeof metadata.request_id === "string" ? metadata.request_id : undefined,
    messageId: typeof metadata.message_id === "string" ? metadata.message_id : undefined,
    // "cancelled" also includes broken transports/producer shutdown. Only the
    // local Stop action has evidence for the user-stopped label.
    stopped: false,
    interrupted: !failure && (metadata.status === "cancelled" || metadata.partial === true),
  };
}

/** JSON failures may be returned directly or inside an HTTP detail object. */
export function failureEnvelope(body: unknown): Record<string, unknown> | undefined {
  if (!record(body)) return;
  const candidate = record(body.detail) ? body.detail : body;
  if (candidate.type === "error" || candidate.code === "output_budget_exhausted" || candidate.code === "agent_failed")
    return candidate;
  if (["chat_stream_active", "request_already_submitted", "chat_capacity", "chat_capacity_reached"].includes(String(candidate.code)))
    return candidate;
}
