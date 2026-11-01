/** Muraqabah: watchers, quiet windows around salah, and learned attention. */

export type TriggerKind = "daily" | "prayer" | "hijri" | "page";
export const PRAYERS = ["fajr", "dhuhr", "asr", "maghrib", "isha"] as const;

export interface Watcher {
  id: string;
  title: string;
  trigger: Record<string, unknown> & { kind: TriggerKind };
  task: string;
  priority: "judge" | "always";
  enabled: boolean;
  when: string;
  next_due: string | null;
  last_fired: string | null;
}

export interface Place {
  label: string;
  lat: number;
  lon: number;
  tz: string;
  method: string;
  hanafi: boolean;
  budget: number;
  digest: string;
  quiet: boolean;
}

export interface Overview {
  place: Place | null;
  today: {
    date: string;
    times: Record<string, string>;
    quiet: { prayer: string; from: string; to: string }[];
    quiet_now: boolean;
  } | null;
  watchers: Watcher[];
  delivered_today: number;
  budget: number;
  attention: Record<string, { useful: number; not_now: number }>;
  session_id: string;
  methods: string[];
}

export interface TriggerForm {
  kind: TriggerKind;
  time: string;
  prayer: string;
  offset: number;
  days: string;
  url: string;
  hours: number;
}

/** The trigger the API expects, from the form's fields. */
export function triggerFrom(form: TriggerForm): Record<string, unknown> {
  switch (form.kind) {
    case "daily":
      return { kind: "daily", time: form.time };
    case "prayer":
      return { kind: "prayer", prayer: form.prayer, offset: Math.round(form.offset) };
    case "hijri":
      return {
        kind: "hijri",
        days: form.days
          .split(/[\s,]+/)
          .map(Number)
          .filter((day) => Number.isInteger(day) && day >= 1 && day <= 30),
        time: form.time,
      };
    case "page":
      return { kind: "page", url: form.url.trim(), hours: form.hours };
  }
}

/** How often this kind of notice was useful: the posterior mean, as a whole percent. */
export function usefulShare(counts: { useful: number; not_now: number }): number {
  const total = counts.useful + counts.not_now;
  return total > 0 ? Math.round((counts.useful / total) * 100) : 0;
}

/** A UTC time shown in the user's own time zone. */
export function localTime(iso: string | null, timeZone: string | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timeZone || "UTC",
  });
}

export const STATUS_LABELS: Record<string, string> = {
  pending: "waiting",
  held: "held for salah",
  digest: "in tonight's digest",
  delivered: "delivered",
  opened: "useful",
  dismissed: "not now",
};
