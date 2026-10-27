/** Helpers for the administrator's runtime settings form. */

export interface RuntimeSetting {
  key: string;
  group: string;
  label: string;
  kind: "text" | "int" | "float" | "bool" | "choice" | "secret" | "url";
  description: string;
  default: string;
  choices: string[];
  minimum: number | null;
  maximum: number | null;
  apply: "live" | "provider" | "restart";
  source: "admin" | "environment" | "default";
  restart_pending: boolean;
  value: string | null;
  is_set: boolean;
}

export const isOn = (value: string) => ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());

/** Only real changes are sent: untouched secrets, equal values and no-op resets are dropped. */
export function pendingChanges(
  settings: RuntimeSetting[],
  edits: Record<string, string | boolean | null>,
): Record<string, string | boolean | null> {
  const result: Record<string, string | boolean | null> = {};
  const byKey = new Map(settings.map((item) => [item.key, item]));
  for (const [key, value] of Object.entries(edits)) {
    const item = byKey.get(key);
    if (!item) continue;
    if (value === null) {
      if (item.source === "admin") result[key] = null;
      continue;
    }
    if (item.kind === "secret") {
      if (typeof value === "string" && value.trim()) result[key] = value.trim();
      continue;
    }
    if (item.kind === "bool") {
      const current = isOn(item.value ?? item.default);
      if (Boolean(value) !== current) result[key] = Boolean(value);
      continue;
    }
    if (String(value) !== String(item.value ?? "")) result[key] = String(value);
  }
  return result;
}
