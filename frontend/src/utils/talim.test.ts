import { isTalimView, parseExamples, parseLabelMap, verdict, type TalimReport } from "./talim.ts";

let passed = 0;
function check(name: string, ok: boolean) {
  if (!ok) throw new Error(`talim: ${name}`);
  passed += 1;
}

const parsed = parseExamples("compute | 2 ki power 10\nconverse\tSalaam\n\nbad line\nnope | x", [
  "compute",
  "converse",
]);
check("two examples", parsed.examples.length === 2 && parsed.examples[1].text === "Salaam");
check("errors name the lines", parsed.errors.length === 2 && parsed.errors[0].startsWith("Line 4"));
check("a new language label is allowed", parseExamples("ta | வணக்கம்", ["en"], true).examples.length === 1);
check("label map", JSON.stringify(parseLabelMap("0 = no\n1=yes")) === '{"0":"no","1":"yes"}');
check("bad label map", parseLabelMap("0 no") === null && parseLabelMap("") === null);
const report: TalimReport = {
  examples: 10,
  seeds_scored: 100,
  before: 0.9,
  after: 0.91,
  p_worse: 0.02,
  kept: true,
  learned: 0.8,
  changed_classes: {},
};
check("kept verdict", verdict(report).startsWith("Kept: 90.0% → 91.0%"));
check("refused verdict", verdict({ ...report, kept: false, p_worse: 0.97 }).startsWith("Refused: P(worse) = 0.970"));
check("view", isTalimView({ models: {}, batches: [] }) && !isTalimView({ models: {} }));
console.log(`talim: ${passed} checks passed`);
