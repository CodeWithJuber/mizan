import { dailySeries, isSummary, parseLimit, renewal, share, usd } from "./iqtisad.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

check("recognised", isSummary({ spent_usd: {}, limits_usd: {}, history: [], by_model: [] }));
check("not a summary", !isSummary({}) && !isSummary(null) && !isSummary([]));
check("small spend keeps its digits", usd(0.0042) === "$0.0042" && usd(1.5) === "$1.50" && usd(0) === "$0");
check("no value", usd(null) === "—" && usd(Number.NaN) === "—");
check("share of a limit", share(0.5, 2) === 0.25 && share(3, 2) === 1 && share(1, null) === null);
check("a zero limit is full", share(0, 0) === 1);
const series = dailySeries([{ day: "2026-10-26", cost_usd: 0.3, calls: 2 }], "2026-10-27", 3);
check(
  "missing days are zero, in order",
  series.map((entry) => `${entry.day}:${entry.cost_usd}`).join(",") ===
    "2026-10-25:0,2026-10-26:0.3,2026-10-27:0",
);
check("limits typed", parseLimit("") === null && parseLimit(" 2.5 ") === 2.5 && parseLimit("-1") === undefined);
check("not a number", parseLimit("abc") === undefined);
check("renewal in words", renewal("2026-10-28T00:00:00+05:30") === "28 Oct, 00:00" && renewal("") === "");

console.log(`iqtisad: ${checks} checks passed`);
