import { ahlHeadline, ahlLines, isAhl, type AhlReport } from "./ahl.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const report: AhlReport = {
  checked: 3,
  supported: [
    {
      claim: "Titan is Saturn's largest moon.",
      verdict: "supported",
      title: "Titan (moon)",
      url: "https://en.wikipedia.org/wiki/Titan_(moon)",
      source: "wikipedia",
    },
  ],
  contradicted: [{ claim: "It was found in 1672.", verdict: "contradicted", title: "Titan (moon)", source: "ilm" }],
  unknown: 1,
};
check("recognised", isAhl(report));
check("not a report", !isAhl(null) && !isAhl({ checked: 1 }));
check("headline", ahlHeadline(report) === "Sources asked: 1 confirmed, 1 contradicted, 1 not found");
check(
  "nothing settled",
  ahlHeadline({ checked: 2, supported: [], contradicted: [], unknown: 2 }) ===
    "Sources asked: 2 not found — the model's own words, Allahu a'lam",
);
check("ruling only", ahlHeadline({ checked: 0, supported: [], contradicted: [], unknown: 0, ruling: true }).includes("scholar"));
const lines = ahlLines(report);
check("lines", lines.length === 2 && lines[0].text.startsWith("Confirmed: Titan") && lines[0].text.includes("Wikipedia"));
check("source label", lines[1].text.includes("settled before") && lines[1].url === undefined);

console.log(`ahl: ${checks} checks passed`);
