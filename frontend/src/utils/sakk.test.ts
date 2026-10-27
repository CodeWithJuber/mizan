import { isReceipts, outcomeTone, verdictLine } from "./sakk.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

check("intact chain", verdictLine({ ok: true, receipts: 3 }).startsWith("All 3 receipts verify"));
check("empty chain", verdictLine({ ok: true, receipts: 0 }) === "No receipts yet.");
check(
  "broken chain names the receipt",
  verdictLine({ ok: false, receipts: 3, broken_at: 2, problem: "receipt was changed" }) ===
    "Receipt 2 does not verify: receipt was changed.",
);
check("tones", outcomeTone("done") === "good" && outcomeTone("held") === "held" && outcomeTone("declined") === "bad" && outcomeTone(undefined) === "plain");
check("shape", isReceipts({ receipts: [], public_key: "k" }) && !isReceipts({ receipts: [] }) && !isReceipts(null));

console.log(`sakk: ${checks} checks passed`);
