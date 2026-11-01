/** Iqtisad: what a user's model calls cost, against their spending limits. */

export type Period = "day" | "month";

export interface SpendDay {
  day: string;
  cost_usd: number;
  calls: number;
}

export interface SpendModel {
  model: string;
  cost_usd: number;
  calls: number;
  estimated_calls: number;
}

export interface SpendSummary {
  day: string;
  month: string;
  spent_usd: Record<Period, number>;
  limits_usd: Record<Period, number | null>;
  own_limits_usd: Record<Period, number | null>;
  remaining_usd: Record<Period, number | null>;
  renews_at: Record<Period, string>;
  history: SpendDay[];
  by_model: SpendModel[];
  unpriced: string;
}

export interface SpendUser {
  owner_id: string;
  username: string;
  cost_usd: number;
  calls: number;
  limits_usd: Record<Period, number | null>;
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function isSummary(value: unknown): value is SpendSummary {
  return (
    record(value) &&
    record(value.spent_usd) &&
    record(value.limits_usd) &&
    Array.isArray(value.history) &&
    Array.isArray(value.by_model)
  );
}

/** Dollars with enough digits that a small spend never reads as $0.00. */
export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "$0";
  if (Math.abs(value) < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

/** Spent as a share of the limit (0…1), or null when there is no limit. */
export function share(spent: number, limit: number | null): number | null {
  if (limit === null || !Number.isFinite(limit)) return null;
  if (limit <= 0) return 1;
  return Math.min(1, Math.max(0, spent / limit));
}

/** One bar per day for the last `days` days ending today, empty days as $0. */
export function dailySeries(history: SpendDay[], today: string, days = 30): SpendDay[] {
  const byDay = new Map(history.map((entry) => [entry.day, entry]));
  const end = new Date(`${today}T00:00:00Z`);
  const series: SpendDay[] = [];
  for (let back = days - 1; back >= 0; back--) {
    const date = new Date(end.getTime() - back * 86_400_000).toISOString().slice(0, 10);
    series.push(byDay.get(date) ?? { day: date, cost_usd: 0, calls: 0 });
  }
  return series;
}

/** A limit typed by the user: a number, null for "no limit", or undefined if invalid. */
export function parseLimit(text: string): number | null | undefined {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) && value >= 0 ? value : undefined;
}

/** "renews 28 Oct, 00:00" in the viewer's locale-free short form. */
export function renewal(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || "");
  if (!match) return "";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(match[3])} ${months[Number(match[2]) - 1]}, ${match[4]}:${match[5]}`;
}
