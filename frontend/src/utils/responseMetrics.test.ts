import type { CognitiveMetadata } from "../types.ts";
import { cognitiveMetrics, usageMetrics } from "./responseMetrics.ts";

let passed = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(`FAIL: ${name}`);
  passed += 1;
}

// Historical screenshot payload has no provenance field. It must still be honest.
const screenshot: CognitiveMetadata = {
  qalb: { state: "neutral", confidence: 0.5, recommended_tone: "standard", signals: [] },
  yaqin: { level: "ilm_al_yaqin", confidence: 0.5, source: "agentic_reasoning", evidence: [] },
  lubb: { quality: "confident", coherence_score: 1, bias_flags: [] },
  ruh_energy: 81,
  nafs_level: 3,
  nafs_name: "Mulhama",
  cognitive_method: "tafakkur",
  mizan_label: "Zann — Probable inference",
  lawwama: { health: 1, hallucination_score: 0.3, repair_level: 0, errors: 0 },
};
const display = cognitiveMetrics(screenshot);
const values = [...display.pills, ...display.details].map((item) => `${item.label}: ${item.value}`).join("\n");
check("legacy percentages are not rendered as measured facts", !values.includes("%"));
check("default neutral does not claim a measured emotion", display.pills.find((item) => item.key === "qalb")?.value === "No tone match");
check("fixed inference score is labeled an estimate", display.pills.find((item) => item.key === "yaqin")?.value === "Inference estimate");
check("confident text label is not asserted as factual confidence", !values.includes("confident"));
check("workload remains visible as an internal counter", values.includes("Ruh workload: 81/100"));
check("policy stage remains visible", values.includes("Agent stage: N3 Mulhama"));
check("hallucination rate is explicitly unmeasured", display.details.find((item) => item.key === "accuracy")?.value === "Not measured");
check("zero rule flags is not labeled zero errors", values.includes("Rule flags: 0") && !values.includes("Errors: 0"));
check("zero rule flags includes limits", display.details.find((item) => item.key === "rule_flags")?.explanation.includes("does not mean zero") === true);
check("a self-check-only payload is still explained", cognitiveMetrics({ lawwama: screenshot.lawwama }).details.length > 0);
check("missing cognitive values are not invented", cognitiveMetrics({}).pills.length === 0 && cognitiveMetrics({}).details.length === 0);
check("invalid workload is omitted", !cognitiveMetrics({ ruh_energy: NaN }).pills.length && !cognitiveMetrics({ ruh_energy: 140 }).pills.length);
const changed = cognitiveMetrics({ ...screenshot, ruh_energy: 36 });
check("dynamic workload change is reflected", changed.pills.find((item) => item.key === "ruh")?.value === "36/100");

check("missing usage does not invent zeroes", usageMetrics().parts.length === 0);
const partial = usageMetrics({ output_tokens: 19 });
check("missing input count remains absent", partial.parts.join().includes("19 out tokens") && !partial.parts.join().includes(" in"));
check("actual reported zero remains visible", usageMetrics({ input_tokens: 0 }).parts.includes("0 in tokens"));
check("non-finite or negative telemetry is hidden", usageMetrics({ input_tokens: NaN, output_tokens: -1, latency_ms: Infinity, cost_usd: -1 }).parts.length === 0);
check("fractional token counts are not presented as valid counts", usageMetrics({ input_tokens: 3.5 }).parts.length === 0);
const oldTiming = usageMetrics({ latency_ms: 1200 });
check("legacy timing is identified as model-call time", oldTiming.parts.includes("Model calls 1.2s"));
check("legacy timing does not claim provider measurement", oldTiming.explanations.join().includes("measured by Mizan"));
check("legacy timing acknowledges missing failed attempts", oldTiming.explanations.join().includes("may omit failed attempts"));
const measured = usageMetrics({
  latency_ms: 1200,
  timings: { provider_ms: 3400, total_ms: 8000, queue_wait_ms: 2000, execution_ms: 6000, tool_ms: 1000, other_execution_ms: 1600 },
});
check("full provider-attempt timer replaces legacy subset", measured.parts.includes("Model calls 3.4s") && !measured.parts.includes("Model calls 1.2s"));
check("agent duration stays distinct from provider calls", measured.parts.includes("Agent time 8.0s"));
check("queue/tool sources remain inspectable", measured.explanations.join().includes("Queue wait: 2.0s") && measured.explanations.join().includes("Tool batches: 1.0s"));
check("agent timer scope is explicit", measured.explanations.join().includes("API preparation and message saving are outside"));
const estimated = usageMetrics({ cost_usd: 0.0012, cost_estimated: true });
check("estimated cost is visibly marked", estimated.parts.includes("~$0.0012"));
check("reported cost is not called an estimate", usageMetrics({ cost_usd: 0.0012, cost_estimated: false }).explanations.includes("Cost is reported in the provider response."));
check("partial aggregated token counts are disclosed", usageMetrics({ input_tokens: 10, calls: [{ input_tokens: 10 }, {}] }).explanations.join().includes("totals are partial"));
check("unverified completion is labeled", usageMetrics({ completion_status: "unverified_answer" }).parts.includes("Answer not verified"));
const reasoning = usageMetrics({ output_tokens: 1200, reasoning_tokens: 1000, visible_output_tokens: 200 });
check("reported reasoning tokens remain distinct", reasoning.parts.includes("1.0k reasoning"));
check("derived non-reasoning count is not claimed to be visible text", reasoning.explanations.join().includes("can include tool calls, not just visible text"));
check("reasoning signal does not invent a token count", !usageMetrics({ reasoning_observed: true }).parts.some((part) => part.includes("reasoning")));
const checkpoint = usageMetrics({ model: "mizan-owned", owned_checkpoint: { source: "registry", sha256: "a".repeat(64), generation: 2 } });
check("actual checkpoint receipt remains inspectable", checkpoint.explanations.join().includes("generation 2") && checkpoint.explanations.join().includes("a".repeat(64)));
console.log(`responseMetrics: ${passed} checks passed`);
