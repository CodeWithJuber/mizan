import { GRADES, headline, isIsnad, segments, type IsnadSummary } from "./isnad.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const summary: IsnadSummary = {
  counts: { sahih: 3, hasan: 0, daif: 1, mawdu: 0 },
  claims: 4,
  supported: 0.75,
  ledger: [
    { text: "2**100 = 1267650600228229401496703205376", kind: "sentence", grade: "sahih", support: ["MIZAN calculated it exactly"] },
    { text: "That is a big number.", kind: "sentence", grade: "daif", support: ["the language model's words only"] },
  ],
};
check("recognised", isIsnad(summary) && !isIsnad({ claims: 1 }) && !isIsnad(null));
const bars = segments(summary);
check("segments skip empty grades", bars.length === 2 && bars[0].grade === "sahih" && bars[0].share === 0.75);
check("headline", headline(summary) === "3 sahih · 1 da'if");
check("no claims, no segments", segments({ ...summary, claims: 0 }).length === 0);
check("every grade has an icon and a label", Object.values(GRADES).every((g) => g.icon && g.label && g.meaning));

console.log(`isnad: ${checks} checks passed`);
