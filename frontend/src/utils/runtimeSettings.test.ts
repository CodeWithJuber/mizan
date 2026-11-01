import { isOn, pendingChanges, type RuntimeSetting } from "./runtimeSettings.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const base = { group: "Model", label: "x", description: "", default: "", choices: [] as string[], minimum: null, maximum: null, apply: "live" as const, restart_pending: false, is_set: true };
const settings: RuntimeSetting[] = [
  { ...base, key: "MIZAN_CHAT_EFFORT", kind: "choice", value: "high", source: "environment" },
  { ...base, key: "MIZAN_NLP_NATIVE_WSD", kind: "bool", value: "1", source: "environment" },
  { ...base, key: "OPENROUTER_API_KEY", kind: "secret", value: null, source: "admin" },
  { ...base, key: "MIZAN_CHAT_MAX_STEPS", kind: "int", value: "100", source: "admin" },
];

check("1 counts as on", isOn("1") && isOn("TRUE") && !isOn("0"));
const changes = pendingChanges(settings, {
  MIZAN_CHAT_EFFORT: "high",
  MIZAN_NLP_NATIVE_WSD: true,
  OPENROUTER_API_KEY: "",
  MIZAN_CHAT_MAX_STEPS: "250",
});
check("unchanged values are not sent", !("MIZAN_CHAT_EFFORT" in changes) && !("MIZAN_NLP_NATIVE_WSD" in changes));
check("empty secret keeps the saved key", !("OPENROUTER_API_KEY" in changes));
check("changed numbers are sent as text", changes.MIZAN_CHAT_MAX_STEPS === "250");
const flips = pendingChanges(settings, { MIZAN_NLP_NATIVE_WSD: false, OPENROUTER_API_KEY: " sk-new ", MIZAN_CHAT_EFFORT: null });
check("toggle off is sent", flips.MIZAN_NLP_NATIVE_WSD === false);
check("new secret is trimmed", flips.OPENROUTER_API_KEY === "sk-new");
check("reset of a non-admin value is a no-op", !("MIZAN_CHAT_EFFORT" in flips));
check("reset of an admin value is sent", pendingChanges(settings, { MIZAN_CHAT_MAX_STEPS: null }).MIZAN_CHAT_MAX_STEPS === null);

console.log(`${checks} runtime settings checks passed`);
