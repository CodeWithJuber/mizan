import { checkLine, isReceipt, removedLine, type MahwReceipt } from "./mahw.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const clean: MahwReceipt = {
  kind: "chat",
  removed: { "chat messages": 12, "chat summary": 1, notes: 0, "task records": 3 },
  checked: 240,
  traces: 0,
};
check("recognised", isReceipt(clean) && !isReceipt({}) && !isReceipt(null));
check("only what was removed", removedLine(clean) === "chat messages 12 · chat summary 1 · task records 3");
check("a clean check", checkLine(clean) === "Checked 240 times across your stores: nothing of it is left.");
const left = { ...clean, traces: 2, traces_by_store: { notes: 2 } };
check("copies left are named", checkLine(left).includes("2 copies remain in notes"));
check("one copy", checkLine({ ...clean, traces: 1, traces_by_store: { notes: 1 } }).includes("1 copy remains"));

console.log(`mahw: ${checks} checks passed`);
