/**
 * The public reliability page: MIZAN's published AGI-test results (aggregates
 * only) and its signed Sakk roots, readable without signing in.
 */
import type { Report } from "./imtihan.ts";

export interface SignedRoot {
  day: string;
  root: string;
  leaves: number;
  signature: string;
  signed_at: string;
}

export interface PublishedRun {
  run_id: string;
  created_at: number;
  published_at: string;
  model: string | null;
  repeats: number | null;
  blocks: string[];
  report: Report;
  report_sha256: string;
  receipt: { seq?: number; hash?: string };
}

export interface HistoryEntry {
  run_id: string;
  created_at: number;
  model: string | null;
  index: Report["index"] | null;
  weighted: Report["weighted"] | null;
}

export interface PublicView {
  latest: PublishedRun | null;
  history: HistoryEntry[];
  sakk: { public_key: string; roots: SignedRoot[] };
}

export function isPublicView(value: unknown): value is PublicView {
  const view = value as PublicView | null;
  return (
    !!view &&
    Array.isArray(view.history) &&
    !!view.sakk &&
    typeof view.sakk.public_key === "string" &&
    Array.isArray(view.sakk.roots)
  );
}

/** Oldest first, as percentages, for the history chart. */
export function historySeries(history: HistoryEntry[]) {
  return [...history]
    .sort((a, b) => a.created_at - b.created_at)
    .map((entry) => ({
      date: new Date(entry.created_at * 1000).toISOString().slice(0, 10),
      base: entry.index?.base.score != null ? Math.round(entry.index.base.score * 1000) / 10 : null,
      mizan: entry.index?.mizan.score != null ? Math.round(entry.index.mizan.score * 1000) / 10 : null,
    }));
}

/** A long hex digest shortened for display; the full value stays in the title. */
export function short(hash: string | null | undefined, keep = 10): string {
  if (!hash) return "—";
  return hash.length <= keep + 4 ? hash : `${hash.slice(0, keep)}…${hash.slice(-4)}`;
}
