import { browserTimeZone, timeZoneField } from "./timezone.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

check("a real zone is kept", browserTimeZone(() => "Asia/Kolkata") === "Asia/Kolkata");
check("an odd value is dropped", browserTimeZone(() => "../../etc/passwd x") === undefined);
check("a failing lookup is dropped", browserTimeZone(() => { throw new Error("no Intl"); }) === undefined);
check("the field is omitted without a zone", Object.keys(timeZoneField(null)).length === 0);
check("the field carries the zone", timeZoneField("Europe/London").timezone === "Europe/London");
check("this runtime reports a zone or nothing", ["string", "undefined"].includes(typeof browserTimeZone()));

console.log(`timezone: ${checks} checks passed`);
