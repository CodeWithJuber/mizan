import { learnedCount, percent, workRows, type RoutingRow } from "./tadbirLearning.ts";

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

console.log(`tadbirLearning: ${checks} checks passed`);
