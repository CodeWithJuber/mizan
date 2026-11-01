/** Ta'lim: an administrator teaches MIZAN's understanding new examples. */

export interface TalimReport {
  examples: number;
  seeds_scored: number;
  before: number;
  after: number;
  p_worse: number;
  kept: boolean;
  learned: number;
  changed_classes: Record<string, { n: number; before: number; after: number }>;
}

export interface TalimBatch {
  id: string;
  model: string;
  source: string;
  licence: string;
  by: string;
  created: number;
  status: "kept" | "refused" | "undone" | string;
  size: number;
  report: TalimReport;
}

export interface TalimView {
  enabled: boolean;
  models: Record<string, string[]>;
  languages: Record<string, string>;
  batches: TalimBatch[];
}

export function isTalimView(value: unknown): value is TalimView {
  if (!value || typeof value !== "object") return false;
  const view = value as Partial<TalimView>;
  return typeof view.models === "object" && view.models !== null && Array.isArray(view.batches);
}

/** One example per line, "label<TAB>text" or "label | text"; blank lines skipped. */
export function parseExamples(
  input: string,
  labels: string[],
  allowNew = false,
): { examples: { label: string; text: string }[]; errors: string[] } {
  const examples: { label: string; text: string }[] = [];
  const errors: string[] = [];
  input.split("\n").forEach((raw, index) => {
    const line = raw.trim();
    if (!line) return;
    const match = line.match(/^([^\t|]+?)\s*(?:\t|\|)\s*(.+)$/);
    if (!match) {
      errors.push(`Line ${index + 1}: write it as "label | text"`);
      return;
    }
    const [, label, text] = match;
    if (!allowNew && !labels.includes(label)) {
      errors.push(`Line ${index + 1}: "${label}" is not a label of this model`);
      return;
    }
    if (text.length > 500) {
      errors.push(`Line ${index + 1}: longer than 500 characters`);
      return;
    }
    examples.push({ label, text });
  });
  return { examples, errors };
}

/** "dataset label = MIZAN label" per line, for an import. */
export function parseLabelMap(input: string): Record<string, string> | null {
  const map: Record<string, string> = {};
  for (const raw of input.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const [from, to] = line.split("=").map((part) => part.trim());
    if (!from || !to) return null;
    map[from] = to;
  }
  return Object.keys(map).length ? map : null;
}

export function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** The batch's verdict in words: kept, or refused because it made MIZAN worse. */
export function verdict(report: TalimReport): string {
  const change = `${percent(report.before)} → ${percent(report.after)} on what MIZAN knew`;
  return report.kept
    ? `Kept: ${change}; reads the new examples ${percent(report.learned)}`
    : `Refused: P(worse) = ${report.p_worse.toFixed(3)} (${change})`;
}
