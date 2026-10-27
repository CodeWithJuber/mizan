import {
  armBadges,
  diffRows,
  formatCost,
  formatMs,
  opLabel,
  spanSummary,
  spanTree,
  type CompareChecks,
  type TraceSpan,
} from "./debugTrace.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const span = (id: string, parent: string | null, op: string, name: string, start: number, attributes = {}): TraceSpan => ({
  id, parent, op, name, start_ms: start, duration_ms: 1, status: "ok", attributes,
});

const tree = spanTree([
  span("c", "b", "chat", "lisan.write_code", 5),
  span("a", null, "understand", "build_and_run", 0, { language: "en", by: "fahm" }),
  span("b", null, "invoke_agent", "Katib", 2),
  span("d", "b", "execute_tool", "workspace_run", 9, { ok: true }),
  span("e", "missing", "verify", "furqan", 12, { accepted: false, problems: ["number 9 is not in MIZAN's facts"] }),
]);
check("roots first in start order", tree.map(({ span }) => span.id).join("") === "abcde");
check("children are indented", tree[2].depth === 1 && tree[3].depth === 1 && tree[1].depth === 0);
check("an unknown parent is shown at the top", tree[4].depth === 0);
check("Lisan calls are named", opLabel(tree[2].span) === "Lisan" && opLabel(tree[1].span) === "Agent");
check("understand summary", spanSummary(tree[0].span) === "build_and_run · en · by fahm");
check("rejected check says why", spanSummary(tree[4].span).startsWith("rejected: number 9"));
check("tool summary", spanSummary(tree[3].span) === "ran");

check("ms", formatMs(250) === "250 ms" && formatMs(2500) === "2.5 s" && formatMs(undefined) === "—");
check("cost", formatCost(0.0012, true) === "~$0.00120" && formatCost(0.5) === "$0.500" && formatCost(undefined) === "—");

const report: CompareChecks = {
  intent: "compute",
  grounded: true,
  base: { unsupported_numbers: ["1267650600228229401496703205377"], unbacked_action_claims: [], abstained: false, characters: 40 },
  mizan: { unsupported_numbers: [], unbacked_action_claims: [], abstained: false, characters: 60 },
  agreement: { verified_values: ["1267650600228229401496703205376"], base_states: [], share: 0 },
  similarity: 0.4,
  diff: ["--- base model", "+++ MIZAN", "@@ -1 +1 @@", "-a", "+b", " c"],
};
const base = armBadges(report, "base");
check("unsupported numbers are flagged", base.some((b) => b.tone === "bad" && b.label.includes("no fact")));
check("agreement shown for the base arm", base.some((b) => b.label.includes("0% of MIZAN's verified")));
check("clean MIZAN arm", armBadges(report, "mizan")[0].label === "Nothing unsupported");
const quoted = armBadges({ ...report, agreement: undefined, quote: { status: "differs", coverage: 0.4, precision: 0.4, words: 4 } }, "base");
check("quote verdict", quoted.some((b) => b.label === "Quote differs from the source" && b.tone === "bad"));
const close = armBadges({ ...report, agreement: undefined, quote: { status: "close", coverage: 0.1, precision: 0.86, words: 69, changed: [{ source: "وانما لكل", given: "ولكل" }] } }, "base");
check("wording changes counted", close.some((b) => b.label === "Quote has 1 wording change(s) from the source"));
const excerpt = armBadges({ ...report, agreement: undefined, quote: { status: "excerpt", coverage: 0.25, precision: 1, words: 8 } }, "base");
check("excerpt", excerpt.some((b) => b.label === "Quotes 25% of the text, word for word" && b.tone === "info"));

const rows = diffRows(report.diff);
check("diff headers dropped", rows.length === 4);
check("diff kinds", rows.map((row) => row.kind).join(",") === "hunk,del,add,same");

console.log(`debugTrace: ${checks} checks passed`);
