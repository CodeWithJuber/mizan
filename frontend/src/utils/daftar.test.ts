import { expiryIn, isLedger, provenance, type DaftarEntry } from "./daftar.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const now = new Date("2026-10-27T12:00:00Z");
const note: DaftarEntry = {
  id: "note:1",
  kind: "note",
  content: "Prays Fajr at the masjid",
  source: { kind: "manual", label: "you added it" },
  created: "2026-10-03T08:00:00Z",
  last_used: "2026-10-27T09:00:00Z",
  expires: "",
  editable: true,
};
check("recognised", isLedger({ entries: [], counts: {} }) && !isLedger({}) && !isLedger(null));
check("dates read as words", provenance(note, now) === "you added it · made 3 Oct · last used today");
check(
  "an unused note says so and shows its expiry",
  provenance({ ...note, last_used: "", expires: "2026-11-01T00:00:00Z" }, now) ===
    "you added it · made 3 Oct · not used yet · forgotten after 1 Nov",
);
check("yesterday", provenance({ ...note, last_used: "2026-10-26T20:00:00Z" }, now).endsWith("last used yesterday"));
check("other years show the year", provenance({ ...note, created: "2025-01-05T00:00:00Z" }, now).includes("5 Jan 2025"));
check("expiry in days", expiryIn(7, now) === "2026-11-03T12:00:00.000Z" && expiryIn(0, now) === "");

console.log(`daftar: ${checks} checks passed`);
