import { isSidq, sidqHeadline, sidqLines, type SidqReport } from "./sidq.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const report: SidqReport = {
  mode: "strict",
  corrected: [{ kind: "arithmetic", detail: "12 * 12 = 144 (not 154)" }],
  removed: [{ kind: "action", detail: "I ran the code." }, { kind: "link", detail: "https://made-up.example" }],
  flagged: [],
};
check("recognised", isSidq(report));
check("a passed gate is not shown", !isSidq({ mode: "strict", passed: true }) && !isSidq(null));
check("nothing to show", !isSidq({ ...report, corrected: [], removed: [] }));
check("headline", sidqHeadline(report) === "Truth Gate: 1 corrected, 2 removed");
check("lines", sidqLines(report)[0] === "Arithmetic corrected: 12 * 12 = 144 (not 154)");
check("flag mode", sidqHeadline({ ...report, corrected: [], removed: [], flagged: [{ kind: "quote", detail: "x" }] }) === "Truth Gate: 1 marked");

console.log(`sidq: ${checks} checks passed`);
