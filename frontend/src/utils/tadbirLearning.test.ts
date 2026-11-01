import { learnedCount, percent, shareText, topFamilies, workRows, type RoutingRow } from "./tadbirLearning.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const row = (agent: string, intent: string, estimate: number, evidence = 0): RoutingRow => ({
  agent, role: agent.toLowerCase(), intent, success_estimate: estimate, evidence, specialist: false,
});
const rows = [
  row("Khalifah", "run_code", 0.71),
  row("Katib", "run_code", 0.9, 3),
  row("Khalifah", "hadith", 0.9, 2),
  row("Katib", "hadith", 0.33),
  row("Mystery", "new_kind", 0.5),
];
const table = workRows(rows);

check("one row per kind of work", table.length === 3);
check("known kinds come first in a fixed order", table[0].intent === "run_code" && table[1].intent === "hadith");
check("unknown kinds still show", table[2].label === "new_kind");
check("the most trusted agent leads", table[0].leader === "Katib" && table[1].leader === "Khalifah");
check("evidence adds up across agents", table[0].evidence === 3);
check("the others are listed", table[0].others[0].agent === "Khalifah");
check("percent rounds", percent(0.714) === "71%");
check("one result is singular", learnedCount(0.98) === "1 result learned" && learnedCount(2.6) === "3 results learned");

const families = topFamilies(
  [
    { family: "converse", language: "en", requests: 3, zero_call: 0, zero_call_share: 0, interval: [0, 0.56] },
    { family: "compute", language: "ur", requests: 9, zero_call: 9, zero_call_share: 1, interval: [0.7, 1] },
    { family: "mystery", language: "ar", requests: 1, zero_call: 1, zero_call_share: 1, interval: [0.21, 1] },
  ],
  2,
);
check("families: most answers first, limited", families.length === 2 && families[0].family === "compute");
check("families are labelled", families[0].label === "Calculate" && families[1].label === "Conversation");
check("a share reads with its interval", shareText(0.62, [0.48, 0.75]) === "62% (48%–75%)");
check("no answers yet", shareText(null, null) === "no answers yet");

console.log(`tadbirLearning: ${checks} checks passed`);
