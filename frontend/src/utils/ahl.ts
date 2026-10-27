/** Ahl al-Dhikr: what MIZAN's sources said about the claims of an answer in the model's own words. */

export interface AhlItem {
  claim: string;
  verdict: "supported" | "contradicted";
  says?: string;
  title?: string;
  url?: string;
  /** "ilm" (settled before), "wikipedia" or "web" */
  source?: string;
  checked?: string;
}

export interface AhlReport {
  checked: number;
  supported: AhlItem[];
  contradicted: AhlItem[];
  unknown: number;
  ruling?: boolean;
}

const SOURCE_LABELS: Record<string, string> = {
  ilm: "settled before",
  wikipedia: "Wikipedia",
  web: "web search",
};

export function isAhl(value: unknown): value is AhlReport {
  if (!value || typeof value !== "object") return false;
  const report = value as Partial<AhlReport>;
  return Array.isArray(report.supported) && Array.isArray(report.contradicted) && typeof report.checked === "number";
}

export function ahlHeadline(report: AhlReport): string {
  if (!report.checked) return report.ruling ? "Sources: a ruling question, for a scholar" : "Sources asked";
  const parts = [
    report.supported.length ? `${report.supported.length} confirmed` : "",
    report.contradicted.length ? `${report.contradicted.length} contradicted` : "",
    report.unknown ? `${report.unknown} not found` : "",
  ].filter(Boolean);
  const headline = `Sources asked: ${parts.join(", ")}`;
  // No claim settled: the answer is the language model's own words.
  const settled = report.supported.length + report.contradicted.length;
  return settled ? headline : `${headline} — the model's own words, Allahu a'lam`;
}

/** Each settled claim with where it was settled. */
export function ahlLines(report: AhlReport): { text: string; url?: string }[] {
  const line = (verb: string) => (item: AhlItem) => ({
    text: `${verb}: ${item.claim} — ${item.title ?? ""} (${SOURCE_LABELS[item.source ?? ""] ?? item.source ?? ""})`,
    url: item.url,
  });
  return [...report.supported.map(line("Confirmed")), ...report.contradicted.map(line("Contradicted"))];
}
