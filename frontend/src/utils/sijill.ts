/** Sijill: the live record of what MIZAN learns from your work, as it learns it. */

export interface LearningNote {
  seq: number;
  at: number;
  kind: string;
  summary: string;
  details?: Record<string, string | number | boolean>;
}

export const NOTE_LABELS: Record<string, string> = {
  taallum: "Wording",
  hifz: "Program memory",
  tajriba: "Repair lesson",
  tajdid: "Instruction",
  majlis: "Routing",
  game: "Game",
  sidq: "Truth Gate",
};

/** New notes first, without duplicates, at most ``max`` of them. */
export function mergeNotes(previous: LearningNote[], incoming: LearningNote[], max = 50): LearningNote[] {
  const seen = new Set(previous.map((note) => note.seq));
  const fresh = incoming.filter((note) => !seen.has(note.seq)).sort((a, b) => b.seq - a.seq);
  return [...fresh, ...previous].slice(0, max);
}

/** How long ago, in a few words. */
export function ago(at: number, now: number = Date.now() / 1000): string {
  const seconds = Math.max(0, Math.round(now - at));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
