import type { CognitiveMetadata, MessageUsageMeta } from "../types.ts";

export interface MetricDisplay {
  key: string;
  label: string;
  value: string;
  explanation: string;
}

const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0;
const count = (value: unknown): value is number => finite(value) && Number.isInteger(value);

/** These scores are heuristics, so never format them as accuracy percentages. */
export function cognitiveMetrics(cognitive: CognitiveMetadata): {
  pills: MetricDisplay[];
  details: MetricDisplay[];
} {
  const pills: MetricDisplay[] = [];
  const details: MetricDisplay[] = [];
  if (cognitive.qalb) {
    const noMatch =
      cognitive.qalb.state === "neutral" && !cognitive.qalb.signals?.length;
    pills.push({
      key: "qalb",
      label: "Qalb",
      value: noMatch ? "No tone match" : `${cognitive.qalb.state} hint`,
      explanation: noMatch
        ? "No tone keyword matched; neutral is the default, not a measured emotional state."
        : "A tone hint from keyword rules, not a measured emotional state.",
    });
    if (cognitive.qalb.signals?.length) {
      details.push({
        key: "tone_signals",
        label: "Matched tone words",
        value: cognitive.qalb.signals.join(", "),
        explanation: "",
      });
    }
  }
  if (cognitive.yaqin) {
    pills.push({
      key: "yaqin",
      label: "Yaqin",
      value: "Inference estimate",
      explanation: "An internal inference label; it does not measure whether the answer is correct.",
    });
    details.push({
      key: "inference",
      label: "Inference label",
      value: ({
        ilm_al_yaqin: "'Ilm (inference)",
        ayn_al_yaqin: "'Ayn (internal label)",
        haqq_al_yaqin: "Haqq (internal label)",
      })[cognitive.yaqin.level] ?? "Unrecognized internal label",
      explanation: cognitive.yaqin.evidence?.length
        ? `Recorded evidence labels: ${cognitive.yaqin.evidence.join(", ")}. These are not an accuracy evaluation.`
        : "No independent accuracy evaluation is attached to this label.",
    });
  }
  if (cognitive.lubb) {
    const labels: Record<string, string> = {
      confident: "Low concern",
      hedged: "Review suggested",
      uncertain: "Review needed",
    };
    pills.push({
      key: "lubb",
      label: "Lubb",
      value: labels[cognitive.lubb.quality] ?? "Text check",
      explanation: "A text-pattern assessment, not a factual accuracy check. A low-concern label can still accompany an incorrect answer.",
    });
    if (cognitive.lubb.bias_flags?.length) {
      details.push({
        key: "bias_flags",
        label: "Text-rule flags",
        value: cognitive.lubb.bias_flags.join(", "),
        explanation: "Potential patterns flagged by rules; not confirmed bias findings.",
      });
    }
  }
  if (finite(cognitive.ruh_energy) && cognitive.ruh_energy <= 100) {
    pills.push({
      key: "ruh",
      label: "Ruh workload",
      value: `${Math.round(cognitive.ruh_energy)}/100`,
      explanation: "An internal counter adjusted by estimated task complexity and idle time. It is not CPU usage, model training progress, or measured capability.",
    });
  }
  if (count(cognitive.nafs_level) && cognitive.nafs_level >= 1 && cognitive.nafs_level <= 7) {
    pills.push({
      key: "nafs",
      label: "Agent stage",
      value: `N${cognitive.nafs_level}${cognitive.nafs_name ? ` ${cognitive.nafs_name}` : ""}`,
      explanation: "An internal policy stage that controls available tools and turn limits; not a validated intelligence or learning level.",
    });
  }
  if (cognitive.cognitive_method) {
    details.push({
      key: "method",
      label: "Selected method",
      value: cognitive.cognitive_method,
      explanation: "The selected reasoning route, not a measurement of reasoning quality.",
    });
  }
  if (cognitive.mizan_label) {
    details.push({
      key: "mizan",
      label: "Mizan estimate",
      value: cognitive.mizan_label,
      explanation: "A label derived from the inference heuristic; not independent verification.",
    });
  }
  if (cognitive.lawwama) {
    const { errors, repair_level } = cognitive.lawwama;
    if (count(errors)) {
      details.push({
        key: "rule_flags",
        label: "Rule flags",
        value: String(errors),
        explanation: "Patterns detected by the self-check. Zero flags does not mean zero factual or execution errors.",
      });
    }
    if (count(repair_level)) {
      const repair = {
        key: "repair",
        label: "Repair stage",
        value: `L${repair_level}`,
        explanation: "The self-check's selected repair stage; it does not verify a successful repair.",
      };
      details.push(repair);
      if (repair_level > 0) pills.push(repair);
    }
    details.push({
      key: "accuracy",
      label: "Accuracy / hallucination rate",
      value: "Not measured",
      explanation: "Legacy health and hallucination scores use text rules and assumed inputs. They do not measure answer accuracy or server health.",
    });
  }
  return { pills, details };
}

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}

