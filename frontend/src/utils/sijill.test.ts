import { ago, mergeNotes, type LearningNote } from "./sijill.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const note = (seq: number): LearningNote => ({ seq, at: 1000 + seq, kind: "hifz", summary: `note ${seq}` });
const merged = mergeNotes([note(2), note(1)], [note(3), note(2), note(4)]);
check("newest first, no duplicates", merged.map((n) => n.seq).join(",") === "4,3,2,1");
check("capped", mergeNotes([], [note(1), note(2), note(3)], 2).length === 2);
check("seconds", ago(100, 130) === "30s ago");
check("minutes", ago(0, 125) === "2m ago");
check("hours and days", ago(0, 7200) === "2h ago" && ago(0, 172800) === "2d ago");

console.log(`sijill: ${checks} checks passed`);
