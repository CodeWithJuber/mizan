import { agenticRows, blockRows, categoryRows, facultyPoints, gameRows, historyPoints, patternText, plainArms, intervalText, pct, percentileText, signed, taskRows, type FacultyEntry, type Report, type ResultRow, type RunSummary } from "./imtihan.ts";

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

const weighted: Report = {
  ...report,
  weighted: {
    categories: {
      coding: { weight: 0.2, blocks: ["agent_coding"], base: 0.5, mizan: 1 },
      agents: { weight: 0.3, blocks: ["agent_web"], base: 0.75, mizan: 0.875 },
    },
    base: 0.65,
    mizan: 0.925,
  },
  agentic: {
    base: { tasks: 10, success: 0.7, objectives: 0.86, tool_accuracy: 1, groundedness: 1, recovery: 1, guardrail_violations: 0, latency_median_ms: 7871.5, tool_calls: 39 },
    mizan: { tasks: 10, success: 0.9, objectives: 0.95, tool_accuracy: 1, groundedness: 1, recovery: 1, guardrail_violations: 0, latency_median_ms: 5244.7, tool_calls: 43 },
  },
};
check("categories by weight", categoryRows(weighted)[0].label === "Agents" && categoryRows(weighted)[1].weight === 0.2);
check("no categories in an old report", categoryRows(report).length === 0 && agenticRows(report).length === 0);
const dims = agenticRows(weighted);
check("agentic success", dims[0].base === "70%" && dims[0].mizan === "90%");
check("latency in seconds, lower is better", dims[6].mizan === "5.2 s" && !dims[6].higher);

const played: Report = { ...report, games: { mizan: { games: 3, won: 3, levels: 1, efficiency: 0.5, actions: 81, model_calls: 0 } } };
check("game rows", gameRows(played)[0].mizan === "3/3" && gameRows(played)[0].base === "—" && gameRows(report).length === 0);
const arms = plainArms({
  prompt: "Count errors",
  agentic: {
    base: { text: "E101", objectives: [{ check: "errors.csv exists", pass: false }], calls: [{ name: "workspace_read" }] },
    mizan: { text: "E101: 9", objectives: [{ check: "errors.csv exists", pass: true }], calls: [{ name: "web_browse", error: "HTTP 404" }] },
  },
});
check("plain arms", arms !== null && arms.arms.length === 2 && arms.arms[1].checks[0].pass);
check("failed calls are named", arms!.arms[1].calls[0] === "web_browse (failed: HTTP 404)");
check("a debug run is not plain", plainArms({ prompt: "x", base: {}, mizan: {} }) === null);

const facultyArm = (rate: number | null, human: FacultyEntry["mizan"]["human"] = null) => ({ scored: rate == null ? 0 : 10, passed: rate == null ? 0 : Math.round(rate * 10), rate, interval: [0.2, 0.8] as [number, number], human });
const faculty = (key: string, rate: number | null, items = 10, panel: FacultyEntry["panel"] = null): FacultyEntry => ({
  key, name: key, arabic: "", script: "", ayah: "1:1", words: "", composite: false, items, blocks: [key],
  base: facultyArm(rate), mizan: facultyArm(rate), delta: 0, panel, anchors: [],
});
const profile = {
  framework: "f", translation: "t", levels_source: "l", propensity: {}, panel_people: 0,
  faculties: [faculty("reasoning", 0.5), faculty("memory", null), faculty("attention", 0.25, 0), faculty("social", 1, 10, { people: 3, mean: 0.7, median: 0.75 })],
};
const axes = facultyPoints(profile);
check("faculty points skip empty axes", axes.length === 3 && axes[0].base === 50 && axes[1].mizan === null);
check("panel median in percent", axes[2].panel === 75 && axes[0].panel === null);
check("no panel", percentileText(null) === "no panel answers yet");
check("pattern incomplete", patternText({ measured: 4, above_median: 2, top_percentile: 0, shape: "incomplete" }).includes("4 of 10"));
check("pattern partial", patternText({ measured: 10, above_median: 7, top_percentile: 0, shape: "below_median_somewhere" }).endsWith("on 7 of 10 faculties"));
check("pattern all", patternText({ measured: 10, above_median: 10, top_percentile: 0, shape: "above_median_everywhere" }).includes("all ten"));
check(
  "percentile text",
  percentileText({ people: 10, percentile: 0.6, interval: [0.31, 0.83], level: "competent" }) ===
    "outperforms 60% of 10 (95% interval 31–83%), Competent",
);

console.log(`imtihan: ${checks} checks passed`);