export function fmtLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

export function fmtCost(usd: number, estimated?: boolean): string {
  const body = usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
  return estimated ? `~${body}` : body;
}

export function usageMetrics(meta?: MessageUsageMeta): {
  parts: string[];
  explanations: string[];
} {
  if (!meta) return { parts: [], explanations: [] };
  const parts: string[] = [];
  const explanations: string[] = [];
  if (meta.model) parts.push(meta.model);
  const statuses: Record<string, string> = {
    abstained: "Abstained",
    incomplete: "Incomplete response",
    human_review_required: "Human review required",
    reviewed_memory: "Reviewed memory replay",
    evidence_observed: "Tool results observed",
    unverified_answer: "Answer not verified",
    missing_receipt: "Completion not confirmed",
    empty_response: "Empty response",
    tool_request: "Tool requested",
    failed: "Response failed",
  };
  const status = meta.owned_status === "abstained" ? "abstained" : meta.completion_status;
  if (status && statuses[status]) parts.push(statuses[status]);
  const counts = [
    count(meta.input_tokens) ? `${fmtTokens(meta.input_tokens)} in` : "",
    count(meta.output_tokens) ? `${fmtTokens(meta.output_tokens)} out` : "",
  ].filter(Boolean);
  if (counts.length) {
    parts.push(`${counts.join(" / ")} tokens`);
    const partial = meta.calls?.some((call) => !count(call.input_tokens) || !count(call.output_tokens));
    explanations.push(partial
      ? "Tokens are provider-reported counts. Some calls did not report complete usage, so these totals are partial."
      : "Tokens are provider-reported counts, summed across reported calls. Missing counts are not filled in.");
  }
  if (count(meta.reasoning_tokens)) {
    parts.push(`${fmtTokens(meta.reasoning_tokens)} reasoning`);
    explanations.push("Reasoning tokens are reported by the provider and may be included in the output-token total.");
  } else if (meta.reasoning_observed) {
    explanations.push("The provider indicated reasoning activity but did not report a reasoning-token count.");
  }
  if (count(meta.visible_output_tokens)) {
    explanations.push(`Non-reasoning tokens: ${fmtTokens(meta.visible_output_tokens)}, derived from reported output minus reasoning tokens. This can include tool calls, not just visible text.`);
  }
  if (meta.owned_checkpoint) {
    explanations.push(`Own-model checkpoint selected for this response: ${meta.owned_checkpoint.sha256} (${meta.owned_checkpoint.source}${meta.owned_checkpoint.generation != null ? `, generation ${meta.owned_checkpoint.generation}` : ""}). Selection does not establish a completed or correct answer.`);
  }
  if (finite(meta.timings?.total_ms)) {
    parts.push(`Agent time ${fmtLatency(meta.timings.total_ms)}`);
    explanations.push("Agent time is measured by Mizan from agent execution entry to return, including queue wait and candidate capture. API preparation and message saving are outside this interval.");
  }
  if (finite(meta.timings?.provider_ms)) {
    parts.push(`Model calls ${fmtLatency(meta.timings.provider_ms)}`);
    explanations.push("Model-call time is measured by Mizan around provider attempts, including failed attempts. It is not provider-reported latency or total task time.");
  } else if (finite(meta.latency_ms)) {
    parts.push(`Model calls ${fmtLatency(meta.latency_ms)}`);
    explanations.push("This legacy model-call time is measured by Mizan and summed over recorded calls. It may omit failed attempts and is not total task time.");
  }
  const intervals = [
    ["Queue wait", meta.timings?.queue_wait_ms],
    ["Active execution", meta.timings?.execution_ms],
    ["Tool batches", meta.timings?.tool_ms],
    ["Other execution", meta.timings?.other_execution_ms],
  ] as const;
  const breakdown = intervals.filter(([, value]) => finite(value))
    .map(([label, value]) => `${label}: ${fmtLatency(value as number)}`);
  if (breakdown.length) {
    explanations.push(`Measured intervals — ${breakdown.join("; ")}. Tool time is batch wall time, not summed parallel-tool durations.`);
  }
  if (finite(meta.cost_usd)) {
    parts.push(fmtCost(meta.cost_usd, meta.cost_estimated));
    explanations.push(meta.cost_estimated
      ? "Cost is estimated from a price table; it is not your actual bill."
      : "Cost is reported in the provider response.");
  }
  return { parts, explanations };
}
