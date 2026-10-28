/** Sidq, the Truth Gate: what MIZAN corrected, removed or marked before showing an answer. */

export interface SidqItem {
  kind: string;
  detail: string;
}

export interface SidqReport {
  mode: "strict" | "flag";
  /** The gate's one-line summary (channels without a notes view print it). */
  note?: string;
  corrected: SidqItem[];
  removed: SidqItem[];
  flagged: SidqItem[];
  links?: { checked: number; dead: string[] };
}

const KIND_LABELS: Record<string, string> = {
  arithmetic: "Arithmetic",
  quote: "Quoted text",
  action: "Claimed action",
  citation: "Citation",
  link: "Link",
  hadith_source: "Hadith source",
};

/** A report worth showing: the gate changed or marked something. */
export function isSidq(value: unknown): value is SidqReport {
  if (!value || typeof value !== "object") return false;
  const report = value as Partial<SidqReport>;
  return (
    Array.isArray(report.corrected) &&
    Array.isArray(report.removed) &&
    Array.isArray(report.flagged) &&
    report.corrected.length + report.removed.length + report.flagged.length > 0
  );
}

export function sidqHeadline(report: SidqReport): string {
  const parts = [
    report.corrected.length ? `${report.corrected.length} corrected` : "",
    report.removed.length ? `${report.removed.length} removed` : "",
    report.flagged.length ? `${report.flagged.length} marked` : "",
  ].filter(Boolean);
  return `Truth Gate: ${parts.join(", ")}`;
}

/** Every change as one line: what it was and what MIZAN did. */
export function sidqLines(report: SidqReport): string[] {
  const line = (verb: string) => (item: SidqItem) => `${KIND_LABELS[item.kind] ?? item.kind} ${verb}: ${item.detail}`;
  return [
    ...report.corrected.map(line("corrected")),
    ...report.removed.map(line("removed")),
    ...report.flagged.map((item) =>
      item.kind === "hadith_source" ? `${KIND_LABELS[item.kind]}: ${item.detail}` : line("not backed")(item),
    ),
  ];
}
