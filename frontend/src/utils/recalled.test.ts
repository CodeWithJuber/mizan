import { recalledHeadline, recalledLines } from "./recalled.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const lines = recalledLines([
  { session_id: "a", created_at: "2026-10-20T08:00:00Z", content: "My daughter is Maryam" },
  { session_id: "b", created_at: "2026-10-21T08:00:00Z", content: "I live in Pune" },
  { session_id: "b", created_at: "2026-10-21T08:01:00Z", content: "  " },
  "not a line",
]);
check("only real lines", lines.length === 2);
check("count and chats", recalledHeadline(lines) === "Used 2 lines from 2 other chats");
check("one line", recalledHeadline(lines.slice(0, 1)) === "Used 1 line from another chat");
check("nothing", recalledLines(undefined).length === 0 && recalledLines({}).length === 0);

console.log(`recalled: ${checks} checks passed`);
