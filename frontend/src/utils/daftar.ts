/** Daftar: everything MIZAN keeps about the user, with where it came from. */

export type EntryKind = "note" | "preference" | "summary" | "learned";

export interface DaftarEntry {
  id: string;
  kind: EntryKind;
  content: string;
  key?: string;
  tags?: string[];
  source: { kind: string; label: string; session_id?: string };
  created: string;
  last_used: string;
  uses?: number;
  expires: string;
  editable: boolean;
}

export interface Ledger {
  entries: DaftarEntry[];
  counts: Partial<Record<EntryKind, number>>;
}

export const KINDS: { key: EntryKind | ""; label: string }[] = [
  { key: "", label: "All" },
  { key: "note", label: "Notes" },
  { key: "preference", label: "Preferences" },
  { key: "summary", label: "Chat summaries" },
  { key: "learned", label: "Learned" },
];

export function isLedger(value: unknown): value is Ledger {
  return !!value && typeof value === "object" && Array.isArray((value as Ledger).entries);
}

/** "made 3 Oct · last used today · expires 1 Nov": only the dates the entry has. */
export function provenance(entry: DaftarEntry, now: Date = new Date()): string {
  const parts = [entry.source.label];
  if (entry.created) parts.push(`made ${day(entry.created, now)}`);
  if (entry.last_used) parts.push(`last used ${day(entry.last_used, now)}`);
  else if (entry.kind === "note") parts.push("not used yet");
  if (entry.expires) parts.push(`forgotten after ${day(entry.expires, now)}`);
  return parts.join(" · ");
}

function day(iso: string, now: Date): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10);
  const same = (a: Date, b: Date) => a.toISOString().slice(0, 10) === b.toISOString().slice(0, 10);
  if (same(date, now)) return "today";
  const yesterday = new Date(now.getTime() - 86_400_000);
  if (same(date, yesterday)) return "yesterday";
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    ...(date.getUTCFullYear() !== now.getUTCFullYear() ? { year: "numeric" } : {}),
    timeZone: "UTC",
  });
}

/** An expiry chosen as "in N days", sent as an ISO time ("" keeps it forever). */
export function expiryIn(days: number, now: Date = new Date()): string {
  return days > 0 ? new Date(now.getTime() + days * 86_400_000).toISOString() : "";
}
