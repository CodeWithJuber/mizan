import { historySeries, isPublicView, short } from "./reliability.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const index = (base: number, mizan: number) => ({
  base: { score: base, pooled: base, interval: [0, 1] as [number, number] },
  mizan: { score: mizan, pooled: mizan, interval: [0, 1] as [number, number] },
});
const series = historySeries([
  { run_id: "b", created_at: 1793200000, model: "m", index: index(0.4, 0.9), weighted: null },
  { run_id: "a", created_at: 1793100000, model: "m", index: index(0.333, 0.8567), weighted: null },
]);
check("oldest first", series[0].base === 33.3 && series[1].mizan === 90);
check("rounded to a tenth", series[0].mizan === 85.7);
check("missing index stays empty", historySeries([{ run_id: "c", created_at: 1, model: null, index: null, weighted: null }])[0].base === null);
check("short hash", short("a".repeat(64)) === "aaaaaaaaaa…aaaa" && short(null) === "—" && short("abc") === "abc");
check(
  "view shape",
  isPublicView({ latest: null, history: [], sakk: { public_key: "k", roots: [] } }) &&
    !isPublicView({ detail: "Not Found" }) &&
    !isPublicView(null),
);

console.log(`reliability: ${checks} checks passed`);
