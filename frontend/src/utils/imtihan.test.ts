import { blockRows, historyPoints, intervalText, pct, signed, taskRows, type Report, type ResultRow, type RunSummary } from "./imtihan.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const arm = (rate: number | null) => ({ scored: 4, errors: 0, passed: 2, rate, interval: [0.15, 0.85] as [number, number], pass_at_1: rate, pass_all: rate });
const report: Report = {
  blocks: {
    exactness: { tasks: 4, base: arm(0.5), mizan: arm(1), delta: 0.5 },
    mystery: { tasks: 4, base: arm(null), mizan: arm(0.25), delta: null },
  },
  index: { base: { score: 0.5, pooled: 0.5, interval: [0.2, 0.8] }, mizan: { score: 0.625, pooled: 0.6, interval: [0.3, 0.9] } },
  calibration: { base: { ece: 0.1, brier: 0.2, answers_with_confidence: 4, answers: 4 }, mizan: { ece: 0.05, brier: 0.1, answers_with_confidence: 4, answers: 4 } },
  consistency: { base: { groups: 3, consistent: 1, rate: 0.333 }, mizan: { groups: 3, consistent: 3, rate: 1 } },
  cost: { base: { input_tokens: 1, output_tokens: 1, cost_usd: null, latency_ms: 1, model_calls: 1, tool_calls: 0 }, mizan: { input_tokens: 1, output_tokens: 1, cost_usd: null, latency_ms: 1, model_calls: 0, tool_calls: 1 } },
};
const rows = blockRows(report);
check("labels", rows[0].label === "Exact answers" && rows[1].label === "mystery");
check("pct", pct(0.625) === "63%" && pct(null) === "—");
check("signed", signed(0.5) === "+50 pts" && signed(-0.1) === "-10 pts" && signed(null) === "—");
check("interval", intervalText([0.15, 0.85]) === "95% interval 15–85%");

const runs: RunSummary[] = [
  { id: "b", created_at: 2_000_000, status: "complete", model: "m", repeats: 1, blocks: null, index: report.index },
  { id: "a", created_at: 1_000_000, status: "complete", model: "m", repeats: 1, blocks: null, index: report.index },
  { id: "c", created_at: 3_000_000, status: "running", model: "m", repeats: 1, blocks: null, index: null },
];
const points = historyPoints(runs);
check("history keeps completed runs, oldest first", points.map((p) => p.id).join("") === "ab");
check("history values are percents", points[0].mizan === 63 && points[0].base === 50);

const results: ResultRow[] = [
  { task_id: "t1", block: "exactness", arm: "base", attempt: 1, pass: false, detail: "expects 4" },
  { task_id: "t1", block: "exactness", arm: "base", attempt: 2, pass: true },
  { task_id: "t1", block: "exactness", arm: "mizan", attempt: 1, pass: true, detail: "expects 4" },
  { task_id: "t1", block: "exactness", arm: "mizan", attempt: 2, pass: true },
  { task_id: "t2", block: "exactness", arm: "base", attempt: 1, pass: false, error: "RateLimitError" },
];
const table = taskRows(results, [{ id: "t1", block: "exactness", prompt: "2+2" }, { id: "t2", block: "exactness", prompt: "x" }]);
check("passes counted across attempts", table[0].base.passed === 1 && table[0].base.scored === 2 && table[0].mizan.passed === 2);
check("first attempt detail", table[0].base.detail === "expects 4");
check("errors are not failures", table[1].base.error && table[1].base.scored === 0 && table[1].base.detail === "RateLimitError");
check("no rows", table[1].mizan.scored === 0 && !table[1].mizan.error);

console.log(`imtihan: ${checks} checks passed`);
