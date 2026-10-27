import { localTime, triggerFrom, usefulShare, type TriggerForm } from "./muraqabah.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const form: TriggerForm = { kind: "prayer", time: "08:00", prayer: "fajr", offset: 20.4, days: "13, 14 15 x 31", url: " https://masjid.example ", hours: 6 };
check("prayer", JSON.stringify(triggerFrom(form)) === '{"kind":"prayer","prayer":"fajr","offset":20}');
check("daily", JSON.stringify(triggerFrom({ ...form, kind: "daily" })) === '{"kind":"daily","time":"08:00"}');
check("hijri keeps only days 1-30", JSON.stringify(triggerFrom({ ...form, kind: "hijri" })) === '{"kind":"hijri","days":[13,14,15],"time":"08:00"}');
check("page trims the address", (triggerFrom({ ...form, kind: "page" }) as { url: string }).url === "https://masjid.example");
check("useful share", usefulShare({ useful: 3, not_now: 1 }) === 75 && usefulShare({ useful: 0, not_now: 0 }) === 0);
check("local time", localTime("2026-10-30T14:30:00+00:00", "Asia/Karachi") === "Fri 30 Oct, 19:30");
check("no time", localTime(null, "Asia/Karachi") === "—");

console.log(`muraqabah: ${checks} checks passed`);
