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
  /** A ruling question: the referral to a qualified scholar, shown under the answer. */
  referral?: string;
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

/** Each settled claim with where it was settled; a contradicted one with the
 * source's own sentence, so the reader weighs the two side by side. (Notes are
 * shown here, under the answer, never inside it.) */
export function ahlLines(report: AhlReport): { text: string; url?: string }[] {
  const where = (item: AhlItem) =>
    `${item.title ?? ""} (${SOURCE_LABELS[item.source ?? ""] ?? item.source ?? ""})`;
  return [
    ...(report.referral ? [{ text: report.referral }] : []),
    ...report.supported.map((item) => ({ text: `Confirmed: ${item.claim} — ${where(item)}`, url: item.url })),
    ...report.contradicted.map((item) => ({
      text: `Contradicted: ${item.claim} — ${where(item)} says: “${item.says ?? ""}”`,
      url: item.url,
    })),
  ];
}
